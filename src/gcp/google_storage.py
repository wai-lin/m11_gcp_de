from google.cloud import storage
import os


def get_storage_with_bucket(bucket_name, credentials=None, project=None):
    """Initialize Google Cloud Storage client and get bucket reference.

    Accepts optional `credentials` (google.auth credentials) and `project`.
    """
    if project is None:
        project = os.getenv("GCP_PROJECT_ID")

    storage_client = storage.Client(credentials=credentials, project=project)
    bucket = storage_client.bucket(bucket_name)
    return storage_client, bucket
