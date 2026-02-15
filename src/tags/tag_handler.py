import json
import boto3
import os
import base64
import urllib.parse
from boto3.dynamodb.conditions import Key
from decimal import Decimal
from botocore.config import Config

# Handle DynamoDB Numbers (Decimals) for JSON serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize clients
s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
dynamodb = boto3.resource('dynamodb')

table = dynamodb.Table(os.environ['TABLE_NAME'])
THUMB_BUCKET = os.environ['THUMB_BUCKET']

def generate_presigned_url(s3_key):
    """Generates a 15-minute temporary link for the private S3 object"""
    if not s3_key:
        return None
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': THUMB_BUCKET, 'Key': s3_key},
        ExpiresIn=900
    )

def handler(event, context):
    user_id = event['requestContext']['authorizer']['principalId']
    path_params = event.get('pathParameters') or {}
    query_params = event.get('queryStringParameters') or {}
    raw_tag = path_params.get('tag_name')

    try:
        if raw_tag:
            # GALLERY VIEW: GET /tags/{tag_name}
            decoded_tag = urllib.parse.unquote(raw_tag)
            search_pk = f"USER#{user_id}#TAG#{decoded_tag}"

            query_args = {
                "KeyConditionExpression": Key('PK').eq(search_pk),
                "Limit": 50
            }

            next_token = query_params.get('next_token')
            if next_token:
                query_args["ExclusiveStartKey"] = json.loads(base64.b64decode(next_token).decode())

            response = table.query(**query_args)

            clean_items = []
            for item in response.get('Items', []):
                s3_key = item.get('ThumbnailKey')
                clean_items.append({
                    "ImageId": item['SK'].replace("IMAGE#", ""),
                    'ImageName': item.get('ImageName'),
                    "Tag": decoded_tag,
                    "ThumbnailUrl": generate_presigned_url(s3_key)
                })

            last_key = response.get('LastEvaluatedKey')
            encoded_token = base64.b64encode(json.dumps(last_key).encode()).decode() if last_key else None

            return {
                "statusCode": 200,
                "headers": { "Content-Type": "application/json" },
                "body": json.dumps({
                    "items": clean_items,
                    "next_token": encoded_token
                }, cls=DecimalEncoder)
            }

        else:
            # TAG CLOUD VIEW: GET /tags
            pk = f"USER#{user_id}#TAG_CLOUD"
            response = table.query(KeyConditionExpression=Key('PK').eq(pk))

            data = []
            for i in response.get('Items', []):
                data.append({
                    "Text": i['SK'].replace("TAG#", ""),
                    "Count": i.get('Count', 0)
                })

            data.sort(key=lambda x: x['Count'], reverse=True)

            return {
                "statusCode": 200,
                "headers": { "Content-Type": "application/json" },
                "body": json.dumps(data, cls=DecimalEncoder)
            }

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
