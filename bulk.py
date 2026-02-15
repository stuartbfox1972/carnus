import os, io, json, base64, uuid, time, subprocess, argparse
from concurrent.futures import ThreadPoolExecutor

import yaml
import rawpy
import brotli
import boto3
from PIL import Image
from pycognito import Cognito
from tqdm import tqdm
from botocore.exceptions import ClientError

def load_config(config_path="/opt/carnus/config.yaml"):
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

    id_res = idp.get_id(IdentityPoolId=aws['identity_pool_id'], Logins={provider: u_pool.id_token})
    identity_id = id_res['IdentityId']

    creds_res = idp.get_credentials_for_identity(IdentityId=identity_id, Logins={provider: u_pool.id_token})
    c = creds_res['Credentials']

    session = boto3.Session(
        aws_access_key_id=c['AccessKeyId'],
        aws_secret_access_key=c['SecretKey'],
        aws_session_token=c['SessionToken'],
        region_name=aws['region']
    )
    return session.client('s3'), identity_id, u_pool.id_claims['sub']

def upload_batch(s3, batch_data, user_sub, bucket_name):
    batch_id = uuid.uuid4().hex
    payload = {"user_id": user_sub, "images": batch_data}
    s3.put_object(
        Bucket=bucket_name,
        Key=f"incoming/{user_sub}/{batch_id}.json",
        Body=json.dumps(payload),
        ContentType="application/json"
    )

def get_exif_with_tool(file_path):
    try:
        cmd = ['exiftool', '-json', '-G', file_path]
        result = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return json.loads(result)[0]
    except Exception as e:
        return {"SourceFile": os.path.basename(file_path), "Error": str(e)}

def process_image(file_path, debug=False, force=False):
    fname = os.path.basename(file_path)
    if debug: print(f"[DEBUG] Processing: {fname} {'(FORCE)' if force else ''}")

    try:
        exif_dict = get_exif_with_tool(file_path)
        with rawpy.imread(file_path) as raw:
            try:
                thumb = raw.extract_thumb()
                img = Image.open(io.BytesIO(thumb.data)) if thumb.format == rawpy.ThumbFormat.JPEG else Image.fromarray(thumb.data)
            except:
                img = Image.fromarray(raw.postprocess(use_camera_wb=True, half_size=True, no_auto_bright=True))

            img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            final_thumb = buf.getvalue()

        return {
            "filename": fname,
            "force_reprocess": force,
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
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip", type=int, default=0)
    args = parser.parse_args()

    config = load_config()
    ingest_cfg = config.get('ingestion', {})
    debug_mode = args.debug or ingest_cfg.get('debug', False)
    force_mode = args.force or ingest_cfg.get('force_reprocess', False)

    if force_mode:
        print(f"\n{'!'*60}\n⚠️  NOTICE: Force Reprocess ENABLED.\nExisting data for these images will be overwritten.\n{'!'*60}")
        print("Starting in 5 seconds... (Ctrl+C to abort)")
        time.sleep(5)

    s3, _, user_sub = get_authenticated_session(config)
    raw_extensions = tuple(ext.lower() for ext in ingest_cfg.get('extensions', []))
    
    files = [os.path.join(r, f) for r, _, fs in os.walk(args.directory) for f in fs if f.lower().endswith(raw_extensions)]
    if args.skip > 0: files = files[args.skip:]

    current_batch, current_batch_bytes = [], 0
    workers = 1 if debug_mode else ingest_cfg.get('max_workers', 4)
    batch_size, max_bytes = ingest_cfg.get('batch_size', 20), 5 * 1024 * 1024

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for res in tqdm(executor.map(lambda f: process_image(f, debug_mode, force_mode), files), total=len(files)):
            if not res: continue
            current_batch.append(res)
            current_batch_bytes += len(json.dumps(res))

            if len(current_batch) >= batch_size or current_batch_bytes >= max_bytes:
                try:
                    upload_batch(s3, current_batch, user_sub, config['aws']['raw_source_s3_bucket'])
                except ClientError as e:
                    if e.response['Error']['Code'] in ['ExpiredToken', 'CredentialsError']:
                        s3, _, user_sub = get_authenticated_session(config)
                        upload_batch(s3, current_batch, user_sub, config['aws']['raw_source_s3_bucket'])
                    else: raise e
                current_batch, current_batch_bytes = [], 0

    if current_batch: upload_batch(s3, current_batch, user_sub, config['aws']['raw_source_s3_bucket'])
    if debug_mode: print(f"\n✨ Ingestion complete.")

if __name__ == "__main__":
    main()
