from collections import Counter
from datetime import datetime
import re
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .staging import write_and_upload_csv
from .utils import load_csv_to_bq, sanitize_bq_columns


def _pick_first(mapping: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return default


def _pick_series(df: pd.DataFrame, candidates: list[str], default=0):
    for c in candidates:
        if c in df.columns:
            return df[c].fillna(default)
    return pd.Series([default] * len(df), index=df.index)


def _extract_hashtags(text: Any) -> list[str]:
    if not isinstance(text, str):
        return []
    return re.findall(r"#(\w+)", text)


class ProdPostModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    post_id: str | None = None
    channel_id: str
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
    model_config = ConfigDict(populate_by_name=True, extra="allow")

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
        if value:
            return int(value)
    return 1


def _build_user_profile(df_user: pd.DataFrame) -> dict[str, Any]:
    if df_user.empty:
        return {}

    row = df_user.iloc[0].to_dict()
    return {
        "channel_id": row.get("channel_id") or row.get("uniqueId"),
        "profile_name": _pick_first(row, ["uniqueId", "profile_name", "nickname"]),
        "nickname": _pick_first(row, ["nickname", "uniqueId"]),
        "bio_description": _pick_first(row, ["signature", "bioDescription", "bio_description"]),
        "verified": _pick_first(row, ["verified", "isVerified"], None),
        "follower_count": _pick_first(row, ["stats_followerCount", "statsV2_followerCount", "followerCount", "followers", "follower_count"], None),
    }


def build_prod_frames(df_user: pd.DataFrame, df_posts: pd.DataFrame):
    followers = _infer_followers(df_user)

    raw_posts = df_posts.to_dict(orient="records")
    prod_posts = [ProdPostModel.from_raw(row, followers) for row in raw_posts]
    posts_df = pd.DataFrame([post.model_dump() for post in prod_posts])

    grouped = posts_df.groupby("channel_id", dropna=False)

    def _top_hashtags(series, n=5):
        cnt = Counter()
        for tags in series.dropna():
            if isinstance(tags, (list, tuple)):
                cnt.update(tags)
        return [tag for tag, _ in cnt.most_common(n)]

    channel_summary = grouped.agg(
        post_count=("post_id", lambda s: int(s.notna().sum())),
        avg_likes=("likes", lambda s: int(s.fillna(0).mean())),
        median_likes=("likes", lambda s: int(s.fillna(0).median())),
        avg_comments=("comments", lambda s: int(s.fillna(0).mean())),
        avg_shares=("shares", lambda s: int(s.fillna(0).mean())),
        avg_views=("views", lambda s: int(s.fillna(0).mean())),
    ).reset_index()
    channel_summary["top_hashtags"] = grouped["hashtags"].apply(lambda s: _top_hashtags(s, 5)).values

    user_profile = _build_user_profile(df_user)
    user_profile_df = pd.DataFrame([user_profile]) if user_profile else pd.DataFrame()
    if not user_profile_df.empty:
        channel_summary = channel_summary.merge(user_profile_df, on="channel_id", how="left")

    prod_channels = [ProdChannelModel(**row).model_dump() for row in channel_summary.to_dict(orient="records")]

    return sanitize_bq_columns(pd.DataFrame(prod_channels)), sanitize_bq_columns(posts_df)


def load_prod_tables(channels: pd.DataFrame, posts_enriched: pd.DataFrame, user_id: str, gcs_bucket: str, bq_client, dataset_id: str, td: str, timestamp: str):
    _, channels_gs = write_and_upload_csv(
        channels,
        td,
        f"prod_channels_{user_id}_{timestamp}.csv",
        gcs_bucket,
        f"prod/channels/{user_id}/prod_channels_{user_id}_{timestamp}.csv",
    )
    _, posts_gs = write_and_upload_csv(
        posts_enriched,
        td,
        f"prod_posts_{user_id}_{timestamp}.csv",
        gcs_bucket,
        f"prod/posts/{user_id}/prod_posts_{user_id}_{timestamp}.csv",
    )

    print(f"Uploaded prod channels CSV to {channels_gs}")
    print(f"Uploaded prod posts CSV to {posts_gs}")

    load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/prod/channels/{user_id}/prod_channels_{user_id}_{timestamp}.csv", f"{dataset_id}.prod_channels")
    load_csv_to_bq(bq_client, f"gs://{gcs_bucket}/prod/posts/{user_id}/prod_posts_{user_id}_{timestamp}.csv", f"{dataset_id}.prod_posts")
