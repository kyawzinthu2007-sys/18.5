# TSO Edu Vocabulary — 100,000-word upgrade

- Total vocabulary entries: **100,000** (10,000 existing + 90,000 added)
- The original curated learner cards are preserved.
- The additional 90,000 entries expand search and word-recognition coverage.
- Extended entries include CEFR-style UI buckets, Myanmar learner labels, and example templates; these metadata fields are generated reference metadata and should not be treated as dictionary-grade definitions.
- Existing vocabulary API/frontend integration remains unchanged.

## Deployment
No additional database migration is required for the local vocabulary catalogue. Commit the updated `backend/edu_app/vocabulary_data.py` and deploy normally to Railway.
