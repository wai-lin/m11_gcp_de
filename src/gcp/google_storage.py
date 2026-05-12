from google.cloud import storage


def get_storage_with_bucket(bucket_name):
    """Initialize Google Cloud Storage client and get bucket reference."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    return storage_client, bucket
