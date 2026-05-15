## Instructions

Add the following instruction in the insturction textbox.

```
- channel owner's id is `noraspersonalspace`
- channel owner only play steam games on mac with M series chip
- other popular channel ids similar in channel categories `swiitsour` and `cozywithronnie`
- filter with `scraped_at` to get the latest updated data
```

---

## Queries Examples

Q: If I want to get over 1K view and get more followers, what type of video should I post next?

```sql
SELECT
  video_type,
  COUNT(1) AS post_count,
  ROUND(AVG(view_count),0) AS avg_views,
  ROUND(AVG(like_count),0) AS avg_likes
FROM
  `hs2026de.tiktok_scraper.prod_posts` AS posts
WHERE
  LOWER(channel_id) = 'noraspersonalspace'
  AND DATE(scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY video_type
ORDER BY avg_views DESC
LIMIT 10;
```

--------------------------------------------------------------

Q: Which videos from `noraspersonalspace` had >=1,000 views in last 30 days?

```sql
SELECT
  video_id,
  title,
  view_count,
  like_count,
  published_at,
  scraped_at
FROM
  `hs2026de.tiktok_scraper.prod_posts`
WHERE
  LOWER(channel_id) = 'noraspersonalspace'
  AND view_count >= 1000
  AND DATE(published_at, 'Asia/Bangkok') >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
ORDER BY view_count DESC
LIMIT 100;
```

Q: Which hashtags correlate with high views (last 90 days)?

```sql
SELECT
  tag,
  COUNT(1) AS uses,
  ROUND(AVG(view_count),0) AS avg_views
FROM
  `hs2026de.tiktok_scraper.prod_posts`,
  UNNEST(SPLIT(LOWER(hashtags), ',')) AS tag
WHERE
  tag != ''
  AND DATE(scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY tag
ORDER BY avg_views DESC
LIMIT 50;
```

Q: Best publish hour (Thailand timezone) for average views (last 90 days)?

```sql
SELECT
  EXTRACT(HOUR FROM DATETIME(published_at, 'Asia/Bangkok')) AS hour_bkk,
  ROUND(AVG(view_count),0) AS avg_views,
  COUNT(1) AS posts
FROM
  `hs2026de.tiktok_scraper.prod_posts`
WHERE
  DATE(published_at, 'Asia/Bangkok') >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY hour_bkk
ORDER BY avg_views DESC
LIMIT 24;
```

Q: Top channels by average views per post (min 5 posts) — can find similar creators.

```sql
SELECT
  channel_id,
  COUNT(1) AS posts,
  ROUND(AVG(view_count),0) AS avg_views,
  MAX(follower_count) AS followers
FROM
  `hs2026de.tiktok_scraper.prod_posts`
GROUP BY channel_id
HAVING posts >= 5
ORDER BY avg_views DESC
LIMIT 20;
```

Q: Get latest record per channel (use `scraped_at` to ensure freshest data).

```sql
SELECT * EXCEPT(rn) FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY channel_id ORDER BY scraped_at DESC) rn
  FROM `hs2026de.tiktok_scraper.prod_posts`
) WHERE rn = 1;
```

-- Tip: always filter by `scraped_at` when you need most-recent dataset state.

----------------------------------------------

Q: What type of games are trending now or others are playing?

```sql
SELECT
  tag AS game,
  COUNT(1) AS posts,
  ROUND(AVG(view_count),0) AS avg_views,
  ROUND(AVG(like_count),0) AS avg_likes
FROM
  `hs2026de.tiktok_scraper.prod_posts`,
  UNNEST(SPLIT(LOWER(hashtags), ',')) AS tag
WHERE
  tag != ''
  AND DATE(scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY game
ORDER BY avg_views DESC
LIMIT 50;
```

