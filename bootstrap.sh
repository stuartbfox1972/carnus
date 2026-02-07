#!/bin/bash

# --- CONFIGURATION ---
VENV_NAME="carnus_env"
EXIFTOOL_VERSION="13.49"
EXIFTOOL_URL="https://cytranet-dal.dl.sourceforge.net/project/exiftool/Image-ExifTool-${EXIFTOOL_VERSION}.tar.gz"

echo "🛠️  Starting Carnus Repository Bootstrap..."

# Function to install AWS SAM CLI
install_sam_cli() {
    if command -v sam &> /dev/null; then
        echo "✅ AWS SAM CLI is already installed."
        return
    fi
    echo "📥 AWS SAM CLI not found. Starting installation..."
    ARCH=$(uname -m)
    if [ "$ARCH" == "x86_64" ]; then
        SAM_URL="https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip"
    elif [ "$ARCH" == "aarch64" ]; then
        SAM_URL="https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-arm64.zip"
    else
        echo "❌ Unsupported architecture: $ARCH. Please install SAM CLI manually."
        return
    fi
    wget -q "$SAM_URL" -O sam-installer.zip
    unzip -q sam-installer.zip -d sam-installation
    sudo ./sam-installation/install
    rm -rf sam-installer.zip sam-installation
}

# 1. System Setup
sudo apt-get update -qq
sudo apt-get install -y build-essential wget python3-venv python3-pip zip awscli unzip -qq
mkdir -p src bin
install_sam_cli

# 2. Python Environment
python3 -m venv $VENV_NAME
source $VENV_NAME/bin/activate
pip install --upgrade pip --quiet
pip install pyyaml pygeohash boto3 --quiet
echo -e "pyyaml\npygeohash" > src/requirements.txt

# 3. Fetch ExifTool
if [ ! -f "bin/exiftool" ]; then
    wget -q "$EXIFTOOL_URL" -O exiftool.tar.gz
    tar -xzf exiftool.tar.gz
    cp "Image-ExifTool-$EXIFTOOL_VERSION/exiftool" bin/
    cp -r "Image-ExifTool-$EXIFTOOL_VERSION/lib" bin/
    cp "Image-ExifTool-$EXIFTOOL_VERSION/exiftool" src/
    cp -r "Image-ExifTool-$EXIFTOOL_VERSION/lib" src/
    rm -rf src/lib/Image/ExifTool/html
    find src/lib -name "*.pod" -delete
    rm -rf "Image-ExifTool-$EXIFTOOL_VERSION" exiftool.tar.gz
    chmod +x bin/exiftool src/exiftool
fi

# 4. Interactive Configuration
echo -e "\n📝 --- Configuration Setup ---"
RAND_ID=$(head /dev/urandom | tr -dc 'a-z0-9' | head -c 4)

read -p "Enter DynamoDB Table Name [Default: Carnus-$RAND_ID]: " USER_TABLE
DDB_TABLE=${USER_TABLE:-"Carnus-$RAND_ID"}

read -p "Enter Raw Upload S3 Bucket [Default: carnus-raw-$RAND_ID]: " USER_RAW
RAW_BUCKET=${USER_RAW:-"carnus-raw-$RAND_ID"}

read -p "Enter Thumbnail S3 Bucket [Default: carnus-thumbs-$RAND_ID]: " USER_THUMBS
THUMB_BUCKET=${USER_THUMBS:-"carnus-thumbs-$RAND_ID"}

# 5. Injection Logic (Syncing config.yaml and template.yaml)
sed -i "s|dynamo_table: .*|dynamo_table: \"$DDB_TABLE\"|" config.yaml
sed -i "s|raw_source_s3_bucket: .*|raw_source_s3_bucket: \"$RAW_BUCKET\"|" config.yaml
sed -i "s|thumbnail_s3_bucket: .*|thumbnail_s3_bucket: \"$THUMB_BUCKET\"|" config.yaml

sed -i "s|Default: \"Carnus-.*\"|Default: \"$DDB_TABLE\"|" template.yaml
sed -i "s|Default: \"carnus-raw-.*\"|Default: \"$RAW_BUCKET\"|" template.yaml
sed -i "s|Default: \"carnus-thumbs-.*\"|Default: \"$THUMB_BUCKET\"|" template.yaml

echo "------------------------------------------------"
echo "✅ Bootstrap Complete! Resource Names Synced."
echo "🚀 Run: sam build && sam deploy"
echo "------------------------------------------------"
