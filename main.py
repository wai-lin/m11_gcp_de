import os

from dotenv import load_dotenv
from src.tiktok import get_user_posts


load_dotenv()


def scrape_tiktok():
    user_id = os.getenv("TIKTOK_USER_ID", "noraspersonalspace")
    posts = get_user_posts(user_id)
    print(posts.model_dump_json(indent=2))
    if posts.data:
        return posts.data
    return "No posts found"


if __name__ == "__main__":
    scrape_tiktok()
