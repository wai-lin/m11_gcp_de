import os
import re
from datetime import datetime, timezone
import tempfile
import sys
from pathlib import Path

# Make project root importable when running this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
import pandas as pd
from google.cloud import bigquery

from src.google import get_bigquery_client, get_storage_bucket
from src.tiktok.rapidapi import get_sec_uid, get_user_info, get_user_posts


load_dotenv()


def to_dict_safe(model):
    """Convert Pydantic model to dict."""
    try:
        return model.model_dump()
    except Exception:
        return dict(model)


def upload_file_to_gcs(bucket_name: str, source_file: str, dest_path: str) -> str:
    """Upload file to GCS and return gs:// URI."""
    _, bucket = get_storage_bucket(bucket_name=bucket_name)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(source_file)
    return f"gs://{bucket_name}/{dest_path}"


def ensure_bq_dataset(bq_client: bigquery.Client, dataset_id: str) -> None:
    """Ensure BigQuery dataset exists."""
    try:
        bq_client.get_dataset(dataset_id)
    except Exception:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = os.getenv("BQ_LOCATION", "US")
        bq_client.create_dataset(dataset)
        print(f"Created BigQuery dataset {dataset_id}")


def load_csv_to_bq(bq_client: bigquery.Client, gcs_uri: str, table_id: str) -> None:
    """Load CSV from GCS into BigQuery table."""
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    load_job = bq_client.load_table_from_uri(gcs_uri, table_id, job_config=job_config)
    load_job.result()
    table = bq_client.get_table(table_id)
    print(f"Loaded {table.num_rows} rows into {table_id}")


def sanitize_bq_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize DataFrame column names for BigQuery compatibility."""
    renamed = []
    seen = {}
    for col in df.columns:
        clean = re.sub(r"[^A-Za-z0-9_]", "_", str(col))
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean:
            clean = "col"
        if clean[0].isdigit():
            clean = f"col_{clean}"
        count = seen.get(clean, 0)
        seen[clean] = count + 1
        if count:
            clean = f"{clean}_{count}"
        renamed.append(clean)

    df = df.copy()
    df.columns = renamed
    return df


def run_etl(
    user_id: str,
    gcs_bucket: str = None,
    bq_project: str = None,
    bq_dataset: str = "tiktok_scraper",
) -> None:
    """
    Run ETL pipeline: fetch TikTok user data, upload to GCS, load into BigQuery.
    """
    gcs_bucket = gcs_bucket or os.getenv("GCS_BUCKET", "hsde_tiktok_scraper")
    bq_project = bq_project or os.getenv("BQ_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not bq_project:
        try:
            import subprocess
            bq_project = (
                subprocess.check_output(["gcloud", "config", "get-value", "project"]).decode().strip()
            )
        except Exception:
            raise RuntimeError("BigQuery project not configured. Set BQ_PROJECT or run 'gcloud config set project <id>'")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"Fetching user info for {user_id}")
    user_info = get_user_info(user_id)
    sec_uid = get_sec_uid(user_id, user_info)
    print(f"Fetching posts for {user_id}")
    posts = get_user_posts(sec_uid)

    user_dict = to_dict_safe(user_info)
    posts_list = []
    try:
        data = getattr(posts, "data", None)
        if data and hasattr(data, "itemList"):
            for p in data.itemList:
                posts_list.append(to_dict_safe(p))
        else:
            posts_list = to_dict_safe(posts).get("data", {}).get("itemList", [])
    except Exception:
        posts_list = []

    # Build DataFrames
    df_user = pd.json_normalize(user_dict)
    df_posts = pd.json_normalize(posts_list)
    df_user = sanitize_bq_columns(df_user)
    df_posts = sanitize_bq_columns(df_posts)

    # Write and upload CSVs
    with tempfile.TemporaryDirectory() as td:
        user_csv = os.path.join(td, f"user_{user_id}_{timestamp}.csv")
        posts_csv = os.path.join(td, f"posts_{user_id}_{timestamp}.csv")
        df_user.to_csv(user_csv, index=False)
        df_posts.to_csv(posts_csv, index=False)

        users_path = f"users/{user_id}/{os.path.basename(user_csv)}"
        posts_path = f"posts/{user_id}/{os.path.basename(posts_csv)}"
        user_gs = upload_file_to_gcs(gcs_bucket, user_csv, users_path)
        posts_gs = upload_file_to_gcs(gcs_bucket, posts_csv, posts_path)
        print(f"Uploaded user CSV to {user_gs}")
        print(f"Uploaded posts CSV to {posts_gs}")

        # Load into BigQuery
        bq_client = get_bigquery_client(project=bq_project)
        dataset_id = f"{bq_project}.{bq_dataset}"
        ensure_bq_dataset(bq_client, dataset_id)

        user_table = f"{dataset_id}.users"
        posts_table = f"{dataset_id}.posts"
        load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/{users_path}", user_table)
        load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/{posts_path}", posts_table)

    print("ETL finished")
