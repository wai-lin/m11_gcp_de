import os
from datetime import datetime
import tempfile

from dotenv import load_dotenv
import pandas as pd
from google.cloud import storage, bigquery

from src.tiktok.rapidapi import get_user_info, get_user_posts


load_dotenv()


def to_dict_safe(model):
    # pydantic v2 models support model_dump
    try:
        return model.model_dump()
    except Exception:
        # fallback assume it's already a dict
        return dict(model)


def upload_file_to_gcs(bucket_name: str, source_file: str, dest_path: str):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(source_file)
    return f"gs://{bucket_name}/{dest_path}"


def ensure_bq_dataset(bq_client: bigquery.Client, dataset_id: str):
    try:
        bq_client.get_dataset(dataset_id)
    except Exception:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = os.getenv("BQ_LOCATION", "US")
        bq_client.create_dataset(dataset)
        print(f"Created BigQuery dataset {dataset_id}")


def load_csv_to_bq(bq_client: bigquery.Client, gcs_uri: str, table_id: str):
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


def run_etl(
    user_id: str,
    gcs_bucket: str = None,
    bq_project: str = None,
    bq_dataset: str = "tiktok_scraper",
):
    gcs_bucket = gcs_bucket or os.getenv("GCS_BUCKET", "hsde_tiktok_scraper")
    bq_project = bq_project or os.getenv("BQ_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not bq_project:
        # try gcloud config
        try:
            import subprocess

            bq_project = (
                subprocess.check_output(["gcloud", "config", "get-value", "project"]).decode().strip()
            )
        except Exception:
            raise RuntimeError("BigQuery project not configured. Set BQ_PROJECT or run 'gcloud config set project <id>'")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    print(f"Fetching user info for {user_id}")
    user_info = get_user_info(user_id)
    print(f"Fetching posts for {user_id}")
    posts = get_user_posts(user_id)

    user_dict = to_dict_safe(user_info)
    posts_list = []
    # posts object may have nested structure; find item list
    try:
        data = getattr(posts, "data", None)
        if data and hasattr(data, "itemList"):
            for p in data.itemList:
                posts_list.append(to_dict_safe(p))
        else:
            # fallback: try to dump whole model
            posts_list = to_dict_safe(posts).get("data", {}).get("itemList", [])
    except Exception:
        posts_list = []

    # Build DataFrames
    df_user = pd.json_normalize(user_dict)
    df_posts = pd.json_normalize(posts_list)

    # write csv to temp files
    with tempfile.TemporaryDirectory() as td:
        user_csv = os.path.join(td, f"user_{user_id}_{timestamp}.csv")
        posts_csv = os.path.join(td, f"posts_{user_id}_{timestamp}.csv")
        df_user.to_csv(user_csv, index=False)
        df_posts.to_csv(posts_csv, index=False)

        # upload
        users_path = f"users/{user_id}/{os.path.basename(user_csv)}"
        posts_path = f"posts/{user_id}/{os.path.basename(posts_csv)}"
        user_gs = upload_file_to_gcs(gcs_bucket, user_csv, users_path)
        posts_gs = upload_file_to_gcs(gcs_bucket, posts_csv, posts_path)
        print(f"Uploaded user CSV to {user_gs}")
        print(f"Uploaded posts CSV to {posts_gs}")

        # BigQuery load
        bq_client = bigquery.Client(project=bq_project)
        dataset_id = f"{bq_project}.{bq_dataset}"
        ensure_bq_dataset(bq_client, dataset_id)

        user_table = f"{dataset_id}.users"
        posts_table = f"{dataset_id}.posts"
        load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/{users_path}", user_table)
        load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/{posts_path}", posts_table)

    print("ETL finished")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("user_id", help="TikTok uniqueId (username)")
    parser.add_argument("--gcs-bucket", dest="gcs_bucket", help="GCS bucket name")
    parser.add_argument("--bq-project", dest="bq_project", help="BigQuery project id")
    parser.add_argument("--bq-dataset", dest="bq_dataset", default="tiktok_scraper")
    args = parser.parse_args()
    run_etl(args.user_id, args.gcs_bucket, args.bq_project, args.bq_dataset)
