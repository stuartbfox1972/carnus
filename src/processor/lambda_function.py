import os
import boto3
import yaml
from processor import run_processor

s3 = boto3.client('s3')
rek = boto3.client('rekognition')
db = boto3.resource('dynamodb').Table(os.environ.get('DYNAMO_TABLE'))

with open('config.yaml', 'r') as f:
    CFG = yaml.safe_load(f)

def lambda_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        temp_path = f"/tmp/{os.path.basename(key)}"
        
        try:
            s3.download_file(bucket, key, temp_path)
            # The processor creates the thumb and DB entry
            run_processor(temp_path, CFG, s3, rek, db)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    return {"status": "ok"}
