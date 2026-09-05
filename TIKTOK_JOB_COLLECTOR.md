# TSO TikTok Myanmar Job Collector

Adds a creator-only TikTok collector that follows the same pipeline as Facebook:

1. Import a TikTok URL plus caption/transcript manually, or sync public Myanmar videos through an **approved TikTok Research API** project.
2. TSO AI extracts the job into the normal TSO job schema and evaluates scam risk.
3. High-confidence/low-risk posts are auto-published; uncertain posts enter creator review; scam verdicts stay hidden.
4. Source URL/video ID and a content hash are retained for audit and duplicate prevention.

## Environment
- `TIKTOK_RESEARCH_TOKEN` — approved TikTok Research API client access token.
- `TIKTOK_JOB_KEYWORDS` — comma-separated Burmese/English job keywords.
- `TIKTOK_SYNC_LIMIT` — default 25.
- `TIKTOK_AUTO_PUBLISH_CONFIDENCE` — default 0.92.
- `TIKTOK_AUTO_PUBLISH_MAX_RISK` — default 0.12.

## TikTok access limitation
The system does **not** scrape TikTok pages, cookies, passwords, or bypass platform controls. TikTok's current Research API can query public video data, but access requires an approved Research Tools project; ordinary Display API access is for an authorized user's own public videos. Therefore the server only enables automatic public-content search when `TIKTOK_RESEARCH_TOKEN` is configured and approved. Manual URL/caption import is always available to the creator.

## Myanmar targeting
Automatic Research API searches use `region_code=MM` plus the configured job keywords. TikTok's API availability and eligibility can change, so the system treats the API as optional and fails safely when access is unavailable.
