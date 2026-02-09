import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')
table_name = os.environ['TABLE_NAME']
table = dynamodb.Table(table_name)

def handler(event, context):
    user_attributes = event['request']['userAttributes']
    user_id = user_attributes['sub']  # Permanent UUID for this user
    email = user_attributes['email']

    # Define our PK/SK pattern for a User Profile
    # PK: USER#<sub>, SK: PROFILE
    item = {
        'PK': f"USER#{user_id}",
        'SK': "PROFILE",
        'GSI1PK': "USER_LIST", # Useful for an admin view later
        'GSI1SK': email,
        'Email': email,
        'UserId': user_id,
        'CreatedAt': boto3.utils.rfc3339_date(boto3.utils.utcnow()),
        'Status': 'ACTIVE',
        'StorageQuota': 50000000000 # 50GB default, for example
    }

    try:
        table.put_item(Item=item)
        print(f"Profile created for {email}")
    except Exception as e:
        print(f"Error creating profile: {str(e)}")
        # If we fail here, Cognito will fail the confirmation.
        # This prevents "orphan" users in Cognito without a DB record.
        raise e

    # Return the event back to Cognito to finish the confirmation
    return event
