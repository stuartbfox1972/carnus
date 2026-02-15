import json
import boto3
import os
from boto3.dynamodb.conditions import Key
from decimal import Decimal
from botocore.config import Config

# Handle DynamoDB Numbers (Decimals) for JSON serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize clients with s3v4 for global compatibility
s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

def handler(event, context):
    user_id = event['requestContext']['authorizer']['sub']
    image_id = event.get('pathParameters', {}).get('image_id')

    try:
        # 1. Direct Point Read from User-Image Partition
        response = table.get_item(
            Key={
                'PK': f"USER#{user_id}#IMAGE",
                'SK': f"IMAGE#{image_id}"
            }
        )
        item = response.get('Item')

        if not item:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Image not found"})
            }

        # 2. Generate 15-minute Presigned URLs (900 seconds)
        thumb_key = item.get('ThumbnailKey')
        if thumb_key:
            signed_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': os.environ['THUMB_BUCKET'], 'Key': thumb_key},
                ExpiresIn=900
            )
            item['DetailUrl'] = signed_url
            item['ThumbnailUrl'] = signed_url
        else:
            item['DetailUrl'] = None
            item['ThumbnailUrl'] = None

        # 3. Construct Lean Payload
        # Exclude internal DynamoDB keys and the heavy Exif blob
        blacklist_prefixes = ('GSI', 'PK', 'SK')
        blacklist_exact = ('exif',)

        clean_item = {
            k: v for k, v in item.items()
            if not k.startswith(blacklist_prefixes) and k not in blacklist_exact
        }

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(clean_item, cls=DecimalEncoder)
        }

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal Server Error", "details": str(e)})
        }
