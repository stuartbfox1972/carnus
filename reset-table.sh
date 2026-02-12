#!/bin/bash

# Clear screen for focus
clear

# 1. Try to extract table name from config.yaml
if [ -f "config.yaml" ]; then
    TABLE_NAME=$(grep 'dynamo_table:' config.yaml | sed 's/.*dynamo_table:[[:space:]]*//' | tr -d '"'\'' ')
fi

# 2. If config failed, prompt the user for the name
if [ -z "$TABLE_NAME" ]; then
    read -p "Table name not found in config.yaml. Please enter table name: " TABLE_NAME
fi

# 3. HIGH-VISIBILITY WARNING
echo "--------------------------------------------------------"
echo "⚠️  WARNING: DATA DESTRUCTION IN PROGRESS"
echo "--------------------------------------------------------"
echo "You are about to DELETE and RECREATE the table: $TABLE_NAME"
echo "This will PERMANENTLY REMOVE all items and metadata."
echo "--------------------------------------------------------"
read -p "Are you absolutely sure you want to proceed? (yes/no): " CONFIRM

if [[ "$CONFIRM" != "yes" && "$CONFIRM" != "y" ]]; then
    echo "❌ Operation aborted by user."
    exit 1
fi

# 4. Teardown
echo "🗑️  Deleting table: $TABLE_NAME..."
aws dynamodb delete-table --table-name "$TABLE_NAME" > /dev/null 2>&1

echo "⏳ Waiting for deletion to complete..."
aws dynamodb wait table-not-exists --table-name "$TABLE_NAME"

# 5. Rebuild with new Indexing Strategy
echo "🏗️  Creating fresh table: $TABLE_NAME..."
aws dynamodb create-table \
    --table-name "$TABLE_NAME" \
    --attribute-definitions \
        AttributeName=PK,AttributeType=S \
        AttributeName=SK,AttributeType=S \
        AttributeName=GSI1PK,AttributeType=S \
        AttributeName=GSI1SK,AttributeType=S \
        AttributeName=ImageId,AttributeType=S \
        AttributeName=CaptureDate,AttributeType=S \
    --key-schema \
        AttributeName=PK,KeyType=HASH \
        AttributeName=SK,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --global-secondary-indexes \
        "[
            {
                \"IndexName\": \"GSI1\",
                \"KeySchema\": [
                    {\"AttributeName\":\"GSI1PK\",\"KeyType\":\"HASH\"},
                    {\"AttributeName\":\"GSI1SK\",\"KeyType\":\"RANGE\"}
                ],
                \"Projection\": {
                    \"ProjectionType\": \"INCLUDE\",
                    \"NonKeyAttributes\": [\"ImageName\", \"ImageId\", \"ThumbnailKey\", \"Timestamp\"]
                }
            },
            {
                \"IndexName\": \"ImageIdIndex\",
                \"KeySchema\": [
                    {\"AttributeName\":\"ImageId\",\"KeyType\":\"HASH\"},
                    {\"AttributeName\":\"CaptureDate\",\"KeyType\":\"RANGE\"}
                ],
                \"Projection\": {
                    \"ProjectionType\": \"ALL\"
                }
            }
        ]"

echo "⏳ Waiting for table to become ACTIVE..."
aws dynamodb wait table-exists --table-name "$TABLE_NAME"

echo "--------------------------------------------------------"
echo "✅ SUCCESS: $TABLE_NAME is fresh and ready."
echo "🚀 You can now run bulk-labeler.py to re-populate."
echo "--------------------------------------------------------"
