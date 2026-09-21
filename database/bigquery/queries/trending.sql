-- Home page → trending videos (used by GET /videos/trending).
-- Parameters: @video_type ('video' | 'short' | NULL for both), @limit
SELECT video_id, views, unique_viewers, watch_seconds, trending_score
FROM `${project}.${dataset}.trending_7d`
WHERE (@video_type IS NULL OR video_type = @video_type)
LIMIT @limit;