Q: What type of game should I play next? (recommend games owner hasn't played recently)

```sql
WITH global_tags AS (
  SELECT
    tag,
    ROUND(AVG(view_count),0) AS avg_views,
    COUNT(1) AS uses
  FROM `hs2026de.tiktok_scraper.prod_posts`, UNNEST(SPLIT(LOWER(hashtags), ',')) AS tag
  WHERE tag != '' AND DATE(scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  GROUP BY tag
), owner_tags AS (
  SELECT DISTINCT tag
  FROM `hs2026de.tiktok_scraper.prod_posts`, UNNEST(SPLIT(LOWER(hashtags), ',')) AS tag
  WHERE LOWER(channel_id) = 'noraspersonalspace' AND tag != '' AND DATE(scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
)
SELECT g.tag AS game, g.avg_views, g.uses
FROM global_tags g
LEFT JOIN owner_tags o ON g.tag = o.tag
WHERE o.tag IS NULL
ORDER BY g.avg_views DESC
LIMIT 20;
```

Q: Should I continue playing and make videos of `xxx` game as new series?

```sql
-- replace 'xxx' with game tag (lowercase, no #)
DECLARE GAME STRING DEFAULT 'xxx';

WITH owner_game AS (
  SELECT
    COUNT(1) AS owner_posts,
    ROUND(AVG(view_count),0) AS owner_avg_views,
    ROUND(AVG(like_count),0) AS owner_avg_likes
  FROM `hs2026de.tiktok_scraper.prod_posts`, UNNEST(SPLIT(LOWER(hashtags), ',')) AS tag
  WHERE LOWER(channel_id) = 'noraspersonalspace' AND tag = GAME AND DATE(scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
),
owner_overall AS (
  SELECT ROUND(AVG(view_count),0) AS channel_avg_views
  FROM `hs2026de.tiktok_scraper.prod_posts`
  WHERE LOWER(channel_id) = 'noraspersonalspace' AND DATE(scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
),
global_game AS (
  SELECT ROUND(AVG(view_count),0) AS global_avg_views, COUNT(1) AS global_posts
  FROM `hs2026de.tiktok_scraper.prod_posts`, UNNEST(SPLIT(LOWER(hashtags), ',')) AS tag
  WHERE tag = GAME AND DATE(scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
)
SELECT
  o.owner_posts,
  o.owner_avg_views,
  o.owner_avg_likes,
  os.channel_avg_views AS owner_channel_avg,
  g.global_avg_views,
  g.global_posts,
  CASE WHEN os.channel_avg_views = 0 THEN NULL ELSE ROUND(100 * (o.owner_avg_views - os.channel_avg_views) / os.channel_avg_views, 1) END AS pct_vs_channel_avg
FROM owner_game o, owner_overall os, global_game g;
```

-- Use `scraped_at` filter to ensure recommendations based on freshest data.

-------------------------------------------

Q: Show top posts with owner info (display name, followers).

```sql
SELECT
  p.video_id,
  p.title,
  p.view_count,
  p.like_count,
  u.display_name,
  u.follower_count,
  p.scraped_at
FROM
  `hs2026de.tiktok_scraper.prod_posts` p
LEFT JOIN
  `hs2026de.tiktok_scraper.prod_users` u
ON p.channel_id = u.channel_id
WHERE
  DATE(p.scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
ORDER BY p.view_count DESC
LIMIT 50;
```

Q: Find trending games among creators with >10k followers.

```sql
SELECT
  tag AS game,
  COUNT(1) AS posts,
  ROUND(AVG(p.view_count),0) AS avg_views
FROM
  `hs2026de.tiktok_scraper.prod_posts` p,
  UNNEST(SPLIT(LOWER(p.hashtags), ',')) AS tag
JOIN
  `hs2026de.tiktok_scraper.prod_users` u
ON p.channel_id = u.channel_id
WHERE
  tag != ''
  AND u.follower_count >= 10000
  AND DATE(p.scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY game
ORDER BY avg_views DESC
LIMIT 30;
```

Q: Filter owner-device-specific trends (e.g., Mac M-series players).

```sql
SELECT
  tag AS game,
  COUNT(1) AS posts,
  ROUND(AVG(p.view_count),0) AS avg_views
FROM
  `hs2026de.tiktok_scraper.prod_posts` p,
  UNNEST(SPLIT(LOWER(p.hashtags), ',')) AS tag
JOIN
  `hs2026de.tiktok_scraper.prod_users` u
ON p.channel_id = u.channel_id
WHERE
  tag != ''
  AND LOWER(u.device) LIKE '%mac%m%series%'
  AND DATE(p.scraped_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
GROUP BY game
ORDER BY avg_views DESC
LIMIT 30;
```

