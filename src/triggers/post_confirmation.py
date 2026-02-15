import json
import boto3, os
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
table_name = os.environ['TABLE_NAME']
table = dynamodb.Table(table_name)

def handler(event, context):
    user_attributes = event['request']['userAttributes']
    user_id = user_attributes['sub']  # Permanent UUID for this user
    email = user_attributes['email']
    # Cognito sends attributes as strings, even booleans
    is_verified = user_attributes.get('email_verified') == 'true'

    # Define our PK/SK pattern for a User Profile
    # Updated to match Authorizer expectations: PK: USER#<sub>#PROFILE, SK: METADATA
    item = {
        'PK': f"USER#{user_id}#PROFILE",
        'SK': "METADATA",
        'GSI1PK': "USER_LIST", 
        'GSI1SK': email,
        'Email': email,
        'EmailVerified': is_verified,
        'UserId': user_id,
        'CreatedAt': datetime.now(timezone.utc).isoformat(),
        'Status': 'ACTIVE',
        'StorageQuota': 107374182400 # 100GB default
    }

    try:
        table.put_item(Item=item)
        print(f"Profile created for {email} (Verified: {is_verified})")
    except Exception as e:
        print(f"Error creating profile: {str(e)}")
        raise e

    return event
