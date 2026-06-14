---
title: <short, verb-led summary>
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
scope: backend | frontend | fullstack | infra
---

# Plan: <short, verb-led summary>

## Context

<1–3 sentences on *why* this is being done. Link tickets/issues if mentioned.>

## Goals

- Outcome, not task
- Outcome, not task

## Non-goals

- Explicitly out of scope to prevent creep

## Steps

1. [ ] First concrete, verifiable change
2. [ ] Second step
3. [ ] Third step

## Files to touch

- `backend/...` — reason
- `frontend/...` — reason
- `?` — uncertain, to confirm during execution

## Verification

- `cd backend && ruff check . && black --check . && isort --check-only .`
- `cd backend && python3 -c "import api"`
- Manual: <describe the user-visible check>

## Notes / risks

- Open question
- Risk: <thing that could go wrong>
