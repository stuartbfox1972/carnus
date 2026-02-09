import os
import json
import subprocess
import re
import io
import time
from datetime import datetime
from decimal import Decimal
from PIL import Image
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

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

# --- MAIN PROCESSOR ---
def process_image(file_path, settings, s3, rek, table):
    start_time = time.time()
    filename = os.path.basename(file_path)
    pk = f"IMAGE#{filename}"

    # 1. SKIP LOGIC
    if not settings.get('force_reprocess', False):
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

    # 5. AI REKOGNITION
    img = Image.open(io.BytesIO(preview_bytes))
    img.thumbnail((1600, 1600))
    rek_buf = io.BytesIO()
    img.save(rek_buf, format="JPEG", quality=85)

    rek_resp = rek.detect_labels(
        Image={'Bytes': rek_buf.getvalue()},
        MaxLabels=settings.get('max_labels', 15),
        MinConfidence=settings.get('min_confidence', 75)
    )
    labels = [l['Name'] for l in rek_resp['Labels']] or ["Uncategorized"]

    # 6. ASSEMBLE DYNAMODB ITEM
    lens_val = raw_exif.get('LensID')
    if not lens_val or str(lens_val).strip() == "":
        lens_val = get_fuzzy_tag(raw_exif, r'^LensModel$|^Lens$')

    item_data = {
        'PK': pk,
        'SK': dt_str,
        'CaptureDate': dt_str,
        'ProcessedAt': datetime.now().isoformat(), # Updated to your GMT offset requirement
        'Labels': labels,
        'ThumbnailKey': s3_key,
        'SourceBucket': settings['raw_bucket'],
        'ShutterSpeed': get_fuzzy_tag(raw_exif, r'^ExposureTime$|^ShutterSpeed$'),
        'Aperture': parse_exif_numeric(get_fuzzy_tag(raw_exif, r'^FNumber$|^Aperture$')),
        'FocalLength': parse_exif_numeric(get_fuzzy_tag(raw_exif, r'^FocalLength$')),
        'ISO': parse_exif_numeric(get_fuzzy_tag(raw_exif, r'^ISO$')),
        'Lens': lens_val or 'Unknown',
        'exif': {}
    }

    # 7. FILTERING & CLEANING
    omit = [r'MakerNotes', r'ThumbnailImage', r'PreviewImage', r'JpgFromRaw', r'ICC_Profile', r'^AF']
    for key, value in raw_exif.items():
        if any(re.search(p, key, re.I) for p in omit): continue
        if isinstance(value, (bytes, bytearray)) or (isinstance(value, str) and "(Binary data" in value): continue
        safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', key).strip('_')
        item_data['exif'][safe_key] = value

    # 8. WRITE TO DYNAMODB (NOW SCALABLE)
    if settings.get('debug'):
        print(f"📝 Writing {pk} and updating Tag Cloud...")

    try:
        # Step A: Write the primary image and the individual GSI entries
        with table.batch_writer() as batch:
            batch.put_item(Item=wrap_decimal(item_data))
            for label in labels:
                batch.put_item(Item=wrap_decimal({
                    'PK': f"TAG#{label}",
                    'SK': pk,
                    'GSI1PK': f"TAG#{label}",
                    'GSI1SK': pk,
                    'Timestamp': dt_str,
                    'ThumbnailKey': s3_key
                }))

        # Step B: ATOMIC INCREMENT for the Tag Cloud Partition
        # This prevents having to scan millions of rows for the cloud.
        for label in labels:
            table.update_item(
                Key={'PK': 'TAG_CLOUD', 'SK': f'TAG#{label}'},
                UpdateExpression="ADD #cnt :inc SET LabelName = :ln",
                ExpressionAttributeNames={'#cnt': 'Count'},
                ExpressionAttributeValues={':inc': 1, ':ln': label}
            )

    except Exception as e:
        print(f"❌ DynamoDB Write Error: {e}")

    if settings.get('debug'):
        print(f"✅ {filename} ({(time.time()-start_time)*1000:.0f}ms)")
