-- Run this in the Supabase SQL Editor (https://app.supabase.com → your project → SQL Editor)

CREATE TABLE IF NOT EXISTS inquiries (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT      NOT NULL,
    username    TEXT,
    message     TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'resolved')),
    admin_reply TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_inquiries_user_id    ON inquiries (user_id);
CREATE INDEX IF NOT EXISTS idx_inquiries_status     ON inquiries (status);
CREATE INDEX IF NOT EXISTS idx_inquiries_created_at ON inquiries (created_at DESC);

-- Optional: enable Row Level Security (RLS) if you want per-user data isolation
-- ALTER TABLE inquiries ENABLE ROW LEVEL SECURITY;
