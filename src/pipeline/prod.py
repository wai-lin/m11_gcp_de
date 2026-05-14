import re
from collections import Counter

import pandas as pd

from .staging import write_and_upload_csv
from .utils import load_csv_to_bq, sanitize_bq_columns


def build_prod_frames(df_user: pd.DataFrame, df_posts: pd.DataFrame):
    def _pick_series(df, candidates, default=0):
        for c in candidates:
            if c in df.columns:
                return df[c].fillna(default)
        return pd.Series([default] * len(df), index=df.index)

    def _extract_hashtags(text):
        if not isinstance(text, str):
            return []
        return re.findall(r"#(\w+)", text)

    likes = _pick_series(df_posts, ["stats.diggCount", "diggCount", "like_count", "likes"]).astype(int)
    comments = _pick_series(df_posts, ["stats.commentCount", "commentCount", "comment_count", "comments"]).astype(int)
    shares = _pick_series(df_posts, ["stats.shareCount", "shareCount", "share_count", "shares"]).astype(int)
    views = _pick_series(df_posts, ["stats.playCount", "playCount", "view_count", "views"]).astype(int)

    post_id_candidates = df_posts.columns.intersection(["id", "postId", "awemeId"]).tolist()
    post_id_col = post_id_candidates[0] if post_id_candidates else None
    desc_candidates = df_posts.columns.intersection(["desc", "description", "text"]).tolist()
    desc_col = desc_candidates[0] if desc_candidates else None

    df_posts_enriched = pd.DataFrame({
        "post_id": df_posts[post_id_col] if post_id_col in df_posts.columns else pd.Series([None] * len(df_posts)),
        "channel_id": df_posts.get("channel_id"),
        "created_time": df_posts.get("createTime") if "createTime" in df_posts.columns else df_posts.get("create_time"),
        "description": df_posts[desc_col] if desc_col in df_posts.columns else df_posts.get("caption"),
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "views": views,
        "scraped_at": df_posts.get("scraped_at"),
    })
    df_posts_enriched["hashtags"] = df_posts_enriched["description"].fillna("").apply(_extract_hashtags)

    followers = 1
    for c in ["stats.followerCount", "followerCount", "followers", "follower_count"]:
        if c in df_user.columns:
            followers = int(df_user.iloc[0].get(c, 0) or 1)
            break
    if followers == 1:
        followers = int(df_user.iloc[0].get("stats.followers", 0) or 1)

    df_posts_enriched["engagement"] = (
        df_posts_enriched["likes"].fillna(0)
        + df_posts_enriched["comments"].fillna(0)
        + df_posts_enriched["shares"].fillna(0)
    ) / followers

    grp = df_posts_enriched.groupby("channel_id")
    channels = grp.agg(
        post_count=("post_id", lambda s: s.notna().sum()),
        avg_likes=("likes", lambda s: int(s.fillna(0).mean())),
        median_likes=("likes", lambda s: int(s.fillna(0).median())),
        avg_comments=("comments", lambda s: int(s.fillna(0).mean())),
        avg_shares=("shares", lambda s: int(s.fillna(0).mean())),
        avg_views=("views", lambda s: int(s.fillna(0).mean())),
    ).reset_index()

    def _top_hashtags(series, n=5):
        cnt = Counter()
        for tags in series.dropna():
            if isinstance(tags, (list, tuple)):
                cnt.update(tags)
        return [t for t, _ in cnt.most_common(n)]

    channels["top_hashtags"] = grp["hashtags"].apply(lambda s: _top_hashtags(s, 5)).values

    user_meta_cols = [c for c in df_user.columns if c not in ["scraped_at", "channel_id"]]
    user_meta = df_user[user_meta_cols + ["channel_id"]] if "channel_id" in df_user.columns else df_user.head(1)
    if "channel_id" not in user_meta.columns and "uniqueId" in df_user.columns:
        user_meta = df_user.rename(columns={"uniqueId": "channel_id"})

    channels = channels.merge(user_meta, on="channel_id", how="left")
    return sanitize_bq_columns(channels), sanitize_bq_columns(df_posts_enriched)


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
