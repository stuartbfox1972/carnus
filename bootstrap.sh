#!/bin/bash

# --- CONFIGURATION ---
VENV_NAME="carnus_env"
EXIFTOOL_VERSION="13.49"
EXIFTOOL_URL="https://github.com/exiftool/exiftool/archive/refs/tags/${EXIFTOOL_VERSION}.tar.gz"

echo "🛠️  Starting Carnus Repository Bootstrap (Layer-based Perl)..."

# 1. System Setup
sudo apt-get update -qq
sudo apt-get install -y build-essential wget python3-venv python3-pip zip awscli unzip -qq
mkdir -p src/lib

# 2. Python Environment
echo "🐍 Setting up Python Virtual Environment..."
python3 -m venv $VENV_NAME
source $VENV_NAME/bin/activate
pip install --upgrade pip --quiet
pip install pyyaml pygeohash boto3 --quiet
# Create requirements.txt for the SAM build process
echo -e "pyyaml\npygeohash\nboto3" > src/requirements.txt

# 3. Fetch ExifTool (Perl libraries only)
echo "📦 Fetching ExifTool..."
wget -q "$EXIFTOOL_URL" -O exiftool.tar.gz
tar -xzf exiftool.tar.gz
# We copy the 'exiftool' script and its 'lib' directory into src/
cp "exiftool-$EXIFTOOL_VERSION/exiftool" src/
cp -r "exiftool-$EXIFTOOL_VERSION/lib" src/

# 4. Cleanup & Permissions
echo "🧹 Cleaning up deployment package..."
rm -rf src/lib/Image/ExifTool/html
find src/lib -name "*.pod" -delete
rm -rf "exiftool-$EXIFTOOL_VERSION" exiftool.tar.gz
chmod +x src/exiftool

# 5. Interactive Configuration & Injection
echo -e "\n📝 --- Configuration Setup ---"
RAND_ID=$(head /dev/urandom | tr -dc 'a-z0-9' | head -c 4)

read -p "Enter DynamoDB Table Name [Default: Carnus-Metadata-$RAND_ID]: " USER_TABLE
DDB_TABLE=${USER_TABLE:-"Carnus-Metadata-$RAND_ID"}

read -p "Enter Raw Upload S3 Bucket [Default: carnus-raw-$RAND_ID]: " USER_RAW
RAW_BUCKET=${USER_RAW:-"carnus-raw-$RAND_ID"}

# Sync values to config.yaml and template.yaml
touch config.yaml template.yaml
sed -i "s|dynamo_table: .*|dynamo_table: \"$DDB_TABLE\"|" config.yaml
sed -i "s|raw_source_s3_bucket: .*|raw_source_s3_bucket: \"$RAW_BUCKET\"|" config.yaml
sed -i "s|Default: \"Carnus-.*\"|Default: \"$DDB_TABLE\"|" template.yaml
sed -i "s|Default: \"carnus-raw-.*\"|Default: \"$RAW_BUCKET\"|" template.yaml

echo "------------------------------------------------"
echo "✅ Bootstrap Complete! Ready for SAM deploy."
echo "------------------------------------------------"
