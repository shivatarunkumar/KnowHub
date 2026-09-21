-- Studio → one video's daily performance (used by GET /studio/videos/{id}/analytics).
-- Parameters: @video_id, @days
SELECT day, views, unique_viewers, watch_seconds, completions, likes, shares
FROM `${project}.${dataset}.daily_video_stats`
WHERE video_id = @video_id
  AND day >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
ORDER BY day;
