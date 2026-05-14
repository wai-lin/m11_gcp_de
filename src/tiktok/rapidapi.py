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
    if not apikey:
        raise RuntimeError("RAPIDAPI_KEY is not set")
    print(f"Making request to {url} with params={params!r}")
    headers = {
        "x-rapidapi-key": apikey,
        "x-rapidapi-host": "tiktok-api23.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(
            f"RapidAPI request failed for {path}: status={response.status_code}, body={response.text[:400]}"
        )
    return response


def get_sec_uid(user_id: str, user_info: RapidApiUserInfoResponse):
    sec_uid = user_info.userInfo.user.secUid if user_info.userInfo and user_info.userInfo.user else None
    if not sec_uid:
        # Fallback for response shape changes: scan the whole payload for the first secUid.
        def _find_sec_uid(value):
            if isinstance(value, dict):
                if value.get("secUid"):
                    return value["secUid"]
                for child in value.values():
                    found = _find_sec_uid(child)
                    if found:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = _find_sec_uid(child)
                    if found:
                        return found
            return None

        sec_uid = _find_sec_uid(user_info.model_dump())

    if not sec_uid:
        payload = user_info.model_dump()
        status = payload.get("statusCode")
        message = payload.get("statusMsg") or payload.get("message")
        raise ValueError(
            f"Could not resolve secUid for user_id={user_id!r}; statusCode={status!r}, message={message!r}"
        )
    return sec_uid


def get_user_info(user_id: str):
    """Get user info"""
    params = {"uniqueId": user_id}
    response = _rapid_tiktok("user/info", params)
    return RapidApiUserInfoResponse.model_validate(response.json())


def get_user_posts(sec_uid: str, count: int = 35, cursor: int = 0):
    """Get user posts"""
    params = {"secUid": sec_uid, "count": str(count), "cursor": str(cursor)}
    response = _rapid_tiktok("user/posts", params)
    return RapidApiUserPostsResponse.model_validate(response.json())
