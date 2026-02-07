import subprocess
import json
import os
import time
import decimal
import pygeohash as pgh
import boto3

def run_processor(file_path, config, s3_client, rek_client, db_table):
    """
    Core logic to extract EXIF, generate a thumbnail, 
    run Rekognition AI, and save results to DynamoDB.
    """
    # Helper for DynamoDB numeric compatibility
    to_dec = lambda n: decimal.Decimal(str(round(float(n), 6)))
    
    # Detect if we are in Lambda vs Local to set binary path
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        exif_exe = config['lambda_settings'].get('exiftool_path', './exiftool')
    else:
        exif_exe = 'exiftool'

    filename = os.path.basename(file_path)

    try:
        # 1. Metadata Extraction
        # -j: JSON output, -n: Numerical GPS coords
        meta_proc = subprocess.run(
            [exif_exe, '-j', '-n', file_path], 
            capture_output=True, 
            text=True
        )
        if meta_proc.returncode != 0:
            print(f"❌ Exiftool Error for {filename}: {meta_proc.stderr}")
            return False
            
        tags = json.loads(meta_proc.stdout)[0]

        # 2. Thumbnail Extraction
        # Extracts PreviewImage (large) or ThumbnailImage (small) to stdout
        thumb_proc = subprocess.run(
            [exif_exe, '-b', '-PreviewImage', '-ThumbnailImage', '-W', '-', file_path], 
            capture_output=True
        )
        img_bytes = thumb_proc.stdout

        if not img_bytes:
            print(f"⚠️ No embedded thumbnail found in {filename}. Skipping.")
            return False

        # 3. Date & Path Parsing
        # Fallback sequence for missing dates
        dt_str = tags.get('DateTimeOriginal', tags.get('CreateDate', '1970:01:01 00:00:00'))
        dt_clean = dt_str[:19].replace('-', ':')
        dt_struct = time.strptime(dt_clean, '%Y:%m:%d %H:%M:%S')
        
        epoch = str(int(time.mktime(dt_struct)))
        s3_prefix = time.strftime('%Y/%m/%d', dt_struct)
        dest_key = f"{s3_prefix}/{filename}.jpg"

        # 4. Upload Thumbnail to S3
        # Uses the specific thumbnail bucket from universal config
        s3_client.put_object(
            Bucket=config['aws']['thumbnail_s3_bucket'],
            Key=dest_key,
            Body=img_bytes,
            ContentType='image/jpeg'
        )

        # 5. AWS Rekognition (AI Object Detection)
        labels = rek_client.detect_labels(
            Image={'Bytes': img_bytes},
            MaxLabels=config['ingestion']['max_labels'],
            MinConfidence=config['ingestion']['min_confidence']
        )['Labels']

        # 6. DynamoDB Persistence
        with db_table.batch_writer() as batch:
            # Main Image Record
            item = {
                'PK': f"IMAGE#{filename}",
                'SK': epoch,
                'thumb_path': dest_key,
                'camera': tags.get('Model', 'Unknown'),
                'labels': [l['Name'] for l in labels],
                # Clean EXIF: Remove binary data and very long strings for DDB limits
                'exif': {k: str(v) for k, v in tags.items() if len(str(v)) < 250 and 'Binary' not in k}
            }

            # Handle GPS and Geohash
            lat, lon = tags.get('GPSLatitude'), tags.get('GPSLongitude')
            if lat and lon:
                ghash = pgh.encode(lat, lon, precision=config['geospatial']['precision'])
                item.update({
                    'latitude': to_dec(lat), 
                    'longitude': to_dec(lon), 
                    'geohash': ghash
                })
                
                # Add entry to Geo-Bucket Index (e.g., GEO#abcde)
                geo_prefix = ghash[:config['geospatial']['bucket_size']]
                batch.put_item(Item={
                    'PK': f"GEO#{geo_prefix}",
                    'SK': f"IMAGE#{filename}",
                    'thumb_path': dest_key,
                    'full_hash': ghash
                })

            batch.put_item(Item=item)

            # Add Label Indexing
            for l in labels:
                batch.put_item(Item={
                    'PK': f"TAG#{l['Name'].upper()}",
                    'SK': f"IMAGE#{filename}",
                    'confidence': to_dec(l['Confidence']),
                    'thumb_path': dest_key
                })

        return True

    except Exception as e:
        print(f"❌ Critical error processing {filename}: {str(e)}")
        return False
