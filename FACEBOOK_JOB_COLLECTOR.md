# TSO Facebook Job Collector

## What it does
1. Imports authorized/public Facebook job posts (manual paste or Meta Graph API feed IDs).
2. Sends the text to the configured TSO AI provider.
3. Extracts a normalized job listing and assigns `verdict`, `confidence`, and `risk_score`.
4. Low-risk/high-confidence posts are automatically converted to the normal TSO job format and approved.
5. Suspicious or incomplete posts remain in the normal creator moderation queue.
6. Scam verdicts are stored as rejected and are not public.

## Environment
- `GROQ_API_KEY` — existing TSO AI key.
- `FACEBOOK_GRAPH_TOKEN` — Meta Graph API access token for resources your app is authorized to access.
- `FACEBOOK_FEED_IDS` — comma-separated authorized Page/feed IDs.
- `FACEBOOK_SYNC_LIMIT` — default 25.
- `FB_AUTO_PUBLISH_CONFIDENCE` — default 0.92.
- `FB_AUTO_PUBLISH_MAX_RISK` — default 0.12.

## Facebook restrictions
Do not scrape private groups, use Facebook passwords/cookies, bypass access controls, or collect data that the Meta platform does not authorize your application to access. For groups, use an officially supported Meta integration if your app/account has the required permissions; otherwise use the manual importer.

## Important safety
AI classification is probabilistic. "AI verified" means only that the post passed the configured automated screening threshold; it is not proof that the employer or vacancy is genuine. For a production system, keep human review enabled for high-value/suspicious listings and retain the original source URL/text for audit.
