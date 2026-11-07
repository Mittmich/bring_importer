---
title: Import from a PDF document and from several photos
status: done
created: 2026-11-07
updated: 2026-11-07
---

## Goal

1. **Several photos → one recipe** (e.g. a recipe spread over two cookbook pages, or ingredients
   and method on separate screenshots).
2. **Import from a PDF** (saved recipe, cookbook excerpt, scanned page).

## Approach

- `POST /recipes/parse` accepts the `image` form field up to 8 times; all images go to the model
  in one call ("parts of the same recipe"). Training-data collection only for single-image
  imports (dataset stays one image ↔ one recipe).
- `POST /recipes/import-document` — multipart `file` (PDF, ≤ 15 MB, must start with `%PDF-`),
  optional `language`, `note`. Sent to the model as a native file input (text + page images), so
  no new Python dependency. Stored with `source = {"kind": "document", "value": <filename>}`.
- nginx: `client_max_body_size 20m` and a 120 s read timeout for `/api/` (default 1 MB would
  reject several photos or a PDF).
- Frontend: photo dialog takes several images (thumbnails, remove, add more, max 8); new
  "From a document (PDF)" card in the add chooser + `ImportDocumentModal`; `send()` leaves the
  Content-Type to the browser for `FormData`.

## Steps

- [x] Backend extraction + routes + tests
- [x] nginx template
- [x] Frontend: multi-image dialog, document dialog, chooser, i18n en/de
- [x] Lint, ty, tests, eslint, build; browser check with a fake OpenAI server

## Outcome

- `parse_recipe_with_openai` takes 1–8 images (one call, "parts of ONE recipe" prompt);
  `parse_recipe_from_pdf` sends the PDF as a native `file` part. Shared `_extract_recipe`.
- `POST /recipes/parse` repeats the `image` field (>8 → 422); `POST /recipes/import-document`
  (multipart; not a PDF → 422, > 15 MB → 413, AI failure → 500 with a clear message).
- nginx `/api/`: `client_max_body_size 20m`, `proxy_read_timeout 120s`.
- UI: "From photos" dialog with numbered thumbnails, remove, "Add another photo" (max 8);
  "From a document" card + dialog; document recipes show a file badge with the filename.
- 7 new tests (404 total). Browser check (desktop + 500 px) against a fake OpenAI server: 2 photos
  in one call, PDF sent as a file, non-PDF rejected, source badge shown.
- Not verified: the real model's PDF reading; the nginx limit (only takes effect on deploy).
