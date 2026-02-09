#!/bin/bash

# --- CONFIGURATION ---
VENV_NAME="carnus_env"
EXIFTOOL_VERSION="13.49"
EXIFTOOL_URL="https://github.com/exiftool/exiftool/archive/refs/tags/${EXIFTOOL_VERSION}.tar.gz"

echo "🛠️  Starting Carnus Repository Bootstrap (v${EXIFTOOL_VERSION})..."

# 1. System Setup
sudo apt-get update -qq
sudo apt-get install -y build-essential wget python3-venv python3-pip zip awscli unzip -qq
mkdir -p src/

# 2. Python Environment Setup
if [ ! -f src/requirements.txt ]; then
    echo "❌ Error: src/requirements.txt not found. It must be in Git."
    exit 1
fi

echo "🐍 Setting up local Python Virtual Environment..."
python3 -m venv $VENV_NAME
source $VENV_NAME/bin/activate
pip install --upgrade pip --quiet

echo "📦 Installing dependencies from Git-managed src/requirements.txt..."
pip install -r src/requirements.txt --quiet

# 3. Fetch ExifTool
echo "📦 Fetching ExifTool v${EXIFTOOL_VERSION}..."
wget -q "$EXIFTOOL_URL" -O exiftool.tar.gz
tar -xzf exiftool.tar.gz

# Move binary and lib into src/ for the SAM build to include them
cp "exiftool-$EXIFTOOL_VERSION/exiftool" src/
cp -r "exiftool-$EXIFTOOL_VERSION/lib" src/

# 4. Cleanup & Permissions
echo "🧹 Cleaning up ExifTool source..."
rm -rf src/lib/Image/ExifTool/html
find src/lib -name "*.pod" -delete
rm -rf "exiftool-$EXIFTOOL_VERSION" exiftool.tar.gz
chmod +x src/exiftool

# 5. Interactive Configuration & Randomization
echo -e "\n📝 --- Configuration Setup ---"

# Generate a 5-character random string (lowercase alphanumeric)
RAND_ID=$(head /dev/urandom | tr -dc 'a-z0-9' | head -c 5)
ENV_NAME="Carnus-${RAND_ID}"
echo "🎲 Generated unique environment: $ENV_NAME"

read -p "Enter DynamoDB Table Name [Default: carnus-metadata]: " USER_TABLE
DDB_BASE=${USER_TABLE:-"carnus-metadata"}
DDB_TABLE="${DDB_BASE}-${RAND_ID}"

read -p "Enter Raw S3 Bucket [Default: carnus-raw]: " USER_RAW
RAW_BASE=${USER_RAW:-"carnus-raw"}
RAW_BUCKET="${RAW_BASE}-${RAND_ID}"

read -p "Enter Thumbnail S3 Bucket [Default: carnus-thumbs]: " USER_THUMBS
THUMB_BASE=${USER_THUMBS:-"carnus-thumbs"}
THUMB_BUCKET="${THUMB_BASE}-${RAND_ID}"

echo "📍 Finalized Names:"
echo "   Env:    $ENV_NAME"
echo "   Table:  $DDB_TABLE"
echo "   Raw:    $RAW_BUCKET"
echo "   Thumbs: $THUMB_BUCKET"

# 6. Generate nested config.yaml
cat <<EOF > config.yaml
aws:
  region: "us-east-1"
  environment_name: "$ENV_NAME"
  dynamo_table: "$DDB_TABLE"
  raw_source_s3_bucket: "$RAW_BUCKET"
  thumbnail_s3_bucket: "$THUMB_BUCKET"

ingestion:
  max_workers: 16
  min_confidence: 75
  max_labels: 15
  extensions: [".cr2", ".cr3", ".arw", ".nef", ".dng"]
  debug: true
  force_reprocess: false

lambda_settings:
  exiftool_path: "./src/exiftool"
  cleanup_tmp: true
EOF

# 7. Substitute into template.yaml
echo "📝 Updating template.yaml with unique parameters..."
if [ -f "template-template.yaml" ]; then
    cp template-template.yaml template.yaml
    
    # Use sed to update the Default values for Environment, Table, and Buckets
    sed -i "/EnvironmentName:/,/Default:/ s/Default: .*/Default: \"$ENV_NAME\"/" template.yaml
    sed -i "/TableName:/,/Default:/ s/Default: .*/Default: \"$DDB_TABLE\"/" template.yaml
    sed -i "/RawBucketName:/,/Default:/ s/Default: .*/Default: \"$RAW_BUCKET\"/" template.yaml
    sed -i "/ThumbBucketName:/,/Default:/ s/Default: .*/Default: \"$THUMB_BUCKET\"/" template.yaml
    
    echo "✅ template.yaml updated with unique IDs."
else
    echo "⚠️  Warning: template.yaml not found."
fi

echo "------------------------------------------------"
echo "✅ Bootstrap Complete for v${EXIFTOOL_VERSION}!"
echo "💡 To deploy, run: sam build && sam deploy --stack-name $ENV_NAME"
echo "------------------------------------------------"
