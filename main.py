import os

from dotenv import load_dotenv
from src.pipeline.etl import run_etl


load_dotenv()


def main():
    """
    Main entry point for Cloud Run Job.
    Fetches TikTok user info and posts, uploads to GCS, and loads into BigQuery.
    """
    # Support multiple channel IDs via comma-separated env var `TIKTOK_USER_IDS`.
    # Backward-compatible with single `TIKTOK_USER_ID`.
    user_ids_str = os.getenv("TIKTOK_USER_IDS") or os.getenv("TIKTOK_USER_ID") or "noraspersonalspace"
    user_ids = [u.strip() for u in user_ids_str.split(",") if u.strip()]
    gcs_bucket = os.getenv("GCS_BUCKET", "hsde_tiktok_scraper")
    bq_project = os.getenv("BQ_PROJECT", "hs2026de")
    bq_dataset = os.getenv("BQ_DATASET", "tiktok_scraper")
    for user_id in user_ids:
        print(f"Starting ETL pipeline for user: {user_id}")
        run_etl(user_id, gcs_bucket, bq_project, bq_dataset)
    print("ETL pipelines completed successfully")


if __name__ == "__main__":
    main()
