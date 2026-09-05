# TSO Edu Myanmar Language — New Tab

## URLs
- English: `https://talentshowoff.com/edu`
- Myanmar: `https://talentshowoff.com/edu/lang=my`

## Behavior
- Clicking **မြန်မာ** from the English TSO Edu page opens `/edu/lang=my` in a new browser tab.
- The existing English tab stays open and unchanged.
- Clicking **English** from the Myanmar tab opens `/edu/` in a new browser tab.
- The URL-selected language is authoritative for the newly opened tab.
- The same login/session, TSO Credits, essays, and Supabase-backed data are shared; only the UI language changes.

## Deployment
No database migration or new environment variable is required. Deploy the updated application and the two URLs will be available automatically.
