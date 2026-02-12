import os
import json
import subprocess
import re
import io
import time
import hashlib
import threading
from datetime import datetime
from decimal import Decimal
from PIL import Image
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

# --- GLOBAL STATE & LOCK ---
# Shared across all threads in the ThreadPoolExecutor
_cloud_wiped = False
_wipe_lock = threading.Lock()

# --- PRESERVED UTILITIES ---
def parse_exif_numeric(val):
    if val is None: return None
    try:
        s_val = str(val).lower().strip()
        if '/' in s_val:
            num, den = map(float, s_val.split('/'))
            return Decimal(str(round(num / den, 10)))
        clean_val = re.sub(r'[^\d.]', '', s_val)
        return Decimal(clean_val) if clean_val else None
    except:
        return None

def get_fuzzy_tag(data, pattern):
    matches = [
        str(v).strip() for k, v in data.items()
        if re.search(pattern, k, re.I) and v is not None and str(v).strip() != ""
    ]
    if not matches: return None
    return sorted(matches, key=len, reverse=True)[0]

def wrap_decimal(obj):
    if isinstance(obj, list): return [wrap_decimal(i) for i in obj]
    if isinstance(obj, dict): return {k: wrap_decimal(v) for k, v in obj.items()}
    if isinstance(obj, float): return Decimal(str(obj))
    return obj

def generate_short_id(s3_key):
    """Generates a consistent 12-character hex hash from the S3 path."""
    return hashlib.sha256(s3_key.encode()).hexdigest()[:12]

# --- SELF-CONTAINED THREAD-SAFE WIPE ---
def wipe_tag_cloud_if_needed(table, settings):
    """Clears global tag counts once per session, safe for multi-threading."""
    global _cloud_wiped
    
    # Fast exit for most threads
    if _cloud_wiped or not settings.get('force_reprocess', False):
        return

    # Synchronize threads here
    with _wipe_lock:
        # Double-check inside the lock in case another thread just finished the wipe
        if _cloud_wiped:
            return

        if settings.get('debug'):
            print("\n🗑️  [WIPE] force_reprocess is TRUE. Clearing Tag Cloud for clean session...")

        try:
            response = table.query(KeyConditionExpression=Key('PK').eq('TAG_CLOUD'))
            items = response.get('Items', [])
            
            if items:
                with table.batch_writer() as batch:
                    for item in items:
                        batch.delete_item(Key={'PK': 'TAG_CLOUD', 'SK': item['SK']})
                if settings.get('debug'):
                    print(f"✅ [WIPE] Successfully removed {len(items)} stale tags.")
            
            _cloud_wiped = True 
        except Exception as e:
            print(f"⚠️  [WIPE] Failed to clear cloud: {e}")

