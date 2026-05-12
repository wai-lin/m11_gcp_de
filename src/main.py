import os
import json
import logging

from src.gcp.google_auth import get_auth
from src.pipeline_fn import (
    fetch_courses,
    transform_data,
    load_csv_to_bigquery,
    upload_csv_to_gcs,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def main():
    project = os.getenv('GCP_PROJECT_ID', 'hs2026de')
    bucket_name = os.getenv('GCS_BUCKET_NAME', 'iam_pg')
    destination_blob_name = os.getenv('GCS_DESTINATION_BLOB', 'coursera_exports/courses.csv')

    creds, detected_project = get_auth()
    if detected_project:
        project = detected_project

    # Step 1: Fetch data from Coursera API (provide a search query)
    search_query = os.getenv('SEARCH_QUERY', 'python')
    raw_data = fetch_courses(search_query=search_query, limit=int(os.getenv('SEARCH_LIMIT', '100')))

    # Step 2: Transform the data into a structured format
    df = transform_data(raw_data)

    # Step 3: Upload the transformed data as CSV to Google Cloud Storage
    upload_csv_to_gcs(df, credentials=creds, bucket_name=bucket_name, project=project)

    # Step 4: Load the CSV from GCS into BigQuery
    load_csv_to_bigquery(project, bucket_name, destination_blob_name, credentials=creds)


def coursera_pipeline(request):
    """HTTP Cloud Function entrypoint.

    Accepts optional JSON body or query parameters:
      - search_query or q: search term for Coursera
      - search_limit: integer limit

    Returns JSON response and HTTP status code.
    """
    try:
        creds, detected_project = get_auth()
        project = os.getenv('GCP_PROJECT_ID', detected_project or 'hs2026de')
        bucket_name = os.getenv('GCS_BUCKET_NAME', 'iam_pg')
        destination_blob_name = os.getenv('GCS_DESTINATION_BLOB', 'coursera_exports/courses.csv')

        # extract params from request
        search_query = None
        search_limit = None
        if request is not None:
            try:
                req_json = request.get_json(silent=True)
            except Exception:
                req_json = None

            if req_json and isinstance(req_json, dict):
                search_query = req_json.get('search_query') or req_json.get('q')
                search_limit = req_json.get('search_limit')

            # querystring overrides
            args = getattr(request, 'args', None)
            if args:
                search_query = search_query or args.get('search_query') or args.get('q')
                search_limit = search_limit or args.get('search_limit')

        search_query = search_query or os.getenv('SEARCH_QUERY', 'python')
        search_limit = int(search_limit or os.getenv('SEARCH_LIMIT', '100'))

        logger.info('Starting pipeline: query=%s project=%s', search_query, project)

        raw_data = fetch_courses(search_query=search_query, limit=search_limit)
        df = transform_data(raw_data)
        upload_csv_to_gcs(df, credentials=creds, bucket_name=bucket_name, project=project)
        load_csv_to_bigquery(project, bucket_name, destination_blob_name, credentials=creds)

        return (json.dumps({'status': 'success', 'message': 'Pipeline completed'}), 200, {'Content-Type': 'application/json'})
    except Exception as e:
        logger.exception('Pipeline failed')
        return (json.dumps({'status': 'error', 'message': str(e)}), 500, {'Content-Type': 'application/json'})


if __name__ == "__main__":
    main()
