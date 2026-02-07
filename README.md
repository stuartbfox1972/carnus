# 📸 Carnus: Serverless Photographic Intelligence 

**Carnus** is a high-performance metadata extraction and AI-labeling engine. It is designed for photographers and archivists who need to transform massive volumes of RAW imagery into a searchable, intelligent database without the overhead of traditional asset management software. 

!$$Carnus Architecture$$(architecture.png) 

--- 

## 🎯 Project Intent 

Standard photo management tools often require expensive subscriptions or local database locks. Carnus was built to: 
* **Decouple Metadata:** Store technical EXIF and AI-generated tags in a fast, queryable NoSQL database (DynamoDB) independent of your files. 
* **Automate Discovery:** Utilize Amazon Rekognition to automatically tag images with descriptive labels (e.g., Mountain, Sunset, Portrait). 
* **Handle RAW Workflows:** Native handling of .cr2, .cr3, .arw, .nef, and .dng via a bundled ExifTool binary within the Lambda environment. 
* **Scale to Zero:** Utilizing a serverless architecture ensures you only pay when photos are being processed. 

--- 

## 🏗️ Technical Specification 

### The Stack 
* **Language:** Python 3.12 
* **Infrastructure:** AWS SAM (Serverless Application Model) 
* **Compute:** AWS Lambda (configured for high-concurrency processing) 
* **Storage:** Amazon S3 (Raw Source & Generated Thumbnails) 
* **Database:** Amazon DynamoDB (On-Demand / Pay-per-request) 
* **Intelligence:** Amazon Rekognition (Computer Vision) 
* **Metadata Engine:** ExifTool 13.49 (Bundled Perl-based binary) 

### Project Structure 
carnus/ 
├── src/                 # Lambda Source Code (CodeUri) 
│   ├── lambda_function.py 
│   ├── processor.py     # Core logic shared by Cloud/Local 
│   ├── requirements.txt # Lambda-only dependencies 
│   └── exiftool         # Bundled binary for AWS execution 
├── bin/                 # Local binaries (installed via bootstrapper) 
├── bootstrap.sh         # One-click environment & resource setup 
├── template.yaml        # SAM Infrastructure-as-Code 
├── config.yaml          # Local configuration & resource mapping 
├── bulk-labeler.py      # High-speed local ingestion script 
└── test-event.json      # Mock S3 event for local debugging 

--- 

## 🚀 Getting Started 

### 1. Initialize the Environment 
Run the bootstrapper to install system dependencies (SAM CLI, Python venv, ExifTool) and configure your AWS resource names. 

chmod +x bootstrap.sh 
./bootstrap.sh 
source carnus_env/bin/activate 

*Note: The script will interactively ask you for your S3 Bucket and DynamoDB Table names, then automatically sync them to your configuration files.* 

### 2. Cloud Deployment 
Once your environment is initialized and your AWS CLI is configured, deploy the stack: 

sam build 
sam deploy 

### 3. Local Testing 
Test your Lambda logic locally using the mock event: 

sam local invoke ProcessorFunction -e test-event.json 

--- 

## 🔧 Workflow & Usage 

### High-Speed Ingestion 
To process local archives and sync them to your Carnus cloud infrastructure: 

python bulk-labeler.py /path/to/my/raw/photos/ 

### Configuration (config.yaml) 
* **aws**: Defines the target region and resource names. 
* **ingestion**: Control AI confidence thresholds and file extension filters. 
* **geospatial**: Configure Geohash precision (default 9) for map-based queries. 

--- 

## 📜 License 
This project is licensed under the **GPLv3**. You are free to modify and distribute the code, provided that all derivatives remain open-source under the same license. 

