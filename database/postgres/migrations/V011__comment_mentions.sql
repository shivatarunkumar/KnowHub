-- @mentions in comments: the mentioned person gets a notification.

ALTER TABLE notifications DROP CONSTRAINT notifications_type_check;
ALTER TABLE notifications ADD CONSTRAINT notifications_type_check
    CHECK (type IN (
        'new_video_topic', 'new_video_channel', 'comment_reply', 'comment_mention',
        'video_shared', 'video_ready', 'video_failed'));
