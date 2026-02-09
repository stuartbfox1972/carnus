# Get the Amplify Service Role Name
AMPLIFY_ROLE=$(aws iam list-roles --query "Roles[?contains(RoleName, 'Amplify')].RoleName" --output text | head -n 1)

# Attach the policy so Amplify can read the SAM stack outputs
aws iam put-role-policy \
  --role-name $AMPLIFY_ROLE \
  --policy-name CarnusDiscoveryPolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "cloudformation:DescribeStacks",
      "Resource": "*"
    }]
  }'
