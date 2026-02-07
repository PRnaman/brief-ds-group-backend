import os
import datetime
from google.cloud import storage
from app.core.exceptions import GCSOperationError

# Use a default bucket name if not specified in env
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "mediaflow-bucket")

# Global client variable (initialized lazily)
_storage_client = None

def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        print(f"DEBUG: Attempting to init GCS client with creds: {cred_path}")
        try:
            _storage_client = storage.Client()
            print("DEBUG: GCS Client initialized successfully.")
        except Exception as e:
            # Fallback for local dev without creds
            print(f"ERROR: GCS Client failed to initialize: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    return _storage_client

def _get_bucket():
    client = _get_storage_client()
    if not client:
        raise GCSOperationError("GCS Client not initialized. Check credentials.")
    try:
        return client.bucket(BUCKET_NAME)
    except Exception as e:
        raise GCSOperationError(f"Failed to access bucket {BUCKET_NAME}: {str(e)}")

def upload_file(local_path: str, blob_name: str, content_type: str = None) -> str:
    """
    Uploads a file to the bucket.
    Returns the public URL (or gsutil URI) of the uploaded blob.
    """
    try:
        bucket = _get_bucket()
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_path, content_type=content_type)
        return blob.public_url
    except Exception as e:
        raise GCSOperationError(f"Upload failed: {str(e)}")

def download_file(blob_name: str, local_path: str):
    """Downloads a blob to a local file using the DEFAULT bucket."""
    try:
        bucket = _get_bucket()
        blob = bucket.blob(blob_name)
        # Ensure directory exists
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)
    except Exception as e:
        raise GCSOperationError(f"Download failed: {str(e)}")

def download_from_bucket(bucket_name: str, blob_name: str, local_path: str):
    """Downloads a blob to a local file from a SPECIFIC bucket."""
    try:
        client = _get_storage_client()
        if not client:
            raise GCSOperationError("GCS Client not initialized.")
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)
    except Exception as e:
        raise GCSOperationError(f"Download from {bucket_name} failed: {str(e)}")

def read_file(blob_name: str) -> bytes:
    """Reads a blob's content directly into memory."""
    try:
        bucket = _get_bucket()
        blob = bucket.blob(blob_name)
        return blob.download_as_bytes()
    except Exception as e:
        raise GCSOperationError(f"Read file failed: {str(e)}")

def _get_service_account_email():
    """
    Robustly finds the service account email.
    Works in Local, Cloud Run, and with explicit configs.
    """
    client = _get_storage_client()
    if not client:
        return None
        
    # 1. Try credentials object directly
    try:
        if hasattr(client.get_service_account_email, "__call__"):
            email = client.get_service_account_email()
            if email: return email
    except:
        pass
        
    # 2. Check Environment Variable (User can set this as a backup)
    env_email = os.getenv("SERVICE_ACCOUNT_EMAIL")
    if env_email: return env_email
    
    # 3. Check Metadata Server (Internal GCP logic for Cloud Run)
    import httpx
    try:
        # Standard GCP metadata URL for service account email
        meta_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
        resp = httpx.get(meta_url, headers={"Metadata-Flavor": "Google"}, timeout=1.0)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
        
    return None

def get_signed_url(blob_name: str, method: str = "GET", expiration_minutes: int = 15, content_type: str = None) -> str:
    """
    Generates a signed URL for a specific blob.
    method: 'GET' for read, 'PUT' for upload.
    """
    client = _get_storage_client()
    if not client:
         # Mock for local dev if no client
        return f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}?mock_sig=true"

    try:
        bucket = _get_bucket()
        blob = bucket.blob(blob_name)
        
        # In Cloud Run, credentials often don't have a private key.
        # We use the Service Account Email to delegate signing to GCS internal IAM service.
        service_account_email = _get_service_account_email()

        return blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiration_minutes),
            method=method,
            content_type=content_type,
            service_account_email=service_account_email
        )
    except Exception as e:
        raise GCSOperationError(f"Signed URL generation failed: {str(e)}")

def list_blobs(prefix: str):
    """Lists all blobs with the given prefix."""
    try:
        bucket = _get_bucket()
        return list(bucket.list_blobs(prefix=prefix))
    except Exception as e:
        raise GCSOperationError(f"List blobs failed: {str(e)}")

def delete_blob(blob_name: str):
    """Deletes a blob."""
    try:
        bucket = _get_bucket()
        blob = bucket.blob(blob_name)
        blob.delete()
    except Exception as e:
        raise GCSOperationError(f"Delete blob failed: {str(e)}")
