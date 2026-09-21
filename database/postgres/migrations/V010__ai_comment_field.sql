-- The writing assist now also works on comments, so ai_requests.field accepts 'comment'.

ALTER TABLE ai_requests DROP CONSTRAINT ai_requests_field_check;
ALTER TABLE ai_requests ADD CONSTRAINT ai_requests_field_check
    CHECK (field IN ('title', 'description', 'tags', 'comment'));
