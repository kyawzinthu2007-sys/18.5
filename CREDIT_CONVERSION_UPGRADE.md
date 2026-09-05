# TSO Credit Conversion Upgrade

This release upgrades the existing Credit system without removing the existing features or payment workflow.

## Included
- Credit Wallet-style Tasks page with low-balance messaging.
- Package cards that explain practical value (analysis/generation capacity and cost per Credit).
- 50-Credit starter package highlighted as the default recommendation.
- First approved paid Credit purchase receives a one-time +5 Credit bonus.
- Server-backed `/api/credit/insights` endpoint with usage counts, login streak, spending and package recommendation.
- Personalized package recommendation based on actual Credit transaction usage.
- 7-day login streak display based on real daily-login transactions.
- Credit conversion/value section explaining what 2/3 Credit purchases accomplish.
- Direct "Get Credit" links from TSO Edu analysis/generation when balance is insufficient.
- `/?credit=1` deep link opens the Credit Wallet directly after sign-in.
- Low Credit messaging after job-post payment failures.
- Existing manual KBZ Pay / UAB Pay / AYA Pay screenshot verification remains intact.
- Existing Tasks, referral, promo-code and leaderboard rewards remain intact.

## Important
The payment flow remains manual: the user transfers the exact amount, uploads proof, and a creator/admin approves the purchase. No live payment gateway was introduced.
