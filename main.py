from src.tiktok import get_user_posts


def scrape_tiktok():
    khaby = "khaby.lame"
    nora = "noraspersonalspace2510"
    posts = get_user_posts(nora)
    print(posts)
    if posts.data:
        return "Ok"
    return "No posts found"
