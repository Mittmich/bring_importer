---
name: zest-branding
status: done
updated: 2026-11-05
---

# Rebrand to "Zestry"

## Goal

On 2026-11-05 the user picked option J, "Zest", from the branding mockups
(scratchpad `design-options/branding-more.html`): a citrus-slice mark and brand orange `#f08a24`.
"Zest" already exists, so the user picked the variation **"Zestry"** (zest + pantry), from
`design-options/zest-names.html`. It is the one name everywhere.

## Design

- **Name:** "Zestry" in the in-app title (en/de), browser tab, Apple title, PWA manifest
  (`name`/`short_name`) and the PDF "Exported from …" line. The name is the same in German.
- **Colour:**
  - `#f08a24` (bright orange) for the icon tile and `theme-color`.
  - UI primary `#bf560b` (hsl 25 89% 40%), so white text on buttons stays readable
    (4.6:1, a little above today's indigo at 4.47:1).
  - Tag chips follow the primary colour.
- **Icons:**
  - Generated from the mark with Pillow at 8× and downsampled.
  - `icon-192/512.png` (rounded tile, purpose `any`).
  - `icon-maskable-192/512.png` (full bleed, mark inside the 80 % safe zone).
  - `apple-touch-icon.png` (180, full bleed).
  - `favicon.svg`.
- **Logo:** a `BrandMark` component replaces the small square next to the app name in the
  sidebar, login page and sign-up/reset pages.

## Steps

- [x] 1. Name in i18n (frontend + backend PDF), index.html, manifest, README heading
- [x] 2. Colours: primary/ring CSS vars, tag colour, theme-color
- [x] 3. Icon files + favicon + manifest/index.html links
- [x] 4. `BrandMark` in sidebar, login and link pages
- [x] 5. Tests, typecheck/lint/build, check the rendered icons

## Outcome

- **Name:** "Zestry" in en/de `common.appName`, `<title>`, the Apple title, the manifest
  (`name`, `short_name`, new description), the PDF "Exported from Zestry" line and the README
  heading.
- **Colours:**
  - UI primary and ring are `hsl(25 89% 40%)` (`#bf560b`).
  - Tags use `#bf560b`.
  - `theme-color` is `#f08a24`.
- **Icons:**
  - Rendered with Pillow as a citrus slice: white rind, pale wedges and orange segment gaps
    (the thin-spoke version from the mockup read like a wheel at full size).
  - Files: `icon-192/512.png` (rounded, `any`), `icon-maskable-192/512.png` (full bleed, mark
    at 52 %), `apple-touch-icon.png` (180) and `favicon.svg`.
  - `index.html` now links the SVG favicon and the Apple icon.
- **Logo:** `components/BrandMark.tsx` (the same artwork as the icon) in the sidebar, the login
  page and the sign-up/reset pages.
- **Checks:** 361 backend tests pass; tsc and build pass; eslint stays at the 18-error baseline.
- **Not verified:** a visual check of the UI in a browser.
