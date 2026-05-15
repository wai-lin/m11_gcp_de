import csv
import json
import os
from datetime import datetime

import pandas as pd

from src.tiktok.rapidapi import get_sec_uid, get_user_info, get_user_posts

from .utils import load_csv_to_bq, sanitize_bq_columns, to_dict_safe, upload_file_to_gcs


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
        value = str(value)

    value = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
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

    _, user_gs = write_and_upload_csv(
        df_user,
        td,
        f"user_{user_id}_{timestamp}.csv",
        gcs_bucket,
        f"users/{user_id}/user_{user_id}_{timestamp}.csv",
        user_columns,
    )
    _, posts_gs = write_and_upload_csv(
        df_posts,
        td,
        f"posts_{user_id}_{timestamp}.csv",
        gcs_bucket,
        f"posts/{user_id}/posts_{user_id}_{timestamp}.csv",
        posts_columns,
    )

    print(f"Uploaded user CSV to {user_gs}")
    print(f"Uploaded posts CSV to {posts_gs}")

    load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/users/{user_id}/user_{user_id}_{timestamp}.csv", user_table_id, df_user.reindex(columns=user_columns, fill_value=""))
    load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/posts/{user_id}/posts_{user_id}_{timestamp}.csv", posts_table_id, df_posts.reindex(columns=posts_columns, fill_value=""))
