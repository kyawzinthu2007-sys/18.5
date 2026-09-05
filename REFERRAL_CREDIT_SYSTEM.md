# Promode Referral Credit System

- Every user receives a permanent shareable Promode Code.
- A brand-new account can enter one existing user's code during signup.
- The new account receives 10 Credit.
- The code owner receives 10 Credit.
- Each new account can redeem a Promode Code only once.
- Self-referrals are blocked.
- Referral rewards are recorded in `tso_coin_transactions`.
- Referral code/redemption tables are concurrency-safe in PostgreSQL.
- Google-created new accounts can also use a Promode Code; the signup form also
  accepts a code and pre-fills it from `?promode=CODE`.
