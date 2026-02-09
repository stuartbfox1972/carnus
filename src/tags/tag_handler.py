import json
import boto3
import os
import base64
import urllib.parse
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# Handle DynamoDB Numbers (Decimals) for JSON serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

def handler(event, context):
    path_params = event.get('pathParameters') or {}
    query_params = event.get('queryStringParameters') or {}
    
    # 1. Capture the tag name from the URL
    raw_tag = path_params.get('tag_name')
    
    try:
        if raw_tag:
            # Decode %20 and other URL characters
            decoded_tag = urllib.parse.unquote(raw_tag)
            
            # Ensure we search using the internal prefix
            search_key = f"TAG#{decoded_tag}" if not decoded_tag.startswith("TAG#") else decoded_tag

            query_args = {
                "IndexName": 'GSI1',
                "KeyConditionExpression": Key('GSI1PK').eq(search_key),
                "Limit": 50
            }

            # Handle Pagination
            next_token = query_params.get('next_token')
            if next_token:
                query_args["ExclusiveStartKey"] = json.loads(base64.b64decode(next_token).decode())

            response = table.query(**query_args)
            
            # --- POST-FILTERING / SANITIZATION ---
            # Map internal DynamoDB structure to public API structure
            clean_items = []
            for item in response.get('Items', []):
                clean_items.append({
                    "image_id": item['SK'].replace("IMAGE#", ""),
                    "tag": item['PK'].replace("TAG#", ""),
                    # We only include safe, public fields here
                    "timestamp": item.get('Timestamp'), # Includes GMT offset as per requirements
                    "thumbnail_url": item.get('ThumbnailKey') # Only if projected into GSI
                })

            # Re-encode the LastEvaluatedKey for the next request
            last_key = response.get('LastEvaluatedKey')
            encoded_token = base64.b64encode(json.dumps(last_key).encode()).decode() if last_key else None

            return {
                "statusCode": 200,
                "headers": { 
                    "Content-Type": "application/json", 
                    "Access-Control-Allow-Origin": "*" 
                },
                "body": json.dumps({
                    "items": clean_items,
                    "next_token": encoded_token
                }, cls=DecimalEncoder)
            }
        
        else:
            # TAG CLOUD VIEW: GET /tags
            response = table.query(KeyConditionExpression=Key('PK').eq('TAG_CLOUD'))
            
            # Sanitize the Tag Cloud items
            data = []
            for i in response.get('Items', []):
                data.append({
                    "text": i['SK'].replace("TAG#", ""),
                    "count": i.get('Count', 0)
                })
            
            # Sort by count descending (biggest tags first)
            data.sort(key=lambda x: x['count'], reverse=True)

            return {
                "statusCode": 200,
                "headers": { 
                    "Content-Type": "application/json", 
                    "Access-Control-Allow-Origin": "*" 
                },
                "body": json.dumps(data, cls=DecimalEncoder)
            }

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal Server Error"}) # Don't leak stack traces
        }
