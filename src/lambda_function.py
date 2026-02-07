import os, yaml, boto3, urllib.parse
from processor import run_processor

with open('config.yaml', 'r') as f:
    CFG = yaml.safe_load(f)

s3 = boto3.client('s3')
rek = boto3.client('rekognition')
db = boto3.resource('dynamodb').Table(CFG['aws']['dynamo_table'])

def lambda_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        tmp_path = f"/tmp/{os.path.basename(key)}"
        
        try:
            s3.download_file(bucket, key, tmp_path)
            run_processor(tmp_path, CFG, s3, rek, db)
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)
    return {'statusCode': 200}
