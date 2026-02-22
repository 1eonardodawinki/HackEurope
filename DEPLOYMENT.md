# Deployment + CI/CD

This repo is configured for automatic deployment from `main`:

- CI workflow: `.github/workflows/ci.yml`
- Deploy workflow: `.github/workflows/deploy.yml`

## 1) One-time hosting setup

Deploy this repo as a Docker service (Render/Railway/Fly). The root `Dockerfile` already builds frontend and serves it from backend.

Set required runtime env vars in your hosting provider:

- `ANTHROPIC_API_KEY`
- `VITE_MAPBOX_TOKEN` (build-time arg if needed by platform)
- `AISSTREAM_API_KEY` (optional if demo mode)
- `GFW_API_TOKEN`
- `NEWS_API_KEY`
- `SUPABASE_URL` (optional)
- `SUPABASE_SERVICE_KEY` (optional)
- `DEMO_MODE` (optional, `true`/`false`)

Add persistent storage and ensure these files exist at runtime:

- `/app/historical_unmatched.db`
- `/app/vessel_data.db`

## 2) Deploy hook secret

Create a deploy hook URL in your hosting platform, then add it in GitHub:

- Repository -> Settings -> Secrets and variables -> Actions
- New repository secret:
  - Name: `DEPLOY_HOOK_URL`
  - Value: `<your platform deploy webhook URL>`

## 3) How it works

1. Push or PR runs `CI`
2. If CI succeeds on branch `main`, `Deploy` runs automatically
3. `Deploy` calls your deploy hook URL
4. Host rebuilds and releases latest commit

## 4) Recommended branch protection

Enable branch protection for `main` and require `CI` to pass before merge.
