import os
import requests
import pandas as pd
from google.cloud import bigquery
from src.gcp.google_storage import get_storage_with_bucket


def fetch_courses(search_query, limit=50):
    """Fetch courses from Coursera GraphQL API based on search query."""
    endpoint = 'https://www.coursera.org/graphql-gateway?opname=Search'

    GRAPHQL_QUERY = '''query Search($requests: [Search_Request!]!) {
      SearchResult {
         search(requests: $requests) {
            elements {
            ... on Search_ProductHit {
               id
               name
               url
               imageUrl
               productType
               productDifficultyLevel
               productDuration
               avgProductRating
               numProductRatings
               skills
               partners
               isPartOfCourseraPlus
               isCourseFree
               isCreditEligible
               translatedName
               tagline
            }
            ... on Search_ArticleHit {
               id
               name
               url
               skill: skills
            }
            }
            pagination {
            cursor
            totalElements
            }
         }
      }
   }
   '''

    payload = {
        'operationName': 'Search',
        'variables': {
            'requests': [
              {
                  'entityType': 'PRODUCTS',
                  'query': search_query,
                  'limit': limit,
                  'disableRecommender': True,
                  'maxValuesPerFacet': 1000,
                  'facetFilters': [],
                  'cursor': '0',
              }
            ]
        },
        'query': GRAPHQL_QUERY,
    }

    headers = {
        'Content-Type': 'application/json',
    }

    resp = requests.post(endpoint, json=payload, headers=headers, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(
            f'Coursera API error {resp.status_code}: {resp.text}')

    try:
        data = resp.json()
    except ValueError as e:
        raise RuntimeError('Invalid JSON response from Coursera API') from e

    if 'errors' in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    # defensive access
    search_results = data.get('data', {}).get('SearchResult', {}).get('search')
    if search_results is None:
        raise RuntimeError('Unexpected Coursera response structure')

    print(f'Fetched {len(search_results)} results')
    return search_results


def _safe_get(d, k):
    """Safely get a value from a dictionary, returning None if the key is missing or if the input is not a dictionary."""
    return d.get(k) if isinstance(d, dict) else None


def transform_data(data):
    """Transform raw search results into a structured DataFrame."""
    rows = []
    for result in data:
        elements = result.get('elements') or []
        for e in elements:
            rows.append({
                'id': _safe_get(e, 'id'),
                'name': _safe_get(e, 'name'),
                'url': _safe_get(e, 'url'),
                'imageUrl': _safe_get(e, 'imageUrl'),
                'productType': _safe_get(e, 'productType'),
                'difficulty': _safe_get(e, 'productDifficultyLevel'),
                'duration': _safe_get(e, 'productDuration'),
                'avgRating': _safe_get(e, 'avgProductRating'),
                'numRatings': _safe_get(e, 'numProductRatings'),
                'skills': ','.join(e.get('skills') or []) if isinstance(e.get('skills'), list) else e.get('skills'),
                'partners': ','.join(e.get('partners') or []) if isinstance(e.get('partners'), list) else e.get('partners'),
                'isPartOfCourseraPlus': _safe_get(e, 'isPartOfCourseraPlus'),
                'isCourseFree': _safe_get(e, 'isCourseFree'),
                'isCreditEligible': _safe_get(e, 'isCreditEligible'),
                'tagline': _safe_get(e, 'tagline'),
                'translatedName': _safe_get(e, 'translatedName'),
            })

    df = pd.DataFrame(rows)
    print('Rows transformed:', len(df))
    return df


def upload_csv_to_gcs(df, credentials=None, bucket_name=None, project=None):
    """Save DataFrame to CSV (in /tmp) and upload to GCS. Accepts credentials."""
    if bucket_name is None:
        bucket_name = os.getenv('GCS_BUCKET_NAME', 'iam_pg')

    csv_path = os.path.join('/tmp', 'courses.csv')
    df.to_csv(csv_path, index=False)
    print('Saved CSV to', csv_path)

    destination_blob_name = f'coursera_exports/{os.path.basename(csv_path)}'

    # Initialize storage client with provided credentials
    _storage_client, bucket = get_storage_with_bucket(
        bucket_name, credentials=credentials, project=project
    )
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(csv_path)
    gcs_uri = f'gs://{bucket_name}/{destination_blob_name}'
    print('Uploaded to', gcs_uri)


def load_csv_to_bigquery(project, bucket_name, destination_blob_name, credentials=None):
    """Load CSV from GCS into BigQuery. Accepts credentials."""
    bq_client = bigquery.Client(project=project, credentials=credentials)
    dataset_id = 'university'
    table_id = 'coursera_courses'
    full_table_id = f'{project}.{dataset_id}.{table_id}'

    gcs_uri = f'gs://{bucket_name}/{destination_blob_name}'
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        # Added to handle multi-line strings in columns like 'tagline'
        allow_quoted_newlines=True,
        quote_character='"',
    )

    print(f'Starting BigQuery load job for project: {project}...')
    load_job = bq_client.load_table_from_uri(
        gcs_uri, full_table_id, job_config=job_config)
    load_job.result()  # wait for completion

    table = bq_client.get_table(full_table_id)
    print('Loaded', table.num_rows, 'rows into', full_table_id)
