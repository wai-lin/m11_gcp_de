def get_bigquery_client(credentials=None, project=None):
    """Initialize BigQuery client with optional credentials and project."""
    from google.cloud import bigquery

    if project is None:
        import os
        project = os.getenv("GCP_PROJECT_ID")

    bigquery_client = bigquery.Client(credentials=credentials, project=project)
    return bigquery_client
