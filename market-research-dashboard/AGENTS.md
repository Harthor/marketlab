# market-research-dashboard — AGENTS.md

## Non-negotiables
- Do not edit outside this repo.
- Runs listing must be manifest-driven:
  - correlation: reports/*/summary.json
  - forecast: runs/*/run_summary.json
- Demo mode must conform to the same manifest schema as real mode.

## Frontend setup
- Use the lockfile present (npm/pnpm/yarn). Prefer reproducible installs:
  - npm ci OR pnpm i --frozen-lockfile OR yarn install --frozen-lockfile
- Build:
  - npm run build (or pnpm/yarn equivalent)

## Backend setup
- If Python backend exists, ensure it can start and serve /api endpoints (dev CORS ok).
- If deps cannot be installed in this environment, clearly mark BLOCKED and keep demo mode working.

## Definition of Done
- UI can list runs from manifests and open table/plot via artifacts paths
- Demo mode uses the exact same schema shape as real mode
