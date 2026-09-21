-- Aggregates used by the Studio dashboard and the home page's Trending row.

-- Per video per day: views, unique viewers, watch time, completions.
CREATE OR REPLACE VIEW `${project}.${dataset}.daily_video_stats` AS
SELECT
  DATE(occurred_at)                                                   AS day,
  video_id,
  ANY_VALUE(video_type)                                               AS video_type,
  ANY_VALUE(topic_slug)                                               AS topic_slug,
  COUNTIF(event_type = 'video_view')                                  AS views,
  COUNT(DISTINCT IF(event_type = 'video_view',
                    COALESCE(user_id, session_id), NULL))             AS unique_viewers,
  COUNTIF(event_type = 'video_complete')                              AS completions,
  COUNTIF(event_type = 'video_like')                                  AS likes,
  COUNTIF(event_type = 'video_share')                                 AS shares,
  SUM(IF(event_type = 'video_progress', watch_seconds, 0))            AS watch_seconds
FROM `${project}.${dataset}.events`
WHERE video_id IS NOT NULL
GROUP BY day, video_id;

-- Trending over the last 7 days: views weighted by engagement, recent days count more.
CREATE OR REPLACE VIEW `${project}.${dataset}.trending_7d` AS
SELECT
  video_id,
  ANY_VALUE(video_type)  AS video_type,
  ANY_VALUE(topic_slug)  AS topic_slug,
  SUM(views)             AS views,
  SUM(unique_viewers)    AS unique_viewers,
  SUM(watch_seconds)     AS watch_seconds,
  ROUND(SUM(
    (views + 3 * likes + 5 * shares + 2 * completions) *
    -- a day-old view counts ~0.9, a week-old one ~0.5
    POW(0.9, DATE_DIFF(CURRENT_DATE(), day, DAY))
  ), 2)                  AS trending_score
FROM `${project}.${dataset}.daily_video_stats`
WHERE day >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY video_id
ORDER BY trending_score DESC;
