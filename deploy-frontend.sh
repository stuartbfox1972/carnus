#!/bin/bash

# 1. Extract Stack Name & Region from local samconfig.toml
if [ ! -f "samconfig.toml" ]; then
    echo "❌ Error: samconfig.toml not found. Run 'sam deploy --guided' first."
    exit 1
fi

STACK_NAME=$(grep "stack_name" samconfig.toml | head -n 1 | sed -E 's/.*stack_name = "(.*)"/\1/')
REGION=$(grep "region" samconfig.toml | head -n 1 | sed -E 's/.*region = "(.*)"/\1/')
REGION=${REGION:-us-east-1}

echo "🔍 Found Local Stack: $STACK_NAME ($REGION)"

# 2. Find the Amplify App
APP_ID=$(aws amplify list-apps --query "apps[?name=='Carnus-Frontend'].appId" --output text)

if [ -z "$APP_ID" ] || [ "$APP_ID" == "None" ]; then
    echo "⚠️  Amplify App 'Carnus-Frontend' not found. Creating it now..."
    # Optional: Create the app if it doesn't exist
    APP_ID=$(aws amplify create-app --name "Carnus-Frontend" --query "app.appId" --output text)
fi

# 3. Update Amplify Environment Variables
echo "🔗 Injecting STACK_NAME into Amplify..."
aws amplify update-app --app-id "$APP_ID" --environment-variables STACK_NAME="$STACK_NAME"

# 4. Grant Amplify permission to read CloudFormation
# Pulls the service role assigned to the Amplify app
ROLE_NAME=$(aws amplify get-app --app-id "$APP_ID" --query "app.iamServiceRole" --output text | awk -F/ '{print $NF}')

if [ -n "$ROLE_NAME" ] && [ "$ROLE_NAME" != "None" ]; then
    echo "🔐 Attaching ReadOnly policy to Amplify Role: $ROLE_NAME"
    aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
else
    echo "💡 Note: No Service Role found for Amplify. Ensure you assign one in the console."
fi

echo "✅ Handshake complete. You can now 'git push' to deploy the frontend."
