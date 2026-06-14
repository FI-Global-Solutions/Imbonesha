# Imbonesha Demo Access

## Dashboard
URL: https://imbonesha.vercel.app

## API
URL: https://imbonesha-api.onrender.com
Health check: https://imbonesha-api.onrender.com/health/

## Login credentials

| Role | Email | Password |
|------|-------|----------|
| RHA Officer | demo@imbonesha.gov.rw | Demo2026! |
| Inspector | inspector1@imbonesha.gov.rw | Demo2026! |

## Important notes for the demo

- **First load after 15 min idle takes ~60 seconds** (Render cold start — the API
  is sleeping to save resources). Open the dashboard 5 minutes before any meeting.
- The keep-alive action pings the API every Monday and Thursday — if the demo is
  on another day, open the dashboard once beforehand to warm it up.
- Supabase (database) auto-pings prevent it from pausing — no action needed.

## What works in this demo

- Map with 279 change-detection flags across 9 named AOIs
- Flag detail drawer with parcel info and permit status
- Satellite imagery before/after slider (T1 2023 vs T2 2024)
- Inspector assignment and status workflow
- Reports generation (PDF)
- Mobile-responsive — works on phone browsers

## What is not live in this demo

- New change-detection jobs (ML inference) — existing flags are pre-computed
- Push notifications — requires Expo push token from a running mobile app
- Email notifications — set to console backend (no emails sent)
