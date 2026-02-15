import json
import boto3
import os
import time
import base64
from decimal import Decimal
from botocore.exceptions import ClientError

# Handle DynamoDB Numbers (Decimals) for JSON serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
table = dynamodb.Table(os.environ['TABLE_NAME'])
bucket_name = os.environ['THUMB_BUCKET']

def handler(event, context):
    user_id = event['requestContext']['authorizer']['principalId']
    method = event['httpMethod']
    claims = event['requestContext']['authorizer'].get('claims', {})

    pk = f"USER#{user_id}#PROFILE"
    sk = "METADATA"

    try:
        if method == 'GET':
            response = table.get_item(Key={'PK': pk, 'SK': sk})
            # Default to email from claims if record is missing (Fixes Stuart)
            item = response.get('Item', {'Email': claims.get('email', 'Unknown')})

            # SANITIZATION: Remove internal DynamoDB keys
            for key in ['PK', 'SK', 'GSI1PK', 'GSI1SK']: 
                item.pop(key, None)

            # Logic: Return key ONLY if value exists, otherwise remove it
            if item.get('AvatarUrl'):
                avatar_key = item['AvatarUrl']
                try:
                    item['AvatarUrl'] = s3.generate_presigned_url('get_object', Params={
                        'Bucket': bucket_name,
                        'Key': avatar_key
                    }, ExpiresIn=3600)
                except Exception:
                    item.pop('AvatarUrl', None)
            else:
                item.pop('AvatarUrl', None)

            # Fallback logic: Use Name if exists, otherwise use Email
            first = item.get('FirstName', '').strip()
            email = item.get('Email', 'Unknown')
            item['DisplayName'] = first or email

            return {
                'statusCode': 200,
                'headers': { 'Content-Type': 'application/json' },
                'body': json.dumps(item, cls=DecimalEncoder)
            }

        elif method == 'POST':
            body = json.loads(event.get('body', '{}')) if event.get('body') else {}
            is_avatar_action = 'AvatarBlob' in body or body.get('DeleteAvatar')

            existing = table.get_item(Key={'PK': pk, 'SK': sk}).get('Item', {})

            if is_avatar_action:
                last_update = existing.get('AvatarUpdatedAt', 0)
                if time.time() - last_update < 86400:
                    return {
                        'statusCode': 418,
                        'body': json.dumps({'error': "I'm a teapot (cooldown active)"})
                    }

                if body.get('DeleteAvatar'):
                    try:
                        s3.delete_object(Bucket=bucket_name, Key=f"avatars/{user_id}.jpg")
                    except Exception: pass

                    table.update_item(
                        Key={'PK': pk, 'SK': sk},
                        UpdateExpression="REMOVE AvatarUrl SET AvatarUpdatedAt = :t",
                        ExpressionAttributeValues={':t': int(time.time())}
                    )
                    return {
                        'statusCode': 200,
                        'body': json.dumps({'message': 'Avatar deleted'})
                    }

                if 'AvatarBlob' in body:
                    try:
                        image_data = base64.b64decode(body['AvatarBlob'])
                        s3.put_object(
                            Bucket=bucket_name,
                            Key=f"avatars/{user_id}.jpg",
                            Body=image_data,
                            ContentType='image/jpeg'
                        )
                    except Exception as e:
                        print(f"S3 Upload Error: {str(e)}")
                        return {'statusCode': 500, 'body': json.dumps({'error': 'S3 Upload Failed'})}

            update_expr = "SET FirstName = :f, LastName = :l, Email = :e"
            attr_vals = {
                ':f': body.get('FirstName', existing.get('FirstName', '')),
                ':l': body.get('LastName', existing.get('LastName', '')),
                ':e': existing.get('Email', claims.get('email', 'Unknown'))
            }

            if 'AvatarBlob' in body:
                update_expr += ", AvatarUrl = :u, AvatarUpdatedAt = :t"
                attr_vals[':u'] = f"avatars/{user_id}.jpg"
                attr_vals[':t'] = int(time.time())

            response = table.update_item(
                Key={'PK': pk, 'SK': sk},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=attr_vals,
                ReturnValues="ALL_NEW"
            )

            updated_item = response.get('Attributes', {})
            
            # SANITIZATION: Remove internal keys and sensitive metadata
            for key in ['PK', 'SK', 'GSI1PK', 'GSI1SK', 'AvatarUpdatedAt']: 
                updated_item.pop(key, None)

            return {
                'statusCode': 200,
                'headers': { 'Content-Type': 'application/json' },
                'body': json.dumps(updated_item, cls=DecimalEncoder)
            }

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

    return {"statusCode": 405}
