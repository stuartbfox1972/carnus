import os
import json
import re
import io
import time
import hashlib
import threading
import brotli
import base64
from datetime import datetime
from decimal import Decimal
from urllib.parse import unquote_plus
from PIL import Image
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

# --- IDEMPOTENCY HELPER ---
def undo_old_metrics(user_id, image_id, table, settings):
    """Subtracts old counts for tags and stats before re-processing an image."""
    pk = f"USER#{user_id}#IMAGE"
    sk = f"IMAGE#{image_id}"
    try:
        # Fetch existing tags and size to perform a precise decrement
        resp = table.get_item(
            Key={'PK': pk, 'SK': sk}, 
            ProjectionExpression="Labels, Make, CameraModel, Lens, #sz", 
            ExpressionAttributeNames={'#sz': 'Size'}
        )
        if 'Item' in resp:
            old = resp['Item']
            old_tags = set(old.get('Labels', []))
            old_tags.update([old.get('Make'), old.get('CameraModel'), old.get('Lens')])
            
            # Revert Tag Cloud
            for tag in {t for t in old_tags if t and t != 'Unknown'}:
                table.update_item(
                    Key={'PK': f"USER#{user_id}#TAG_CLOUD", 'SK': f'TAG#{tag}'},
                    UpdateExpression="ADD #cnt :dec",
                    ExpressionAttributeNames={'#cnt': 'Count'},
                    ExpressionAttributeValues={':dec': -1}
                )
            # Revert Profile Stats
            table.update_item(
                Key={'PK': f"USER#{user_id}#PROFILE", 'SK': 'METADATA'},
                UpdateExpression="ADD StorageBytesUsed :sz, ImageCount :inc",
                ExpressionAttributeValues={':sz': -old.get('Size', 0), ':inc': -1}
            )
    except Exception as e:
        if settings.get('debug'): print(f"⚠️ [UNDO] Reversion failed: {e}")

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

def parse_gps(val, ref):
    if not val: return None
    try:
        parts = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", str(val))]
        if not parts: return None
        if len(parts) < 3:
            decimal = parts[0]
        else:
            d, m, s = parts[:3]
            decimal = d + (m / 60.0) + (s / 3600.0)
        if ref and str(ref).strip().upper()[:1] in ['S', 'W']:
            decimal = -decimal
        return Decimal(str(round(decimal, 6)))
    except:
        return None

def get_fuzzy_tag(data, pattern):
    matches = [
        (k, str(v).strip()) for k, v in data.items()
        if re.search(pattern, k, re.I) and v is not None and str(v).strip() != ""
    ]
    if not matches: return None
    return sorted(matches, key=lambda x: len(x[0]))[0][1]

def wrap_decimal(obj):
    if isinstance(obj, list): return [wrap_decimal(i) for i in obj]
    if isinstance(obj, dict): return {k: wrap_decimal(v) for k, v in obj.items()}
    if isinstance(obj, float): return Decimal(str(obj))
    return obj

def generate_short_id(s3_key):
    return hashlib.sha256(s3_key.encode()).hexdigest()[:12]

