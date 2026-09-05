-- TSO Facebook job collector metadata
CREATE INDEX IF NOT EXISTS idx_jobs_source_platform
ON jobs ((data->>'sourcePlatform'));
CREATE INDEX IF NOT EXISTS idx_jobs_collector_status
ON jobs ((data->>'collectorStatus'));
CREATE INDEX IF NOT EXISTS idx_jobs_source_hash
ON jobs ((data->>'sourcePostHash'));
