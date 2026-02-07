import os
import yaml
import boto3
import sys
from concurrent.futures import ThreadPoolExecutor
from processor import run_processor

# Load Universal Config
with open('config.yaml', 'r') as f:
    CFG = yaml.safe_load(f)

# Initialize AWS
s3 = boto3.client('s3')
rek = boto3.client('rekognition')
db = boto3.resource('dynamodb').Table(CFG['aws']['dynamo_table'])

def main(target_dir):
    if not os.path.isdir(target_dir):
        print(f"Error: {target_dir} is not a valid directory.")
        return

    exts = tuple(CFG['ingestion']['extensions'])
    files = [
        os.path.join(r, f) 
        for r, _, fs in os.walk(target_dir) 
        for f in fs if f.lower().endswith(exts)
    ]
    
    print(f"🚀 Starting bulk-labeler on {len(files)} files...")
    
    success_count = 0
    # Process in parallel
    with ThreadPoolExecutor(max_workers=CFG['ingestion']['max_workers']) as executor:
        # Create a mapping of future to filename so we can track progress
        future_to_file = {executor.submit(run_processor, p, CFG, s3, rek, db): p for p in files}
        
        for i, future in enumerate(future_to_file):
            file_path = future_to_file[future]
            filename = os.path.basename(file_path)
            try:
                result = future.result()
                if result:
                    success_count += 1
                    print(f"[{i+1}/{len(files)}] ✅ Success: {filename}")
                else:
                    print(f"[{i+1}/{len(files)}] ⚠️  Skipped (No thumb): {filename}")
            except Exception as e:
                print(f"[{i+1}/{len(files)}] ❌ Failed: {filename} | Error: {e}")

    print(f"\n🏁 Finished! Successfully processed {success_count}/{len(files)} images.")

if __name__ == "__main__":
    dir_to_scan = sys.argv[1] if len(sys.argv) > 1 else 'samples/'
    main(dir_to_scan)
