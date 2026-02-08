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
    Robustly finds the service account email using official google-auth and metadata server.
    """
    try:
        # 1. Check Environment Variable (Highest priority)
        env_email = os.getenv("SERVICE_ACCOUNT_EMAIL")
        if env_email: return env_email

        # 2. Try credentials object
        import google.auth
        credentials, project = google.auth.default()
        
        if hasattr(credentials, 'service_account_email') and credentials.service_account_email:
            # If it's literally 'default', we must fetch the real one from metadata
            if credentials.service_account_email != "default":
                return credentials.service_account_email
        
        # 3. Dedicated Metadata Server call (Source of truth in Cloud Run)
        import httpx
        meta_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
        resp = httpx.get(meta_url, headers={"Metadata-Flavor": "Google"}, timeout=2.0)
        if resp.status_code == 200:
            email = resp.text.strip()
            print(f"DEBUG: Metadata Server returned email: {email}")
            return email
            
    except Exception as e:
        print(f"DEBUG: Failed to discover service account email: {e}")
        
    return None

class IAMSigner:
    """
    Ultimate Signer for Cloud Run.
    Bypasses library checks and calls the IAM signBlob REST API directly.
    """
    def __init__(self, credentials, email):
        self.credentials = credentials
        self.email = email

    def sign_bytes(self, bytes_to_sign):
        import base64
        import json
        import httpx
        from google.auth.transport.requests import Request
        
        # 1. Ensure we have a fresh token
        if not self.credentials.valid:
            self.credentials.refresh(Request())
        
        # 2. Call the Google IAM signBlob API
        url = f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{self.email}:signBlob"
        headers = {
            "Authorization": f"Bearer {self.credentials.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "payload": base64.b64encode(bytes_to_sign).decode("utf-8")
        }
        
        print(f"DEBUG: Requesting IAM Signature from {url}")
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        
        if resp.status_code != 200:
            raise Exception(f"IAM REST signBlob failed ({resp.status_code}): {resp.text}")
            
        # 3. Decode the returned signature
        return base64.b64decode(resp.json()["signedBlob"])

def get_signed_url(blob_name: str, method: str = "GET", expiration_minutes: int = 15, content_type: str = None) -> str:
    """
    Generates a signed URL for a specific blob.
    method: 'GET' for read, 'PUT' for upload.
    """
    client = _get_storage_client()
    if not client:
        return f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}?mock_sig=true"

    try:
        bucket = _get_bucket()
        blob = bucket.blob(blob_name)
        
        service_account_email = _get_service_account_email()
        print(f"DEBUG: Generating Signed URL for {blob_name} using Identity: {service_account_email}")

        # In Cloud Run, credentials don't have a private key.
        # We wrap them in a signer that uses the IAM API.
        if service_account_email and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                import google.auth
                credentials, project = google.auth.default()
                signer_creds = IAMSigner(credentials, service_account_email)
                
                return blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.timedelta(minutes=expiration_minutes),
                    method=method,
                    content_type=content_type,
                    service_account_email=service_account_email,
                    credentials=signer_creds
                )
            except Exception as iam_e:
                print(f"DEBUG: IAM Signer creation failed: {iam_e}. Falling back to default.")

        # Default fallback (works locally with JSON key)
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
