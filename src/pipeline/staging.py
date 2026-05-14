import csv
import json
import os
from datetime import datetime

import pandas as pd

from .utils import load_csv_to_bq, sanitize_bq_columns, to_dict_safe, upload_file_to_gcs
from src.tiktok.rapidapi import get_sec_uid, get_user_info, get_user_posts


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


def write_and_upload_csv(df: pd.DataFrame, td: str, filename: str, gcs_bucket: str, gcs_path: str):
    csv_path = os.path.join(td, filename)
    # Sanitize values to avoid embedded newlines or complex objects breaking CSV columns
    df_safe = df.copy()
    df_safe = df_safe.fillna("")

    def _sanitize_cell(val):
        if isinstance(val, (list, dict)):
            try:
                s = json.dumps(val, ensure_ascii=False)
            except Exception:
                s = str(val)
        else:
            s = str(val)
        # Replace newlines and carriage returns with spaces
        s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        return s

    df_safe = df_safe.astype(object).where(pd.notnull(df_safe), "")
    for col in df_safe.columns:
        df_safe[col] = df_safe[col].map(_sanitize_cell)

    df_safe.to_csv(csv_path, index=False, quoting=csv.QUOTE_NONNUMERIC, encoding="utf-8", line_terminator="\n")
    return csv_path, upload_file_to_gcs(gcs_bucket, csv_path, gcs_path)


def load_staging_tables(df_user: pd.DataFrame, df_posts: pd.DataFrame, user_id: str, gcs_bucket: str, bq_client, dataset_id: str, td: str, timestamp: str):
    _, user_gs = write_and_upload_csv(
        df_user,
        td,
        f"user_{user_id}_{timestamp}.csv",
        gcs_bucket,
        f"users/{user_id}/user_{user_id}_{timestamp}.csv",
    )
    _, posts_gs = write_and_upload_csv(
        df_posts,
        td,
        f"posts_{user_id}_{timestamp}.csv",
        gcs_bucket,
        f"posts/{user_id}/posts_{user_id}_{timestamp}.csv",
    )

    print(f"Uploaded user CSV to {user_gs}")
    print(f"Uploaded posts CSV to {posts_gs}")

    load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/users/{user_id}/user_{user_id}_{timestamp}.csv", f"{dataset_id}.staging_users", df_user)
    load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/posts/{user_id}/posts_{user_id}_{timestamp}.csv", f"{dataset_id}.staging_posts", df_posts)
