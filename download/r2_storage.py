import boto3
import os
import tempfile
from decouple import config
from botocore.exceptions import ClientError

def get_r2_client():
    account_id = config('R2_ACCOUNT_ID')
    access_key_id = config('R2_ACCESS_KEY_ID')
    secret_access_key = config('R2_SECRET_ACCESS_KEY')
    bucket_name = config('R2_BUCKET_NAME')
    
    endpoint_url = f'https://{account_id}.r2.cloudflarestorage.com'
    
    client = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name='auto'
    )
    
    return client, bucket_name

def clean_r2_directory(prefix):
    client, bucket_name = get_r2_client()
    
    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    try:
                        client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                    except Exception as e:
                        print(f'[error] Failed to delete {obj["Key"]}: {str(e)}')
    except Exception as e:
        print(f'[error] Failed to clean directory {prefix}: {str(e)}')

def upload_file_to_r2(local_path, r2_key):
    client, bucket_name = get_r2_client()
    
    try:
        client.upload_file(local_path, bucket_name, r2_key)
        return True
    except Exception as e:
        print(f'[error] Failed to upload {local_path} to {r2_key}: {str(e)}')
        return False

def delete_file_from_r2(r2_key):
    client, bucket_name = get_r2_client()
    
    try:
        client.delete_object(Bucket=bucket_name, Key=r2_key)
        return True
    except Exception as e:
        print(f'[error] Failed to delete {r2_key}: {str(e)}')
        return False

def file_exists_in_r2(r2_key):
    client, bucket_name = get_r2_client()
    
    try:
        client.head_object(Bucket=bucket_name, Key=r2_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise

def upload_string_to_r2(content, r2_key):
    client, bucket_name = get_r2_client()
    
    try:
        client.put_object(
            Bucket=bucket_name,
            Key=r2_key,
            Body=content.encode('utf-8')
        )
        return True
    except Exception as e:
        print(f'[error] Failed to upload string to {r2_key}: {str(e)}')
        return False

def download_file_from_r2(r2_key, local_path):
    client, bucket_name = get_r2_client()
    
    try:
        client.download_file(bucket_name, r2_key, local_path)
        return True
    except Exception as e:
        print(f'[error] Failed to download {r2_key} to {local_path}: {str(e)}')
        return False

def download_string_from_r2(r2_key):
    client, bucket_name = get_r2_client()
    
    try:
        response = client.get_object(Bucket=bucket_name, Key=r2_key)
        content = response['Body'].read().decode('utf-8')
        return content
    except Exception as e:
        print(f'[error] Failed to download string from {r2_key}: {str(e)}')
        return None

def has_files_in_r2_prefix(prefix):
    client, bucket_name = get_r2_client()
    
    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        
        for page in pages:
            if 'Contents' in page and len(page['Contents']) > 0:
                return True
        return False
    except Exception as e:
        print(f'[error] Failed to check files in prefix {prefix}: {str(e)}')
        return False

def list_files_in_r2_prefix(prefix):
    client, bucket_name = get_r2_client()
    files = []
    
    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    files.append(obj['Key'])
        return files
    except Exception as e:
        print(f'[error] Failed to list files in prefix {prefix}: {str(e)}')
        return []
