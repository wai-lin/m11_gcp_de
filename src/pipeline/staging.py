import csv
import json
import os
import re
import tempfile
from datetime import datetime

import pandas as pd

from src.tiktok.rapidapi import get_sec_uid, get_user_info, get_user_posts

from .utils import (
    coerce_df_to_bq_schema,
    download_json_from_gcs,
    load_csv_to_bq,
    sanitize_bq_columns,
    to_dict_safe,
    upload_file_to_gcs,
)


def fetch_tiktok_snapshot(user_id: str):
    print(f"Fetching user info for {user_id}")
    user_info = get_user_info(user_id)
    sec_uid = get_sec_uid(user_id, user_info)
    print(f"Fetching posts for {user_id}")
    posts = get_user_posts(sec_uid)
    return user_info, posts


def extract_posts_list(posts) -> list:
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
    return posts_list


def build_staging_dataframes(user_info, posts_list, user_id: str, scraped_at: datetime):
    user_dict = to_dict_safe(user_info)
    df_user = sanitize_bq_columns(pd.json_normalize(user_dict))
    df_posts = sanitize_bq_columns(pd.json_normalize(posts_list))

    df_user["scraped_at"] = scraped_at
    df_user["channel_id"] = user_id
    df_posts["scraped_at"] = scraped_at
    df_posts["channel_id"] = user_id
    return df_user, df_posts


def _sanitize_csv_value(value):
    if isinstance(value, (list, dict, tuple, set)):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = str(value)
    elif pd.isna(value):
        value = ""
    else:
        # Preserve numeric formatting: convert floats that are whole numbers to ints
        try:
            if isinstance(value, float):
                if value.is_integer():
                    value = str(int(value))
                else:
                    value = repr(value)
            else:
                value = str(value)
        except Exception:
            value = str(value)

    value = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    # Convert string '3.0' -> '3' to avoid BigQuery INT parsing issues
    try:
        if isinstance(value, str) and re.match(r"^-?\d+\.0+$", value):
            value = value.split(".")[0]
    except Exception:
        pass

    return "".join(ch if ch >= " " else " " for ch in value)


def _raw_csv_columns(bq_client, table_id: str, df: pd.DataFrame) -> list[str]:
    try:
        table = bq_client.get_table(table_id)
        columns = [field.name for field in table.schema]
    except Exception:
        columns = []

    for column in df.columns:
        if column not in columns:
            columns.append(column)

    return columns


def _raw_csv_schema(bq_client, table_id: str, df: pd.DataFrame):
    try:
        table = bq_client.get_table(table_id)
        schema = list(table.schema)
    except Exception:
        schema = []

    if not schema:
        from google.cloud import bigquery

        schema = [bigquery.SchemaField(column, "STRING", mode="NULLABLE") for column in df.columns]

    return schema


