-- TSO TikTok job collector metadata
CREATE INDEX IF NOT EXISTS idx_jobs_tiktok_video_id
ON jobs ((data->>'sourceVideoId'));
CREATE INDEX IF NOT EXISTS idx_jobs_tiktok_source_hash
ON jobs ((data->>'sourcePostHash'));
