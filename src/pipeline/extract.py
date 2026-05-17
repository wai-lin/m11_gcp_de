import json
import os
import tempfile
from datetime import datetime, timezone

import pandas as pd

from src.tiktok.rapidapi import get_sec_uid, get_user_info, get_user_posts

from .staging import build_staging_dataframes, extract_posts_list, write_and_upload_csv
from .utils import upload_file_to_gcs


def fetch_tiktok_snapshot(user_id: str):
    print(f"Fetching user info for {user_id}")
    user_info = get_user_info(user_id)
    sec_uid = get_sec_uid(user_id, user_info)
    print(f"Fetching posts for {user_id}")
    posts = get_user_posts(sec_uid)
    return user_info, posts


def _build_manifest(
    user_id: str,
    bq_dataset: str,
    scraped_at: datetime,
    user_csv_uri: str,
    posts_csv_uri: str,
    df_user: pd.DataFrame,
    df_posts: pd.DataFrame,
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "bq_dataset": bq_dataset,
        "scraped_at": scraped_at.isoformat(),
        "user_csv_uri": user_csv_uri,
        "posts_csv_uri": posts_csv_uri,
        "user_columns": list(df_user.columns),
        "posts_columns": list(df_posts.columns),
    }


def run_extraction(
    user_id: str,
    raw_bucket: str | None = None,
    manifest_bucket: str | None = None,
    raw_prefix: str = "raw",
    bq_dataset: str = "tiktok_scraper",
):
    """Fetch TikTok data and upload raw CSV plus manifest to GCS."""
    raw_bucket = raw_bucket or os.getenv("RAW_BUCKET") or os.getenv("GCS_BUCKET", "hsde_tiktok_scraper")
    manifest_bucket = manifest_bucket or os.getenv("MANIFEST_BUCKET") or raw_bucket

    scraped_at = datetime.now(timezone.utc)
    timestamp = scraped_at.strftime("%Y%m%dT%H%M%SZ")
    user_info, posts = fetch_tiktok_snapshot(user_id)
    posts_list = extract_posts_list(posts)
    df_user, df_posts = build_staging_dataframes(user_info, posts_list, user_id, scraped_at)

    with tempfile.TemporaryDirectory() as td:
        _, user_csv_uri = write_and_upload_csv(
            df_user,
            td,
            f"user_{user_id}_{timestamp}.csv",
            raw_bucket,
            f"{raw_prefix}/users/{user_id}/user_{user_id}_{timestamp}.csv",
            list(df_user.columns),
        )
        _, posts_csv_uri = write_and_upload_csv(
            df_posts,
            td,
            f"posts_{user_id}_{timestamp}.csv",
            raw_bucket,
            f"{raw_prefix}/posts/{user_id}/posts_{user_id}_{timestamp}.csv",
            list(df_posts.columns),
        )

        manifest = _build_manifest(
            user_id=user_id,
            bq_dataset=bq_dataset,
            scraped_at=scraped_at,
            user_csv_uri=user_csv_uri,
            posts_csv_uri=posts_csv_uri,
            df_user=df_user,
            df_posts=df_posts,
        )
        manifest_path = f"{raw_prefix}/manifests/{user_id}/manifest_{user_id}_{timestamp}.json"
        manifest_file = os.path.join(td, "manifest.json")
        with open(manifest_file, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        manifest_uri = upload_file_to_gcs(manifest_bucket, manifest_file, manifest_path)

    print(f"Uploaded raw CSVs for {user_id}")
    print(f"Uploaded manifest to {manifest_uri}")
    return {
        "user_id": user_id,
        "manifest_uri": manifest_uri,
        "user_csv_uri": user_csv_uri,
        "posts_csv_uri": posts_csv_uri,
    }