def write_and_upload_csv(df: pd.DataFrame, td: str, filename: str, gcs_bucket: str, gcs_path: str, columns: list[str] | None = None):
    csv_path = os.path.join(td, filename)
    df_safe = df.copy().astype(object)
    if columns:
        df_safe = df_safe.reindex(columns=columns, fill_value="")
    for col in df_safe.columns:
        df_safe[col] = df_safe[col].map(_sanitize_csv_value)

    with open(csv_path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.writer(file_handle, quoting=csv.QUOTE_ALL, escapechar="\\", lineterminator="\n")
        writer.writerow(list(df_safe.columns))
        for row in df_safe.itertuples(index=False, name=None):
            writer.writerow([_sanitize_csv_value(value) for value in row])
    return csv_path, upload_file_to_gcs(gcs_bucket, csv_path, gcs_path)


def load_staging_tables(df_user: pd.DataFrame, df_posts: pd.DataFrame, user_id: str, gcs_bucket: str, bq_client, dataset_id: str, td: str, timestamp: str):
    user_table_id = f"{dataset_id}.staging_users"
    posts_table_id = f"{dataset_id}.staging_posts"

    user_columns = _raw_csv_columns(bq_client, user_table_id, df_user)
    posts_columns = _raw_csv_columns(bq_client, posts_table_id, df_posts)
    user_schema = _raw_csv_schema(bq_client, user_table_id, df_user)
    posts_schema = _raw_csv_schema(bq_client, posts_table_id, df_posts)

    df_user_csv = coerce_df_to_bq_schema(df_user.reindex(columns=user_columns, fill_value=""), user_schema)
    df_posts_csv = coerce_df_to_bq_schema(df_posts.reindex(columns=posts_columns, fill_value=""), posts_schema)

    _, user_gs = write_and_upload_csv(
        df_user_csv,
        td,
        f"user_{user_id}_{timestamp}.csv",
        gcs_bucket,
        f"users/{user_id}/user_{user_id}_{timestamp}.csv",
        user_columns,
    )
    _, posts_gs = write_and_upload_csv(
        df_posts_csv,
        td,
        f"posts_{user_id}_{timestamp}.csv",
        gcs_bucket,
        f"posts/{user_id}/posts_{user_id}_{timestamp}.csv",
        posts_columns,
    )

    print(f"Uploaded user CSV to {user_gs}")
    print(f"Uploaded posts CSV to {posts_gs}")

    load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/users/{user_id}/user_{user_id}_{timestamp}.csv", user_table_id, df_user_csv)
    load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/posts/{user_id}/posts_{user_id}_{timestamp}.csv", posts_table_id, df_posts_csv)


def load_staging_tables_from_manifest(manifest: dict[str, object], bq_client, dataset_id: str):
    user_id = str(manifest["user_id"])
    user_table_id = f"{dataset_id}.staging_users"
    posts_table_id = f"{dataset_id}.staging_posts"

    load_csv_to_bq(
        bq_client,
        str(manifest["user_csv_uri"]),
        user_table_id,
        columns=list(manifest.get("user_columns") or []),
    )
    load_csv_to_bq(
        bq_client,
        str(manifest["posts_csv_uri"]),
        posts_table_id,
        columns=list(manifest.get("posts_columns") or []),
    )

    print(f"Loaded raw staging tables for {user_id}")


def write_staging_complete_marker(
    user_id: str,
    gcs_bucket: str,
    marker_path: str,
    manifest_uri: str,
    bq_dataset: str,
    timestamp: str,
) -> str:
    with tempfile.TemporaryDirectory() as td:
        marker_path_local = os.path.join(td, "staging_complete.json")
        payload = {
            "user_id": user_id,
            "bq_dataset": bq_dataset,
            "manifest_uri": manifest_uri,
            "completed_at": timestamp,
        }
        with open(marker_path_local, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return upload_file_to_gcs(gcs_bucket, marker_path_local, marker_path)


def stage_manifest_event(event) -> dict[str, str]:
    event_data = getattr(event, "data", event) or {}
    if not isinstance(event_data, dict):
        raise ValueError("Staging event payload must be a mapping")

    bucket = event_data.get("bucket") or event_data.get("bucket_name")
    name = event_data.get("name") or event_data.get("object")
    if not bucket or not name:
        raise ValueError("Staging event missing bucket or object name")

    manifest = download_json_from_gcs(str(bucket), str(name))
    bq_project = os.getenv("BQ_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not bq_project:
        raise RuntimeError("BQ_PROJECT or GOOGLE_CLOUD_PROJECT must be set")
    bq_dataset = os.getenv("BQ_DATASET", "tiktok_scraper")
    dataset_id = f"{bq_project}.{bq_dataset}"

    from src.google import get_bigquery_client

    bq_client = get_bigquery_client(project=bq_project)
    from .utils import ensure_bq_dataset

    ensure_bq_dataset(bq_client, dataset_id)
    load_staging_tables_from_manifest(manifest, bq_client, dataset_id)

    marker_bucket = os.getenv("STAGING_MARKER_BUCKET") or str(bucket)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    marker_path = f"prod-ready/{manifest['user_id']}/{timestamp}.json"
    marker_uri = write_staging_complete_marker(
        str(manifest["user_id"]),
        marker_bucket,
        marker_path,
        f"gs://{bucket}/{name}",
        bq_dataset,
        timestamp,
    )

    print(f"Wrote staging marker to {marker_uri}")
    return {"marker_uri": marker_uri, "user_id": str(manifest["user_id"])}
