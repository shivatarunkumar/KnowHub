-- Typed view over the raw events. This is what dashboards and the app query.
-- Adding a field to an event only needs a change here, never a re-ingest.

CREATE OR REPLACE VIEW `${project}.${dataset}.events` AS
SELECT
  message_id                                              AS event_id,
  JSON_VALUE(data, '$.event_type')                        AS event_type,
  COALESCE(
    SAFE.PARSE_TIMESTAMP('%FT%H:%M:%E*SZ', JSON_VALUE(data, '$.occurred_at')),
    publish_time)                                         AS occurred_at,
  JSON_VALUE(data, '$.video_id')                          AS video_id,
  JSON_VALUE(data, '$.owner_id')                          AS owner_id,
  JSON_VALUE(data, '$.user_id')                           AS user_id,
  JSON_VALUE(data, '$.session_id')                        AS session_id,
  JSON_VALUE(data, '$.video_type')                        AS video_type,
  JSON_VALUE(data, '$.topic_slug')                        AS topic_slug,
  SAFE_CAST(JSON_VALUE(data, '$.position_sec') AS INT64)  AS position_sec,
  SAFE_CAST(JSON_VALUE(data, '$.watch_seconds') AS INT64) AS watch_seconds,
  publish_time                                            AS ingested_at,
  data                                                    AS payload_json
FROM `${project}.${dataset}.events_raw`;
