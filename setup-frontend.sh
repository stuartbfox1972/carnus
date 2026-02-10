#!/bin/bash

# --- 1. Validation ---
echo "🎨 Carnus Frontend Handshake (Manual Repo Link)"
echo "============================="

if [ ! -f "samconfig.toml" ]; then
    echo "❌ Error: samconfig.toml not found."
    exit 1
fi

STACK_NAME=$(grep "stack_name" samconfig.toml | head -n 1 | sed -E 's/.*stack_name = "(.*)"/\1/')
REGION=$(grep "region" samconfig.toml | head -n 1 | sed -E 's/.*region = "(.*)"/\1/')
REGION=${REGION:-"us-east-1"}

# --- 2. AWS Resource Discovery ---
echo "🔍 Fetching resource IDs from CloudFormation ($STACK_NAME)..."
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)
CLIENT_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" --output text)
API_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='CarnusApiUrl'].OutputValue" --output text)

# --- 3. Amplify App Creation (No Repo Link to avoid Token error) ---
APP_NAME="Carnus-Frontend"
APP_ID=$(aws amplify list-apps --query "apps[?name=='$APP_NAME'].appId" --output text)

if [ -z "$APP_ID" ] || [ "$APP_ID" == "None" ] || [ -z "$(echo $APP_ID | tr -d '[:space:]')" ]; then
    echo "🏗️  Creating Amplify App shell '$APP_NAME'..."
    # We create the app without the repo to avoid the token requirement
    APP_ID=$(aws amplify create-app --name "$APP_NAME" --query "app.appId" --output text)
    echo "✅ Created Amplify App: $APP_ID"
else
    echo "✨ Found existing Amplify App: $APP_ID"
fi

# --- 4. Permissions & Service Role ---
ROLE_NAME="AmplifyConsoleServiceRole-${STACK_NAME}"
ROLE_ARN=$(aws iam list-roles --query "Roles[?RoleName=='$ROLE_NAME'].Arn" --output text)

if [ -z "$ROLE_ARN" ] || [ "$ROLE_ARN" == "None" ]; then
    echo "🔐 Creating IAM Service Role..."
    cat <<EOF > trust-policy.json
{
  "Version": "2012-10-17",
  "Statement": [{ "Effect": "Allow", "Principal": { "Service": "amplify.amazonaws.com" }, "Action": "sts:AssumeRole" }]
}
EOF
    ROLE_ARN=$(aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document file://trust-policy.json --query "Role.Arn" --output text)
    rm trust-policy.json
    aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/AdministratorAccess-Amplify
    aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
fi

# Link role to App
aws amplify update-app --app-id "$APP_ID" --iam-service-role "$ROLE_ARN"

# --- 5. Generate Local Config & Set Cloud Env ---
echo "⚙️  Finalizing configurations..."
mkdir -p frontend/src
cat <<EOF > frontend/src/amplify-config.js
export const amplifyConfig = {
  Auth: { Cognito: { userPoolId: '$USER_POOL_ID', userPoolClientId: '$CLIENT_ID' } },
  API: { REST: { CarnusApi: { endpoint: '$API_URL', region: '$REGION' } } }
};
EOF

aws amplify update-app --app-id "$APP_ID" --environment-variables STACK_NAME="$STACK_NAME"

echo "📦 Installing npm dependencies..."
cd frontend && npm install

echo "============================="
echo "🎉 Local setup complete!"
echo "👉 FINAL STEP: You must manually link the GitHub repo in the Console:"
echo "🔗 https://$REGION.console.aws.amazon.com/amplify/home?region=$REGION#/$APP_ID/settings/repository"
