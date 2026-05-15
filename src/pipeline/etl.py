import os
import sys
import tempfile

from dotenv import load_dotenv
from datetime import datetime, timezone
from pathlib import Path
from .prod import load_prod_tables_from_staging
from .staging import (
    build_staging_dataframes,
    extract_posts_list,
    fetch_tiktok_snapshot,
    load_staging_tables,
)
from .utils import ensure_bq_dataset
from src.google import get_bigquery_client

# Make project root importable when running this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


load_dotenv()


def _resolve_bq_project(bq_project: str = None) -> str:
    if bq_project:
        return bq_project

    resolved = os.getenv("BQ_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if resolved:
        return resolved

    try:
        import subprocess

        return subprocess.check_output(
            ["gcloud", "config", "get-value", "project"]
        ).decode().strip()
    except Exception as exc:
        raise RuntimeError(
            "BigQuery project not configured. Set BQ_PROJECT or run 'gcloud config set project <id>'"
        ) from exc


def run_etl(
    user_id: str,
    gcs_bucket: str = None,
    bq_project: str = None,
    bq_dataset: str = "tiktok_scraper",
) -> None:
    """
    Run ETL pipeline: fetch TikTok user data, enrich it, and load into BigQuery.
    """
    gcs_bucket = gcs_bucket or os.getenv("GCS_BUCKET", "hsde_tiktok_scraper")
    bq_project = _resolve_bq_project(bq_project)

    scraped_at = datetime.now(timezone.utc)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    user_info, posts = fetch_tiktok_snapshot(user_id)
    posts_list = extract_posts_list(posts)
    df_user, df_posts = build_staging_dataframes(user_info, posts_list, user_id, scraped_at)

    with tempfile.TemporaryDirectory() as td:
        bq_client = get_bigquery_client(project=bq_project)
        dataset_id = f"{bq_project}.{bq_dataset}"
        ensure_bq_dataset(bq_client, dataset_id)

        load_staging_tables(df_user, df_posts, user_id, gcs_bucket, bq_client, dataset_id, td, timestamp)
        load_prod_tables_from_staging(bq_client, dataset_id, user_id)

    print("ETL finished")
