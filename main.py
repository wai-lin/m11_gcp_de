import os

from dotenv import load_dotenv
from src.pipeline.etl import run_etl


load_dotenv()


def main():
    """
    Main entry point for Cloud Run Job.
    Fetches TikTok user info and posts, uploads to GCS, and loads into BigQuery.
    """
    user_id = os.getenv("TIKTOK_USER_ID", "taylorswift")
    gcs_bucket = os.getenv("GCS_BUCKET")
    bq_project = os.getenv("BQ_PROJECT")
    bq_dataset = os.getenv("BQ_DATASET", "tiktok_scraper")
    
    print(f"Starting ETL pipeline for user: {user_id}")
    run_etl(user_id, gcs_bucket, bq_project, bq_dataset)
    print("ETL pipeline completed successfully")


if __name__ == "__main__":
    main()
