CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY,
    creator_id UUID NOT NULL,
    video_created_at TIMESTAMPTZ NOT NULL,
    views_count BIGINT NOT NULL DEFAULT 0,
    likes_count BIGINT NOT NULL DEFAULT 0,
    comments_count BIGINT NOT NULL DEFAULT 0,
    reports_count BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_videos_creator_date
    ON videos (creator_id, video_created_at);

CREATE INDEX IF NOT EXISTS idx_videos_views
    ON videos (views_count DESC);

CREATE INDEX IF NOT EXISTS idx_videos_likes
    ON videos (likes_count DESC);

CREATE TABLE IF NOT EXISTS video_snapshots (
    id UUID PRIMARY KEY,
    video_id UUID NOT NULL REFERENCES videos(id),
    views_count BIGINT,
    likes_count BIGINT,
    comments_count BIGINT,
    reports_count BIGINT,
    delta_views_count BIGINT,
    delta_likes_count BIGINT,
    delta_comments_count BIGINT,
    delta_reports_count BIGINT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_snapshots_video_time
    ON video_snapshots (video_id, created_at);

CREATE INDEX IF NOT EXISTS idx_snapshots_views
    ON video_snapshots (views_count DESC);