# --- MAIN PROCESSOR ---
def process_image(img_data, user_id, settings, s3, rek, table):
    filename = img_data['filename']
    raw_exif = json.loads(brotli.decompress(base64.b64decode(img_data['exif'])))
    preview_bytes = brotli.decompress(base64.b64decode(img_data['thumb']))
    file_size = len(preview_bytes)

    exif_date_raw = get_fuzzy_tag(raw_exif, r'SubSecCreateDate|SubSecDateTimeOriginal|CreateDate|DateTimeOriginal|CreateDate$')
    image_id = hashlib.sha256(f"{exif_date_raw}{filename}".encode()).hexdigest()[:10]

    pk = f"USER#{user_id}#IMAGE"
    sk = f"IMAGE#{image_id}"

    if settings.get('force_reprocess', False):
        if img_data.get('force_reprocess', False) or settings.get('force_reprocess', False):
            if settings.get('debug'): print(f"♻️ [FORCE] Correcting stats/tags for {image_id}")
            undo_old_metrics(user_id, image_id, table, settings)
    else:
        existing = table.get_item(Key={'PK': pk, 'SK': sk}, ProjectionExpression="PK")
        if 'Item' in existing: return

    iso_date_str = re.sub(r'^(\d{4}):(\d{2}):(\d{2})', r'\1-\2-\3', str(exif_date_raw)).replace(" ", "T")
    dt_obj = datetime.fromisoformat(iso_date_str)
    dt_str = dt_obj.isoformat()
    date_path = dt_obj.strftime('%Y/%m/%d')
    s3_key = f"protected/{user_id}/{date_path}/{filename}.jpg"

    s3.put_object(Bucket=settings['assets_bucket'], Key=s3_key, Body=preview_bytes, ContentType='image/jpeg')

    img = Image.open(io.BytesIO(preview_bytes))
    img.thumbnail((1600, 1600))
    rek_buf = io.BytesIO()
    img.save(rek_buf, format="JPEG", quality=85)
    rek_payload = rek_buf.getvalue()

    rek_resp = rek.detect_labels(Image={'Bytes': rek_payload}, MaxLabels=15, MinConfidence=75)
    labels = [l['Name'] for l in rek_resp['Labels']] or ["Uncategorized"]

    faces = []
    if any(l['Name'] == 'Face' and l['Confidence'] > 75 for l in rek_resp['Labels']):
        face_resp = rek.detect_faces(Image={'Bytes': rek_payload}, Attributes=['ALL'])
        for face in face_resp.get('FaceDetails', [])[:3]:
            faces.append({
                "BoundingBox": face.get("BoundingBox"),
                "AgeRange": face.get("AgeRange"),
                "Gender": face.get("Gender") if face.get("Gender", {}).get("Confidence", 0) >= 60 else None,
                "Smile": face.get("Smile") if face.get("Smile", {}).get("Confidence", 0) >= 60 else None,
                "EyesOpen": face.get("EyesOpen") if face.get("EyesOpen", {}).get("Confidence", 0) >= 60 else None,
                "MouthOpen": face.get("MouthOpen") if face.get("MouthOpen", {}).get("Confidence", 0) >= 60 else None,
                "Emotions": [
                    {"Type": e["Type"], "Confidence": e["Confidence"]}
                    for e in face.get("Emotions", []) if e.get("Confidence", 0) >= 60
                ]
            })

    lens_val = get_fuzzy_tag(raw_exif, r'LensID$|LensModel$|^Lens$')
    camera_model = get_fuzzy_tag(raw_exif, r'Model$|UniqueCameraModel$')
    make_val = get_fuzzy_tag(raw_exif, r'Make$|Manufacturer$')

    hw_tags = [v for v in [make_val, camera_model, lens_val] if v and v != 'Unknown']
    all_searchable_tags = set(labels + hw_tags)

    gps_lat = parse_gps(get_fuzzy_tag(raw_exif, r'GPSLatitude$'), get_fuzzy_tag(raw_exif, r'GPSLatitudeRef$'))
    gps_lon = parse_gps(get_fuzzy_tag(raw_exif, r'GPSLongitude$'), get_fuzzy_tag(raw_exif, r'GPSLongitudeRef$'))

    item_data = {
        'PK': pk, 'SK': sk, 'UserId': user_id, 'ImageId': image_id, 'ImageName': filename,
        'CaptureDate': dt_str, 'ProcessedAt': datetime.now().isoformat(),
        'Labels': labels, 'Faces': faces, 'ThumbnailKey': s3_key, 'Size': file_size,
        'Lens': lens_val or 'Unknown', 'CameraModel': camera_model or 'Unknown', 'Make': make_val or 'Unknown',
        'GPSLatitude': gps_lat, 'GPSLongitude': gps_lon,
        'ISO': parse_exif_numeric(get_fuzzy_tag(raw_exif, r'ISO$')),
        'Aperture': parse_exif_numeric(get_fuzzy_tag(raw_exif, r'FNumber$|Aperture$')),
        'ShutterSpeed': get_fuzzy_tag(raw_exif, r'ExposureTime$|ShutterSpeed$'),
        'exif': {}
    }

    omit = [r'MakerNote', r'Image', r'Profile', r'Curve', r'Matrix', r'Data', r'Table']
    for key, value in raw_exif.items():
        if any(re.search(p, key, re.I) for p in omit): continue
        if isinstance(value, (bytes, bytearray)) or "(Binary data" in str(value): continue
        safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', key).strip('_')
        item_data['exif'][safe_key] = value

    try:
        with table.batch_writer() as batch:
            batch.put_item(Item=wrap_decimal(item_data))
            for tag in {t for t in all_searchable_tags if t}:
                batch.put_item(Item=wrap_decimal({
                    'PK': f"USER#{user_id}#TAG#{tag}", 'SK': sk,
                    'GSI1PK': f"TAG#{tag}", 'GSI1SK': sk,
                    'ImageName': filename, 'ImageId': image_id, 'Timestamp': dt_str, 'ThumbnailKey': s3_key
                }))

        for tag in {t for t in all_searchable_tags if t}:
            table.update_item(
                Key={'PK': f"USER#{user_id}#TAG_CLOUD", 'SK': f'TAG#{tag}'},
                UpdateExpression="ADD #cnt :inc SET LabelName = :ln",
                ExpressionAttributeNames={'#cnt': 'Count'},
                ExpressionAttributeValues={':inc': 1, ':ln': tag}
            )

        table.update_item(
            Key={'PK': f"USER#{user_id}#PROFILE", 'SK': 'METADATA'},
            UpdateExpression="ADD StorageBytesUsed :sz, ImageCount :inc",
            ExpressionAttributeValues={':sz': file_size, ':inc': 1}
        )
    except Exception as e:
        print(f"❌ DynamoDB Error: {e}")

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    rek = boto3.client('rekognition')
    table = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
    settings = {
        'assets_bucket': os.environ['THUMB_BUCKET'],
        'debug': os.environ.get('DEBUG', 'false').lower() == 'true'
    }
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        obj = s3.get_object(Bucket=bucket, Key=key)
        payload = json.loads(obj['Body'].read().decode('utf-8'))

        key_parts = key.split('/')
        path_user_id = key_parts[1] if len(key_parts) > 1 else None
        payload_user_id = payload.get('user_id')

        if path_user_id and payload_user_id and path_user_id != payload_user_id:
            raise ValueError(f"Identity Mismatch! Path ID ({path_user_id}) != Payload ID ({payload_user_id})")

        user_id = path_user_id or payload_user_id or 'unknown'
        
        if settings.get('debug'):
            print(f"🚀 [PROCESS] User: {user_id} | Batch Size: {len(payload.get('images', []))} images")

        for img in payload.get('images', []):
            process_image(img, user_id, settings, s3, rek, table)

        if not settings.get('debug'):
            s3.delete_object(Bucket=bucket, Key=key)
        else:
            print(f"💾 [DEBUG] Preserving blob: {key}")

    return {"statusCode": 200}
