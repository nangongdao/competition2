# Add local API key config files

## Goal

Make provider API key setup easier and safer for local endurance baselines by
using a local ignored environment file for real secrets and a tracked template
file for GitHub.

## What I Already Know

- The user prefers a file-based setup instead of typing provider keys directly
  into each PowerShell session.
- The user explicitly suggested two matching files: one local file for real
  use, and one pullable file for GitHub.
- `.gitignore` already ignores `.env` and `.env.local`.
- `backend/requirements.txt` already includes `python-dotenv`.
- `backend/.env.example` already exists as a tracked template.
- `backend/core/config.py` currently uses `env_file = ".env"`, which depends on
  the process working directory.
- The desktop launcher starts the backend with `cwd=backend`, while tools such
  as `tools/endurance_preflight.py` usually run from the repository root.

## Requirements

- Add a clear local secret file path: `backend/.env.local`.
- Keep a matching tracked template at `backend/.env.example`.
- Do not commit real API keys.
- Make backend settings load env files from explicit repository paths, not from
  whichever directory the command happens to run in.
- Preserve existing `.env` compatibility where practical.
- Document exactly where the user should fill keys.
- Avoid a frontend UI for secrets in this task because browser-visible keys are
  unsafe for provider credentials.

## Acceptance Criteria

- [x] `backend/.env.example` tells users to copy/fill `backend/.env.local`.
- [x] `backend/.env.local` exists locally with placeholders and remains ignored
      by Git.
- [x] Backend settings read `backend/.env.local` when tools run from the repo
      root or the backend directory.
- [x] Environment variables still override dotenv values.
- [x] Tests cover dotenv file precedence and environment override behavior.
- [x] README explains the two-file setup for provider keys.

## Out of Scope

- Building a frontend settings screen for API keys.
- Encrypting local secrets.
- Calling real provider APIs during tests.

## Technical Notes

- Likely files: `backend/core/config.py`, `backend/.env.example`, `README.md`,
  and a focused backend config test.
- Existing preflight is already secret-safe: it checks key presence without
  printing or storing secret values.
