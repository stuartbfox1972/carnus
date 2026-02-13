import os
import io
import json
import base64
import uuid
import yaml
import rawpy
import brotli
import boto3
import argparse
import subprocess
from PIL import Image
from pycognito import Cognito
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

def load_config(config_path="config.yaml"):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_authenticated_session(config):
    aws = config['aws']
    u_pool = Cognito(
        aws['user_pool_id'], 
        aws['client_id'], 
        username=aws['cognito_username']
    )
    u_pool.authenticate(password=aws['cognito_password'])
    
    idp = boto3.client('cognito-identity', region_name=aws['region'])
    provider = f"cognito-idp.{aws['region']}.amazonaws.com/{aws['user_pool_id']}"
    
    id_res = idp.get_id(
        IdentityPoolId=aws['identity_pool_id'], 
        Logins={provider: u_pool.id_token}
    )
    identity_id = id_res['IdentityId']
    
    creds_res = idp.get_credentials_for_identity(
        IdentityId=identity_id, 
        Logins={provider: u_pool.id_token}
    )
    c = creds_res['Credentials']

    session = boto3.Session(
        aws_access_key_id=c['AccessKeyId'],
        aws_secret_access_key=c['SecretKey'],
        aws_session_token=c['SessionToken'],
        region_name=aws['region']
    )
    
    return session.client('s3'), identity_id, u_pool.id_claims['sub']

def upload_batch(s3, batch_data, identity_id, user_sub, bucket_name):
    batch_id = uuid.uuid4().hex
    payload = {
        "user_id": user_sub,
        "images": batch_data
    }
    s3.put_object(
        Bucket=bucket_name,
        Key=f"incoming/{identity_id}/{batch_id}.json",
        Body=json.dumps(payload),
        ContentType="application/json"
    )

def get_exif_with_tool(file_path):
    """Deep metadata extraction via ExifTool."""
    try:
        # -G: Group names (EXIF, MakerNotes, etc)
        # -json: Standard output for Python parsing
        cmd = ['exiftool', '-json', '-G', file_path]
        result = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return json.loads(result)[0]
    except Exception as e:
        return {"SourceFile": os.path.basename(file_path), "Error": str(e)}

def process_image(file_path, debug=False):
    fname = os.path.basename(file_path)
    if debug:
        print(f"[DEBUG] Processing: {fname}")
        
    try:
        # 1. FULL METADATA (ExifTool)
        exif_dict = get_exif_with_tool(file_path)

        # 2. THUMBNAIL (rawpy)
        with rawpy.imread(file_path) as raw:
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    img = Image.open(io.BytesIO(thumb.data))
                else:
                    img = Image.fromarray(thumb.data)
            except Exception:
                # Fallback: Half-size render for preview
                thumb_bytes = raw.postprocess(use_camera_wb=True, half_size=True, no_auto_bright=True)
                img = Image.fromarray(thumb_bytes)
            
            img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            final_thumb = buf.getvalue()

        if debug:
            print(f"  └─ [DEBUG] Success: {len(exif_dict)} metadata tags extracted.")

        return {
            "filename": fname,
            "exif": base64.b64encode(brotli.compress(json.dumps(exif_dict).encode())).decode(),
            "thumb": base64.b64encode(brotli.compress(final_thumb)).decode()
        }
    except Exception as e:
        print(f"❌ Error on {fname}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default="./")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    config = load_config()
    ingest_cfg = config.get('ingestion', {})
    debug_mode = args.debug or ingest_cfg.get('debug', False)
    
    if debug_mode:
        print(f"--- Carnus RAW Ingestor (ExifTool Mode) ---")
        print(f"🔐 Authenticating {config['aws']['cognito_username']}...")
        
    s3, identity_id, user_sub = get_authenticated_session(config)
    
    raw_extensions = tuple(ext.lower() for ext in ingest_cfg.get('extensions', []))
    files = [os.path.join(args.directory, f) for f in os.listdir(args.directory) 
             if f.lower().endswith(raw_extensions)]

    if debug_mode:
        print(f"[DEBUG] Found {len(files)} files. Using {ingest_cfg.get('batch_size', 20)} per batch.")

    current_batch = []
    workers = 1 if debug_mode else ingest_cfg.get('max_workers', 4)
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(tqdm(executor.map(lambda f: process_image(f, debug_mode), files), total=len(files)))
        
        for res in results:
            if res:
                current_batch.append(res)
            if len(current_batch) >= ingest_cfg.get('batch_size', 20):
                upload_batch(s3, current_batch, identity_id, user_sub, config['aws']['raw_source_s3_bucket'])
                current_batch = []

    if current_batch:
        upload_batch(s3, current_batch, identity_id, user_sub, config['aws']['raw_source_s3_bucket'])

    if debug_mode:
        print(f"\n✨ Ingestion complete.")

if __name__ == "__main__":
    main()
