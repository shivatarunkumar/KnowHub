-- Landing table for the Pub/Sub → BigQuery subscription on the analytics-events topic.
--
-- A BigQuery subscription without a Pub/Sub schema writes the message body into a
-- column named `data`, plus metadata columns when "write metadata" is enabled. Keeping
-- the raw JSON means a new event field never breaks ingestion: the parsing happens in
-- the `events` view (002), which we can change any time.

CREATE TABLE IF NOT EXISTS `${project}.${dataset}.events_raw`
(
  data              STRING     OPTIONS(description = "event payload as JSON"),
  subscription_name STRING,
  message_id        STRING,
  publish_time      TIMESTAMP,
  attributes        STRING     OPTIONS(description = "Pub/Sub message attributes as JSON")
)
PARTITION BY DATE(publish_time)
CLUSTER BY message_id
OPTIONS (
  description = "Raw KnowHub analytics events delivered by Pub/Sub",
  partition_expiration_days = 400
);
