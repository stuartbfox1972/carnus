import os
import json
import subprocess
import boto3
import pygeohash as pgh
from datetime import datetime

# --- Environment & Path Configuration ---
# PERL_BIN comes from the Shogo82148 Lambda Layer
PERL_BIN = "/opt/bin/perl"
TASK_ROOT = os.environ.get('LAMBDA_TASK_ROOT', os.getcwd())
EXIF_PATH = os.path.join(TASK_ROOT, "exiftool")
EXIF_LIB  = os.path.join(TASK_ROOT, "lib")

# Clients
s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')

# Environment Variables (Injected via template.yaml)
DDB_TABLE = os.environ.get('DYNAMO_TABLE')
THUMB_BUCKET = os.environ.get('THUMB_BUCKET')
table = dynamodb.Table(DDB_TABLE)

def run(bucket, key):
    """
    Main execution logic for processing a RAW image.
    """
    local_path = f"/tmp/{os.path.basename(key)}"
    mapped_metadata = {}

    try:
        # 1. Download Asset from S3
        print(f"📥 Downloading s3://{bucket}/{key}")
        s3.download_file(bucket, key, local_path)

        # 2. Extract Text Metadata (Explicitly excluding large binary blobs)
        # These exclusions prevent DynamoDB 'ItemSize' errors.
        meta_cmd = [
            PERL_BIN, "-I", EXIF_LIB, EXIF_PATH, "-json", "-G",
            "--ThumbnailImage", "--PreviewImage", "--JpgFromRaw", "--OtherImage",
            "--MakerNotes",
            local_path
        ]
        meta_res = subprocess.run(meta_cmd, capture_output=True, text=True)
        raw_exif = json.loads(meta_res.stdout)[0] if meta_res.returncode == 0 else {}

        # 3. Extract Binary Image for Rekognition & S3 Thumbnails
        # We try Thumbnail first, then fallback to PreviewImage
        image_bytes = None
        for tag in ["-ThumbnailImage", "-PreviewImage"]:
            thumb_cmd = [PERL_BIN, "-I", EXIF_LIB, EXIF_PATH, "-b", tag, local_path]
            res = subprocess.run(thumb_cmd, capture_output=True)
            if res.stdout:
                image_bytes = res.stdout
                break

        # 4. AI Analysis & Thumbnail Storage
        if image_bytes:
            # Analyze with Rekognition (Byte-stream doesn't touch the disk)
            print("🧠 Analyzing with Rekognition...")
            rek_res = rekognition.detect_labels(
                Image={'Bytes': image_bytes}, 
                MaxLabels=15, 
                MinConfidence=80
            )
            mapped_metadata['AI_Labels'] = [l['Name'] for l in rek_res['Labels']]

            # Upload Thumbnail to S3
            thumb_key = os.path.splitext(key)[0] + ".jpg"
            print(f"🖼️  Uploading thumbnail to s3://{THUMB_BUCKET}/{thumb_key}")
            s3.put_object(
                Bucket=THUMB_BUCKET,
                Key=thumb_key,
                Body=image_bytes,
                ContentType='image/jpeg'
            )
            mapped_metadata['Thumbnail_S3_Key'] = thumb_key
        else:
            mapped_metadata['AI_Labels'] = []
            print("⚠️ No thumbnail/preview found for AI analysis.")

        # 5. Map Photographic Attributes (Using Composite tags for readability)
        mapped_metadata.update({
            'Make': raw_exif.get('EXIF:Make') or raw_exif.get('IPTC:Make', 'Unknown'),
            'Model': raw_exif.get('EXIF:Model', 'Unknown'),
            'Lens': raw_exif.get('Composite:LensID') or raw_exif.get('EXIF:LensModel', 'Unknown'),
            'FocalLength': raw_exif.get('Composite:FocalLength') or raw_exif.get('EXIF:FocalLength', '0mm'),
            'Aperture': raw_exif.get('Composite:Aperture', 'N/A'),
            'ShutterSpeed': raw_exif.get('Composite:ShutterSpeed', 'N/A'),
            'ISO': raw_exif.get('EXIF:ISO', 'Unknown'),
            'DateTime': raw_exif.get('EXIF:DateTimeOriginal') or raw_exif.get('IPTC:DateCreated', 'Unknown')
        })

        # 6. Geospatial Processing
        lat = raw_exif.get('EXIF:GPSLatitude')
        lon = raw_exif.get('EXIF:GPSLongitude')
        if lat and lon:
            try:
                mapped_metadata['Geohash'] = pgh.encode(float(lat), float(lon), precision=9)
            except (ValueError, TypeError):
                mapped_metadata['Geohash'] = "Error"
        else:
            mapped_metadata['Geohash'] = "None"

        # 7. Persistence (Unpack metadata as top-level attributes)
        print("💾 Saving record to DynamoDB...")
        table.put_item(Item={
            'PK': key,
            'Bucket': bucket,
            'ProcessedAt': datetime.utcnow().isoformat(),
            **mapped_metadata,
            'FullRawJSON': json.dumps(raw_exif) # Cleaned of binary blobs
        })

    except Exception as e:
        print(f"❌ Error processing {key}: {str(e)}")
        raise e

    finally:
        # Cleanup /tmp to prevent storage exhaustion on warm starts
        if os.path.exists(local_path):
            os.remove(local_path)
