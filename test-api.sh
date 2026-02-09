#!/bin/bash

# --- CONFIGURATION ---
# Replace these with your actual IDs from SAM Outputs
USER_POOL_ID="USERPOOLID"
CLIENT_ID="CLIENTID"
API_ENDPOINT="https://APIGATEWAY/Prod/tags/Bird"

EMAIL="EMAIL"
PASSWORD="PASSWORD"

echo "🔐 Attempting to login as $EMAIL..."

# 1. Authenticate with Cognito
AUTH_OUTPUT=$(aws cognito-idp initiate-auth \
    --auth-flow USER_PASSWORD_AUTH \
    --client-id "$CLIENT_ID" \
    --auth-parameters USERNAME="$EMAIL",PASSWORD="$PASSWORD" \
    --query 'AuthenticationResult.IdToken' \
    --output text 2>&1)

# Check if authentication failed
if [[ $AUTH_OUTPUT == *"An error occurred"* ]]; then
    echo "❌ Login Failed!"
    echo "$AUTH_OUTPUT"
    exit 1
fi

ID_TOKEN=$AUTH_OUTPUT
echo "✅ Token received successfully."
echo "--------------------------------"

# 2. Curl the API using the ID Token
echo "📡 Calling API: $API_ENDPOINT"
curl -i -H "Authorization: $ID_TOKEN" "$API_ENDPOINT"

echo -e "\n--------------------------------"
echo "Done."
