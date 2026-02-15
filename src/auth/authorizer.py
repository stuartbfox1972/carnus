import json
import os
import time
import boto3
import urllib.request
import traceback
from jose import jwt, jwk

# Global cache to persist across warm starts
JWKS_CACHE = None
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME', ''))

def handler(event, context):
    global JWKS_CACHE
    
    # 1. Extract Token from Authorization header
    token = event.get('authorizationToken', '')
    if token.startswith('Bearer '):
        token = token.split(' ')[1]

    try:
        # 2. Get JWT Metadata (Unverified)
        unverified_claims = jwt.get_unverified_claims(token)
        unverified_header = jwt.get_unverified_header(token)
        
        iss = unverified_claims.get('iss')
        kid = unverified_header.get('kid')
        principal_id = unverified_claims.get('sub')
        email = unverified_claims.get('email', '')

        # 3. Fetch/Cache JWKS from Cognito
        if not JWKS_CACHE:
            print(f"Fetching JWKS from Cognito: {iss}")
            with urllib.request.urlopen(f"{iss}/.well-known/jwks.json") as response:
                JWKS_CACHE = json.loads(response.read())['keys']

        # 4. Construct Public Key & Verify Signature
        key_data = next((key for key in JWKS_CACHE if key['kid'] == kid), None)
        if not key_data:
            raise Exception(f"Public key (kid: {kid}) not found in JWKS.")

        # Cryptographically verify the token
        claims = jwt.decode(
            token, 
            key_data, 
            algorithms=['RS256'],
            options={'verify_aud': False}
        )

        # 5. Verification Logic (Token Claim -> DynamoDB Fallback)
        token_verified_claim = claims.get('email_verified')
        is_verified = str(token_verified_claim).lower() == 'true'
        
        if not is_verified:
            print(f"Token claim 'email_verified' is {token_verified_claim}. Checking DynamoDB fallback for {principal_id}...")
            is_verified = _check_dynamo_verification(principal_id)

        # 6. Generate Response
        # We pass 'sub' and 'email' in the context so the backend handlers can read them.
        # Note: All values in 'context' must be strings.
        authorizer_context = {
            'sub': str(principal_id),
            'email': str(email),
            'email_verified': str(is_verified).lower()
        }

        if is_verified:
            print(f"ALLOW: {principal_id}")
            return _generate_policy(str(principal_id), 'Allow', '*', authorizer_context)
        else:
            print(f"DENY: {principal_id}")
            return _generate_policy(str(principal_id), 'Deny', '*', authorizer_context)

    except Exception as e:
        print(f"AUTH_CRITICAL_FAILURE: {str(e)}")
        print(traceback.format_exc())
        raise Exception('Unauthorized')

def _check_dynamo_verification(user_id):
    """Real-time fallback for newly verified users with stale JWTs."""
    try:
        response = table.get_item(
            Key={'PK': f"USER#{user_id}#PROFILE", 'SK': "METADATA"},
            ProjectionExpression="EmailVerified"
        )
        item = response.get('Item')
        status = item and item.get('EmailVerified') is True
        return status
    except Exception as e:
        print(f"DYNAMO_CHECK_ERROR: {str(e)}")
        return False

def _generate_policy(principal_id, effect, resource, context):
    """
    Builds the JSON structure required by API Gateway.
    The 'context' keys will be available in downstream Lambdas.
    """
    return {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': resource
            }]
        },
        'context': context
    }
