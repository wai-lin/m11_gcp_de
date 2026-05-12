from src.gcp.google_auth import get_auth
from src.pipeline_fn import fetch_courses, transform_data, load_csv_to_bigquery, upload_csv_to_gcs


def main():
    project = 'hs2026de'
    bucket_name = 'iam_pg'
    destination_blob_name = 'coursera_exports/courses.csv'

    creds = get_auth()

    # Step 1: Fetch data from Coursera API
    raw_data = fetch_courses(search_query='python', limit=100)

    # Step 2: Transform the data into a structured format
    df = transform_data(raw_data)

    # Step 3: Upload the transformed data as CSV to Google Cloud Storage
    upload_csv_to_gcs(df)

    # Step 4: Load the CSV from GCS into BigQuery
    load_csv_to_bigquery(project, bucket_name, destination_blob_name)


if __name__ == "__main__":
    main()
