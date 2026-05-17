import json
import os

from dotenv import load_dotenv

from src.pipeline.extract import run_extraction
from src.pipeline.prod import prod_marker_event as _prod_marker_event
from src.pipeline.staging import stage_manifest_event as _stage_manifest_event


load_dotenv()


def extract_request(request):
    payload = request.get_json(silent=True) or {}
    user_ids_str = (
        payload.get("user_ids")
        or os.getenv("TIKTOK_USER_IDS")
        or os.getenv("TIKTOK_USER_ID")
        or "noraspersonalspace"
    )
    user_ids = [user.strip() for user in str(user_ids_str).split(",") if user.strip()]
    raw_bucket = payload.get("raw_bucket") or os.getenv("RAW_BUCKET") or os.getenv("GCS_BUCKET", "hsde_tiktok_scraper")
    manifest_bucket = payload.get("manifest_bucket") or os.getenv("MANIFEST_BUCKET") or raw_bucket
    raw_prefix = payload.get("raw_prefix") or os.getenv("RAW_PREFIX", "raw")
    bq_dataset = payload.get("bq_dataset") or os.getenv("BQ_DATASET", "tiktok_scraper")

    results = [run_extraction(user_id, raw_bucket, manifest_bucket, raw_prefix, bq_dataset) for user_id in user_ids]
    body = json.dumps({"results": results})
    return body, 200, {"Content-Type": "application/json"}


def stage_manifest_event(event):
    return _stage_manifest_event(event)


def prod_marker_event(event):
    return _prod_marker_event(event)


def main():
    user_ids_str = os.getenv("TIKTOK_USER_IDS") or os.getenv("TIKTOK_USER_ID") or "noraspersonalspace"
    user_ids = [user.strip() for user in user_ids_str.split(",") if user.strip()]
    raw_bucket = os.getenv("RAW_BUCKET") or os.getenv("GCS_BUCKET", "hsde_tiktok_scraper")
    manifest_bucket = os.getenv("MANIFEST_BUCKET") or raw_bucket
    raw_prefix = os.getenv("RAW_PREFIX", "raw")
    bq_dataset = os.getenv("BQ_DATASET", "tiktok_scraper")

    for user_id in user_ids:
        print(f"Starting extraction for user: {user_id}")
        run_extraction(user_id, raw_bucket, manifest_bucket, raw_prefix, bq_dataset)
    print("Extraction finished")


if __name__ == "__main__":
    main()
