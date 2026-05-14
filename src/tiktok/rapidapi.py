import os
import requests

from src.tiktok.rapidapi_models import (
    RapidApiUserInfoResponse,
    RapidApiUserPostsResponse,
)


def _rapid_tiktok(path: str, params: dict):
    """Fetch TikTok data using RapidAPI"""
    url = f"https://tiktok-api23.p.rapidapi.com/api/{path}"
    apikey = os.getenv("RAPIDAPI_KEY")
    print(f"Making request to {url} with params={params!r}")
    headers = {
        "x-rapidapi-key": apikey,
        "x-rapidapi-host": "tiktok-api23.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    return requests.get(url, headers=headers, params=params)


def _get_sec_uid(user_id: str, user_info: RapidApiUserInfoResponse):
    sec_uid = user_info.userInfo.user.secUid if user_info.userInfo and user_info.userInfo.user else None
    if not sec_uid:
        raise ValueError(f"Could not resolve secUid for user_id={user_id!r}")
    return sec_uid


def get_user_info(user_id: str):
    """Get user info"""
    params = {"uniqueId": user_id}
    response = _rapid_tiktok("user/info", params)
    return RapidApiUserInfoResponse.model_validate(response.json())


def get_user_posts(user_id: str):
    """Get user posts"""
    user_info = get_user_info(user_id)
    sec_uid = _get_sec_uid(user_id, user_info)
    params = {"secUid": sec_uid, "count": "35", "cursor": "0"}
    response = _rapid_tiktok("user/posts", params)
    return RapidApiUserPostsResponse.model_validate(response.json())