# --- MAIN PROCESSOR ---
def process_image(file_path, settings, s3, rek, table):
    # This call is now safe for your ThreadPoolExecutor
    wipe_tag_cloud_if_needed(table, settings)
    
    start_time = time.time()
    filename = os.path.basename(file_path)
    pk = f"IMAGE#{filename}"

    # 1. SKIP LOGIC
    is_forcing = settings.get('force_reprocess', False)
    if not is_forcing:
        try:
            response = table.query(
                KeyConditionExpression=Key('PK').eq(pk),
                ProjectionExpression="PK",
                Limit=1
            )
            if response.get('Items'):
                if settings.get('debug'):
                    print(f"⏭️  Skipping {filename}")
                return
        except ClientError as e:
            print(f"⚠️  DB Check Failed: {e}")
    else:
        if settings.get('debug'):
            print(f"⚡ Overwriting: {filename}")

    # 2. EXIF EXTRACTION
    meta_cmd = [settings['exiftool_path'], "-json", "-*", "-LensID", file_path]
    result = subprocess.run(meta_cmd, capture_output=True, text=True)
    if not result.stdout.strip():
        raise Exception(f"ExifTool returned no data for {filename}")
    raw_exif = json.loads(result.stdout)[0]

    # 3. DATE LOGIC
    exif_date_raw = get_fuzzy_tag(raw_exif, r'SubSecCreateDate|SubSecDateTimeOriginal|CreateDate|DateTimeOriginal')
    if not exif_date_raw:
        raise Exception(f"No capture date found in {filename}")

    iso_date_str = re.sub(r'^(\d{4}):(\d{2}):(\d{2})', r'\1-\2-\3', str(exif_date_raw)).replace(" ", "T")
    dt_obj = datetime.fromisoformat(iso_date_str)
    dt_str = dt_obj.isoformat()
    date_path = dt_obj.strftime('%Y/%m/%d')

    # 4. PREVIEW EXTRACTION & S3 UPLOAD
    extract_cmd = [settings['exiftool_path'], "-b", "-JpgFromRaw", "-PreviewImage", file_path]
    preview_bytes = subprocess.run(extract_cmd, capture_output=True).stdout
    if not preview_bytes:
        raise Exception(f"Could not extract preview from {filename}")

    s3_key = f"{date_path}/{filename}.jpg"
    s3.put_object(Bucket=settings['assets_bucket'], Key=s3_key, Body=preview_bytes, ContentType='image/jpeg')
    image_id = generate_short_id(s3_key)

    # 5. AI REKOGNITION (Labels + Top-3 Face Analysis)
    img = Image.open(io.BytesIO(preview_bytes))
    img.thumbnail((1600, 1600))
    rek_buf = io.BytesIO()
    img.save(rek_buf, format="JPEG", quality=85)
    rek_payload = rek_buf.getvalue()

    rek_resp = rek.detect_labels(
        Image={'Bytes': rek_payload},
        MaxLabels=settings.get('max_labels', 15),
        MinConfidence=settings.get('min_confidence', 75)
    )
    labels = [l['Name'] for l in rek_resp['Labels']] or ["Uncategorized"]

    face_details = []
    # Face analysis trigger (75% confidence on Face label)
    has_confident_face = any(l['Name'] == 'Face' and l['Confidence'] >= 75 for l in rek_resp['Labels'])

    if has_confident_face:
        try:
            face_resp = rek.detect_faces(Image={'Bytes': rek_payload}, Attributes=['ALL'])
            top_faces = sorted(face_resp.get('FaceDetails', []), key=lambda x: x['Confidence'], reverse=True)[:3]
            for face in top_faces:
                emotions = [e['Type'] for e in face.get('Emotions', []) if e['Confidence'] > 60]
                face_details.append({
                    'BoundingBox': face['BoundingBox'],
                    'Emotions': emotions,
                    'Smile': face.get('Smile', {}).get('Value', False),
                    'EyesOpen': face.get('EyesOpen', {}).get('Value', False),
                    'Confidence': face['Confidence']
                })
        except Exception as e:
            print(f"⚠️ Face Detection Error for {filename}: {e}")

    # 6. ASSEMBLE DYNAMODB ITEM
    lens_val = raw_exif.get('LensID') or get_fuzzy_tag(raw_exif, r'^LensModel$|^Lens$')
    camera_model = raw_exif.get('Camera Model Name') or get_fuzzy_tag(raw_exif, r'^Model$')
    camera_make = raw_exif.get('Make')

    item_data = {
        'PK': pk,
        'SK': f"ID#{image_id}",
        'ImageId': image_id,
        'ImageName': filename,
        'CaptureDate': dt_str,
        'ProcessedAt': datetime.now().isoformat(),
        'Labels': labels,
        'Faces': face_details,
        'ThumbnailKey': s3_key,
        'SourceBucket': settings['raw_bucket'],
        'ShutterSpeed': get_fuzzy_tag(raw_exif, r'^ExposureTime$|^ShutterSpeed$'),
        'Aperture': parse_exif_numeric(get_fuzzy_tag(raw_exif, r'^FNumber$|^Aperture$')),
        'FocalLength': parse_exif_numeric(get_fuzzy_tag(raw_exif, r'^FocalLength$')),
        'ISO': parse_exif_numeric(get_fuzzy_tag(raw_exif, r'^ISO$')),
        'Lens': lens_val or 'Unknown',
        'CameraModel': camera_model or 'Unknown',
        'Make': camera_make or 'Unknown',
        'exif': {}
    }

    # 7. FILTER EXIF
    omit = [r'MakerNotes', r'ThumbnailImage', r'PreviewImage', r'JpgFromRaw', r'ICC_Profile', r'^AF']
    for key, value in raw_exif.items():
        if any(re.search(p, key, re.I) for p in omit): continue
        if isinstance(value, (bytes, bytearray)) or (isinstance(value, str) and "(Binary data" in value): continue
        safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', key).strip('_')
        item_data['exif'][safe_key] = value

    # 8. INDEXING & ATOMIC UPDATES
    discovery_tags = set(labels)
    if camera_model and camera_model != 'Unknown': discovery_tags.add(camera_model)
    if lens_val and lens_val != 'Unknown': discovery_tags.add(lens_val)
    for face in face_details:
        for emo in face['Emotions']: discovery_tags.add(emo.title())
        if face['Smile']: discovery_tags.add("Smiling")

    try:
        with table.batch_writer() as batch:
            batch.put_item(Item=wrap_decimal(item_data))
            for tag in discovery_tags:
                batch.put_item(Item=wrap_decimal({
                    'PK': f"TAG#{tag}",
                    'SK': f"IMAGE#{image_id}",
                    'GSI1PK': f"TAG#{tag}",
                    'GSI1SK': f"IMAGE#{image_id}",
                    'ImageName': filename,
                    'ImageId': image_id,
                    'Timestamp': dt_str,
                    'ThumbnailKey': s3_key
                }))

        for tag in discovery_tags:
            table.update_item(
                Key={'PK': 'TAG_CLOUD', 'SK': f'TAG#{tag}'},
                UpdateExpression="ADD #cnt :inc SET LabelName = :ln",
                ExpressionAttributeNames={'#cnt': 'Count'},
                ExpressionAttributeValues={':inc': 1, ':ln': tag}
            )
    except Exception as e:
        print(f"❌ DynamoDB Write Error: {e}")

    if settings.get('debug'):
        print(f"✅ {filename} ({(time.time()-start_time)*1000:.0f}ms)")
