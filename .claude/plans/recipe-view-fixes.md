---
name: recipe-view-fixes
status: done
---

# Recipe View Fixes: Public Page Parity, Bottom-Bar Reload, Keep-Awake Button

## Goals

1. Fix the public sharing page ([PublicRecipePage.tsx](frontend-react/src/pages/PublicRecipePage.tsx)):
   - It cannot scroll.
   - Serving amount cannot be adjusted (static, no scaling).
   - The ingredient collapse toggle is missing.
2. Fix the mobile bottom nav vanishing after a pull-to-refresh reload (must scroll to see it again).
3. Add a "keep screen awake" toggle button to the recipe detail view so the phone
   display does not dim while cooking.

---

## Background / Root Causes

- `#root` is `height: 100dvh; overflow: hidden` ([index.css:43-46](frontend-react/src/index.css#L43-L46)).
  Inside the app, [RecipeDetail.tsx](frontend-react/src/components/RecipeDetail.tsx) handles this with a
  `flex flex-col h-full` wrapper whose body is `flex-1 overflow-y-auto`.
  But `PublicRecipePage` is a **standalone route** ([App.tsx:37](frontend-react/src/App.tsx#L37)) whose root is
  just `min-h-screen` — its overflow is clipped by `#root`, so it cannot scroll. **This is the scroll bug.**
- The public page renders the serving as a static `🍽 {recipe.recipeYield}` span and ingredients always-open,
  whereas `RecipeDetail` has a +/- servings control with live scaling and a mobile collapse toggle.
- The serving-scaling helpers (`parseServings`, `servingsUnit`, `formatAmount`, `scaleText`, `formatIngredient`)
  currently live **only** inside `RecipeDetail.tsx` — must be shared to avoid duplication.
- **Bottom bar bug:** the [BottomNav](frontend-react/src/components/BottomNav.tsx) is the last flex child of a
  `100dvh`-tall root. `dvh` tracks the *dynamic* viewport; during a pull-to-refresh the browser shows its
  address-bar chrome, and the layout (sized to the chrome-hidden height) overflows the visible area, pushing
  the nav below the fold until you scroll. Pull-to-refresh overscroll compounds it.

---

## Step 1 — Extract scaling helpers to a shared module

Create `frontend-react/src/lib/scaling.ts` and move from [RecipeDetail.tsx:9-57](frontend-react/src/components/RecipeDetail.tsx#L9-L57):
- `parseServings`, `servingsUnit`, `formatAmount`, `scaleText`, `formatIngredient(ing, scale)`.

Update `RecipeDetail.tsx` to import these instead of defining them locally (pure refactor, behavior unchanged).

## Step 2 — Fix the bottom nav on reload

In [index.css](frontend-react/src/index.css#L43-L46), make the app shell always reserve room for browser chrome:
- Change `#root` height from `100dvh` to `100svh` (small viewport height = chrome-visible, smallest height),
  so the bottom nav is guaranteed to fit regardless of chrome state.
- Add `overscroll-behavior-y: none` (on `body`/`#root`) to suppress the pull-to-refresh overscroll that
  triggers the reflow.
- Verify the existing `safe-area-bottom` padding on the nav still renders correctly with `svh`.

*Note:* `svh` trades a little unused space when chrome is hidden for a nav that never disappears — the right
call for a fixed bottom bar. Test on the real device after the change.

## Step 3 — Add a `useWakeLock` hook

Create `frontend-react/src/hooks/useWakeLock.ts` using the [Screen Wake Lock API](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API):
- Exposes `{ supported, active, toggle() }`.
- `navigator.wakeLock.request('screen')` on enable; store the `WakeLockSentinel`; `release()` on disable/unmount.
- Re-acquire on `visibilitychange` when the document becomes visible (the OS auto-releases when hidden).
- `supported = 'wakeLock' in navigator`; guard all calls; wrap `request` in try/catch (rejects on low battery /
  no user activation).

## Step 4 — Keep-awake button in RecipeDetail

In the mobile top bar of [RecipeDetail.tsx:99-115](frontend-react/src/components/RecipeDetail.tsx#L99-L115)
(and the desktop action row), add a toggle button shown only when `supported`:
- lucide icon pair, e.g. `Lightbulb` / `LightbulbOff`, with active styling (filled/primary) when held.
- `aria-pressed={active}`, label "Keep screen awake". Placed left of the share/edit buttons so it reads as
  "on top of" the detail view.

## Step 5 — Fix scrolling on the public page

In [PublicRecipePage.tsx](frontend-react/src/pages/PublicRecipePage.tsx), restructure the root from
`min-h-screen` to a self-contained scroll container, mirroring `RecipeDetail`:
- Root: `flex flex-col h-[100svh] bg-[#F8FAFC]`; keep the header bar fixed at top.
- Wrap the content (`max-w-2xl mx-auto …`) in a `flex-1 overflow-y-auto` div.
- Apply to the loading / error states so they stay centered and don't clip.

## Step 6 — Adjustable servings on the public page

- Replace the static yield span with the same +/- control from
  [RecipeDetail.tsx:123-137](frontend-react/src/components/RecipeDetail.tsx#L123-L137).
- Add `servings` state from `parseServings(recipe.recipeYield)`, compute `scale`.
- Use shared `formatIngredient(ing, scale)`; pass `scale` into the instructions list so step amounts scale
  live (`PublicInstructions` gains a `scale` prop, matching `StructuredInstructions`).

## Step 7 — Ingredient collapse toggle on the public page

- Port the mobile collapsible ingredients header from
  [RecipeDetail.tsx:211-243](frontend-react/src/components/RecipeDetail.tsx#L211-L243):
  `ingredientsOpen` state, a `md:hidden` toggle button with a rotating `ChevronDown`, body
  `${ingredientsOpen ? '' : 'hidden'} md:block`.

## Step 8 (optional) — Keep-awake button on the public page

The shared link is a likely "cook from someone else's link" surface; add the same keep-awake button to its
header bar ([PublicRecipePage.tsx:64-85](frontend-react/src/pages/PublicRecipePage.tsx#L64-L85)).
*(Default: include.)*

---

## Verification

- `cd frontend-react && npm run build` (typecheck) + lint.
- Manual (real Android device, the reported environment):
  - `/share/:uuid` scrolls; servings +/- scales ingredient and step amounts; ingredients collapse/expand on mobile.
  - Pull-to-refresh on the recipe list/detail — bottom nav stays visible, no scroll needed.
  - Toggle keep-awake; confirm `active` state and the screen stays on. (Wake Lock needs HTTPS + a real display.)

## Notes / Risks

- Screen Wake Lock requires a secure context (HTTPS) and is unsupported on some browsers — the button is
  hidden when `!supported`, so no broken UI on desktop/unsupported.
- `svh` is widely supported (Safari 15.4+, Chrome 108+); fine for this PWA's targets.
- Helper extraction is a pure refactor; keep behavior identical to avoid detail-view regressions.

## Outcome

Implemented all steps. `npm run build` (tsc + vite) passes; new files are lint-clean (10 pre-existing
lint errors remain in EditRecipePage/LoginPage, untouched).

- `lib/scaling.ts` — shared servings/scaling helpers, imported by both RecipeDetail and PublicRecipePage.
- `index.css` — `#root` switched to `100svh`, added `overscroll-behavior-y: none` (body + root) → bottom
  nav no longer drops below the fold on pull-to-refresh.
- `hooks/useWakeLock.ts` + `components/KeepAwakeButton.tsx` — keep-screen-awake toggle (re-acquires on
  `visibilitychange`, hidden when unsupported). Added to RecipeDetail mobile bar + desktop row, and the
  public page header.
- `PublicRecipePage.tsx` — split into a `PublicRecipeView` child (mounted only after the recipe loads, so
  servings state initializes from the real yield). Now scrolls (`h-[100svh]` + `flex-1 overflow-y-auto`),
  has the +/- servings control with live scaling, and the mobile ingredient collapse toggle.

Pending: real-device verification on Android (wake lock needs HTTPS + a physical display).
