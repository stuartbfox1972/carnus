import os
import sys
import yaml
import boto3
import concurrent.futures
from tqdm import tqdm
from src.processor.processor import process_image

def main():
    # 1. Capture CLI Argument
    if len(sys.argv) < 2:
        print("❌ Usage: python bulk-labeler.py <photo_directory_path>")
        sys.exit(1)

    photo_dir = sys.argv[1]
    if not os.path.isdir(photo_dir):
        print(f"❌ Error: {photo_dir} is not a valid directory.")
        sys.exit(1)

    # 2. Load Configuration
    with open("config.yaml", 'r') as f:
        cfg = yaml.safe_load(f)

    # 3. Map Settings to Processor Signature
    settings = {
        'force_reprocess': cfg['ingestion']['force_reprocess'],
        'debug': cfg['ingestion']['debug'],
        'exiftool_path': cfg['lambda_settings']['exiftool_path'],
        'assets_bucket': cfg['aws']['thumbnail_s3_bucket'],
        'raw_bucket': cfg['aws']['raw_source_s3_bucket'],
        'max_labels': cfg['ingestion'].get('max_labels', 15),
        'min_confidence': cfg['ingestion'].get('min_confidence', 75)
    }

    # 4. Initialize AWS Clients
    session = boto3.Session(region_name=cfg['aws']['region'])
    s3 = session.client('s3')
    rek = session.client('rekognition')
    table = session.resource('dynamodb').Table(cfg['aws']['dynamo_table'])

    # 5. Gather Files Recursively (os.walk)
    exts = tuple(cfg['ingestion']['extensions'])
    files = []

    print(f"🔍 Searching for photos in {photo_dir}...")
    for root, _, filenames in os.walk(photo_dir):
        for f in filenames:
            if f.lower().endswith(exts):
                files.append(os.path.join(root, f))

    if not files:
        print(f"ℹ️ No matching files found in {photo_dir} or subfolders.")
        return

    print(f"🚀 Found {len(files)} files. Starting processing...")
    print(f"⚙️  Settings: Force={settings['force_reprocess']}, Debug={settings['debug']}\n")

    # 6. Parallel Execution via ThreadPool with Progress Bar
    max_workers = cfg['ingestion'].get('max_workers', 10)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(process_image, f, settings, s3, rek, table): f for f in files}
        
        # tqdm context manager for the progress bar
        # total=len(files) gives us the "0/266" counter
        with tqdm(total=len(files), desc="Processing Photos", unit="img") as pbar:
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result() # Check for exceptions in threads
                except Exception as e:
                    filename = futures[future]
                    print(f"\n❌ Error processing {filename}: {e}")
                
                pbar.update(1) # Advance the counter by 1

    print(f"\n✅ Finished processing {len(files)} files.")

if __name__ == "__main__":
    main()
