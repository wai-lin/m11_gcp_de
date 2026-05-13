def get_storage_bucket(credential=None, bucket_name=None):
    """Initialize Google Cloud Storage client and get bucket reference."""
    from google.cloud import storage

    if bucket_name is None:
        import os
        bucket_name = os.getenv("GCP_BUCKET_NAME")

    storage_client = storage.Client(credentials=credential)
    bucket = storage_client.bucket(bucket_name)
    return storage_client, bucket
