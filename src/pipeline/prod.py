from collections import Counter
from datetime import datetime
import re
from typing import Any

import pandas as pd
from google.cloud import bigquery
from pydantic import BaseModel, ConfigDict, Field

from .utils import load_df_to_bq, sanitize_bq_columns


def _pick_first(mapping: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return default


def _extract_hashtags(text: Any) -> list[str]:
    if not isinstance(text, str):
        return []
    return re.findall(r"#(\w+)", text)


class ProdPostModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    post_id: str | None = None
    channel_id: str | None = None
    created_time: str | int | None = None
    description: str | None = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    views: int = 0
    scraped_at: datetime | None = None
    hashtags: list[str] = Field(default_factory=list)
    engagement: float = 0.0

    @classmethod
    def from_raw(cls, row: dict[str, Any], followers: int) -> "ProdPostModel":
        description = _pick_first(row, ["desc", "description", "text", "caption"])
        likes = int(_pick_first(row, ["statsV2_diggCount", "stats_diggCount", "diggCount", "like_count", "likes"], 0) or 0)
        comments = int(_pick_first(row, ["stats_commentCount", "commentCount", "comment_count", "comments"], 0) or 0)
        shares = int(_pick_first(row, ["stats_shareCount", "shareCount", "share_count", "shares"], 0) or 0)
        views = int(_pick_first(row, ["stats_playCount", "playCount", "view_count", "views"], 0) or 0)

        return cls(
            post_id=_pick_first(row, ["id", "postId", "awemeId"]),
            channel_id=_pick_first(row, ["channel_id", "uniqueId"]),
            created_time=_pick_first(row, ["createTime", "create_time"]),
            description=description,
            likes=likes,
            comments=comments,
            shares=shares,
            views=views,
            scraped_at=_pick_first(row, ["scraped_at"]),
            hashtags=_extract_hashtags(description),
            engagement=(likes + comments + shares) / max(followers, 1),
        )


class ProdChannelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    channel_id: str
    profile_name: str | None = None
    nickname: str | None = None
    bio_description: str | None = None
    verified: bool | None = None
    follower_count: int | None = None
    post_count: int = 0
    avg_likes: int = 0
    median_likes: int = 0
    avg_comments: int = 0
    avg_shares: int = 0
    avg_views: int = 0
    top_hashtags: list[str] = Field(default_factory=list)


def _infer_followers(df_user: pd.DataFrame) -> int:
    if df_user.empty:
        return 1

    first_row = df_user.iloc[0].to_dict()
    for key in ["stats_followerCount", "statsV2_followerCount", "followerCount", "followers", "follower_count"]:
        value = first_row.get(key)
        if value not in (None, ""):
            try:
                return int(float(value))
            except Exception:
                continue
    return 1


def _build_user_profile(df_user: pd.DataFrame) -> dict[str, Any]:
    if df_user.empty:
        return {}

    row = df_user.iloc[0].to_dict()
    channel_id = row.get("channel_id") or row.get("uniqueId")
    if not channel_id:
        return {}

    return {
        "channel_id": channel_id,
        "profile_name": _pick_first(row, ["uniqueId", "profile_name", "nickname"]),
        "nickname": _pick_first(row, ["nickname", "uniqueId"]),
        "bio_description": _pick_first(row, ["signature", "bioDescription", "bio_description"]),
        "verified": _pick_first(row, ["verified", "isVerified"], None),
        "follower_count": _pick_first(row, ["stats_followerCount", "statsV2_followerCount", "followerCount", "followers", "follower_count"], None),
    }


def _top_hashtags(series: pd.Series, n: int = 5) -> list[str]:
    counter = Counter()
    for tags in series.dropna():
        if isinstance(tags, (list, tuple)):
            counter.update(tags)
    return [tag for tag, _ in counter.most_common(n)]


def _empty_prod_frame(model: type[BaseModel]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(model.model_fields.keys()))


def build_prod_frames(df_user: pd.DataFrame, df_posts: pd.DataFrame):
    followers = _infer_followers(df_user)
    user_profile = _build_user_profile(df_user)

    if df_posts.empty:
        if not user_profile:
            return sanitize_bq_columns(_empty_prod_frame(ProdChannelModel)), sanitize_bq_columns(_empty_prod_frame(ProdPostModel))

        fallback_channel = ProdChannelModel(
            channel_id=user_profile["channel_id"],
            profile_name=user_profile.get("profile_name"),
            nickname=user_profile.get("nickname"),
            bio_description=user_profile.get("bio_description"),
            verified=user_profile.get("verified"),
            follower_count=user_profile.get("follower_count"),
            post_count=0,
            avg_likes=0,
            median_likes=0,
            avg_comments=0,
            avg_shares=0,
            avg_views=0,
            top_hashtags=[],
        ).model_dump()
        return sanitize_bq_columns(pd.DataFrame([fallback_channel])), sanitize_bq_columns(_empty_prod_frame(ProdPostModel))

    raw_posts = df_posts.to_dict(orient="records")
    prod_posts = [ProdPostModel.from_raw(row, followers).model_dump() for row in raw_posts]
    posts_df = pd.DataFrame(prod_posts)

    grouped = posts_df.groupby("channel_id", dropna=False)
    channel_summary = grouped.agg(
        post_count=("post_id", lambda s: int(s.notna().sum())),
        avg_likes=("likes", lambda s: int(s.fillna(0).mean())),
        median_likes=("likes", lambda s: int(s.fillna(0).median())),
        avg_comments=("comments", lambda s: int(s.fillna(0).mean())),
        avg_shares=("shares", lambda s: int(s.fillna(0).mean())),
        avg_views=("views", lambda s: int(s.fillna(0).mean())),
    ).reset_index()
    channel_summary["top_hashtags"] = grouped["hashtags"].apply(lambda series: _top_hashtags(series, 5)).values

    if user_profile:
        channel_summary = channel_summary.merge(pd.DataFrame([user_profile]), on="channel_id", how="left")

    prod_channels = [ProdChannelModel(**row).model_dump() for row in channel_summary.to_dict(orient="records")]

    return sanitize_bq_columns(pd.DataFrame(prod_channels)), sanitize_bq_columns(posts_df)


def load_prod_tables(channels: pd.DataFrame, posts_enriched: pd.DataFrame, user_id: str, bq_client, dataset_id: str):
    print(f"Loading prod tables for {user_id}")
    load_df_to_bq(bq_client, channels, f"{dataset_id}.prod_channels")
    load_df_to_bq(bq_client, posts_enriched, f"{dataset_id}.prod_posts")


def _rows_to_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def load_prod_tables_from_staging(bq_client, dataset_id: str, user_id: str):
    user_query = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("user_id", "STRING", user_id)]
    )
    posts_query = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("user_id", "STRING", user_id)]
    )

    user_job = bq_client.query(
        f"SELECT * FROM `{dataset_id}.staging_users` WHERE channel_id = @user_id LIMIT 1",
        job_config=user_query,
    )
    posts_job = bq_client.query(
        f"SELECT * FROM `{dataset_id}.staging_posts` WHERE channel_id = @user_id",
        job_config=posts_query,
    )

    df_user = _rows_to_df([dict(row) for row in user_job.result()])
    df_posts = _rows_to_df([dict(row) for row in posts_job.result()])

    channels, posts_enriched = build_prod_frames(df_user, df_posts)
    load_prod_tables(channels, posts_enriched, user_id, bq_client, dataset_id)
