import json
import os
import boto3
import time
from collections import Counter

# Core Model: Gemini 3 Flash / Free Tier
dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME')
INDEX_NAME = 'ImageIdIndex'
table = dynamodb.Table(TABLE_NAME)

def handler(event, context):
    try:
        # 1. READ FROM INDEX
        # We scan the GSI to get only projected image metadata, bypassing TAG# rows
        response = table.scan(IndexName=INDEX_NAME)
        items = response.get('Items', [])

        # Handle DynamoDB pagination (1MB limit)
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                IndexName=INDEX_NAME,
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        # 2. AGGREGATE DATA
        # We track by PK (filename) to reach the 266 count confirmed by CLI
        unique_files = set()
        cameras = Counter()
        labels_summary = Counter()
        shots_by_date = Counter()
        images_with_people = 0

        for item in items:
            pk = item.get('PK')
            if not pk or pk in unique_files:
                continue
            
            unique_files.add(pk)

            # Metadata Aggregation
            cam = item.get('CameraModel', 'Unknown')
            cameras[cam] += 1

            # Label Aggregation
            labels = item.get('Labels', [])
            if isinstance(labels, list):
                if "Person" in labels:
                    images_with_people += 1
                for label in labels:
                    labels_summary[label] += 1

            # Date Aggregation (using YYYY-MM-DD for the bar graph)
            # CaptureDate format verified: "2025-04-03T10:14:29..."
            c_date = item.get('CaptureDate')
            if c_date:
                day_string = c_date[:10]
                shots_by_date[day_string] += 1

        # 3. BUILD PAYLOAD
        stats = {
            "total_images": len(unique_files), # Should return 266
            "images_with_people": images_with_people,
            "top_cameras": dict(cameras.most_common(5)),
            "top_labels": dict(labels_summary.most_common(50)),
            "shots_by_date": dict(sorted(shots_by_date.items())),
            "last_updated": int(time.time())
        }

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
                # No CORS added per instructions
            },
            'body': json.dumps(stats)
        }

    except Exception as e:
        print(f"Stats Handler Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
