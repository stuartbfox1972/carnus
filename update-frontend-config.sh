#!/bin/bash

# 1. Extract the stack_name from samconfig.toml
# This regex looks for stack_name = "value" and captures the value inside the quotes
STACK_NAME=$(grep "stack_name" samconfig.toml | head -n 1 | sed -E 's/.*stack_name = "(.*)"/\1/')

if [ -z "$STACK_NAME" ]; then
    echo "❌ Error: Could not find stack_name in samconfig.toml"
    exit 1
fi

echo "🏗️  Using SAM Stack: $STACK_NAME"

# 2. Fetch the Region from samconfig.toml (optional but recommended)
REGION=$(grep "region" samconfig.toml | head -n 1 | sed -E 's/.*region = "(.*)"/\1/')
REGION=${REGION:-us-east-1}

# 3. Fetch IDs from CloudFormation using the dynamic stack name
USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
    --output text)

CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
    --output text)

# 4. Write the config to the frontend directory
cat <<EOF > frontend/src/amplify-config.js
export const amplifyConfig = {
  Auth: {
    Cognito: {
      userPoolId: '$USER_POOL_ID',
      userPoolClientId: '$CLIENT_ID'
    }
  },
  API: {
    REST: {
      CarnusApi: {
        // Matches the 'CarnusApi' resource in your template.yaml
        endpoint: 'https://3cl1502m9b.execute-api.${REGION}.amazonaws.com/Prod',
        region: '$REGION'
      }
    }
  }
};
EOF

echo "✅ frontend/src/amplify-config.js updated successfully."
