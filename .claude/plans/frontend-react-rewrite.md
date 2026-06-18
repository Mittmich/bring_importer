---
name: frontend-react-rewrite
status: active
---

# Frontend React Rewrite

## Goal

Replace the vanilla HTML/JS + Bootstrap frontend with a React + Vite app using the **Clean & Sharp** design direction (white canvas, Indigo accent, Inter, Notion/Linear aesthetic). Ingredients and instructions clearly separated in recipe detail. Proper sidebar navigation. **Must look and work well on mobile.**

## Design reference

`.claude/design-mockups/2-clean-sharp.html` — the chosen design. Key traits:
- White/light-gray background (#FFFFFF / #F8FAFC)
- Indigo accent (#6366F1)
- Inter font throughout
- Three-column layout on desktop: sidebar (220px) · recipe list (300px) · recipe detail (flex)
- Ingredient grid (2-col) + numbered instruction steps, in separate cards
- Flat nav items with rounded active state
- **Mobile:** three columns collapse to a single-column stack with bottom navigation bar; recipe list and detail are separate full-screen views navigated by React Router

## Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Framework | React 18 + Vite | Fast build, first-class TS support |
| Styling | Tailwind CSS + shadcn/ui | Ships the Clean & Sharp look out of the box |
| Routing | React Router v6 | Standard, works well with Vite |
| Data fetching | TanStack Query | Caching, loading states, auth error handling |
| Runtime env | `window.ENV` via `public/env-config.js` | Same nginx sub_filter injection, zero changes to backend or nginx |

## Directory plan

```
frontend-react/           ← new Vite project (replaces frontend/)
  public/
    env-config.js         ← runtime env vars injected by nginx sub_filter
    manifest.json
    images/
  src/
    main.tsx
    App.tsx               ← Router + QueryClient + AuthProvider
    lib/
      api.ts              ← typed fetch helpers (wraps config.apiUrl)
      config.ts           ← reads window.ENV (same logic as old config.js)
    hooks/
      useAuth.ts
      useRecipes.ts
    components/
      ui/                 ← shadcn/ui primitives (Button, Dialog, Input…)
      AppShell.tsx        ← sidebar (desktop) + bottom nav (mobile) + outlet layout
      Sidebar.tsx         ← desktop only (hidden on mobile)
      BottomNav.tsx       ← mobile only (fixed bottom bar)
      RecipeListPanel.tsx
      RecipeCard.tsx
      RecipeDetail.tsx
      ImportPhotoModal.tsx
      ImportUrlModal.tsx
    pages/
      LoginPage.tsx
      HomePage.tsx        ← recent recipes + import buttons
      RecipesPage.tsx     ← full list
      RecipeDetailPage.tsx
      EditRecipePage.tsx
  index.html
  vite.config.ts
  tailwind.config.ts
  components.json         ← shadcn/ui config
```

## Steps

### ✅ 1. Bootstrap Vite + React project

```bash
npm create vite@latest frontend-react -- --template react-ts
cd frontend-react
npm install
```

Install dependencies:
```bash
npm install react-router-dom @tanstack/react-query
npm install -D tailwindcss @tailwindcss/vite
npx shadcn@latest init        # select: New York style, Indigo, yes CSS vars
npx shadcn@latest add button dialog input textarea badge separator
```

Configure Vite to build into `dist/` (default is fine). Add `tailwind.config.ts` and `@tailwindcss/vite` plugin.

### ✅ 2. Runtime env config

Copy `env-config.js` to `frontend-react/public/env-config.js` — unchanged. Add `<script src="/env-config.js"></script>` before the React bundle in `index.html`.

Create `src/lib/config.ts` (port of old `config.js`):
```ts
export const config = {
  apiUrl: (window.ENV?.API_URL && !/^\{\{/.test(window.ENV.API_URL)
    ? window.ENV.API_URL
    : localStorage.getItem('API_URL') ?? 'http://localhost:8001'
  ).replace(/\/$/, ''),
};
```

### ✅ 3. Auth layer

- `src/hooks/useAuth.ts` — token in `localStorage`, decode JWT for email
- `<AuthProvider>` wrapping the router — redirects to `/login` when no token
- `LoginPage.tsx` — email + password form, POST `/api/token`, store token

### ✅ 4. App shell + navigation

Implement `AppShell.tsx` with responsive layout:

**Desktop (md+):** three-column layout from the mockup — `Sidebar` (220px) · recipe list panel (300px) · recipe detail (flex). Sidebar shows Home · All Recipes · Import · Account/Logout with active-route indigo highlight.

**Mobile (< md):** full-width single column. `Sidebar` is hidden. A `BottomNav` (fixed, 56px) shows icon-only tabs: Home · Recipes · Import · Account. Recipe list and detail are separate routes that each fill the screen — no side-by-side panels. Back navigation handled by React Router history.

### ✅ 5. Recipe list panel

`RecipeListPanel.tsx`:
- Fetches `GET /api/recipes` via TanStack Query
- Search input at top
- List rows: name, serving count, time, relative date, `›` arrow
- Active recipe highlighted (indigo tint) on desktop
- Clicking a row navigates to `/recipes/:id` (on mobile this replaces the full screen; on desktop it populates the detail column)
- On mobile: renders full-screen, bottom nav provides navigation out

### ✅ 6. Recipe detail

`RecipeDetail.tsx` (renders inside the detail column on desktop, full-screen on mobile):
- Title, meta chips (servings, time)
- Edit + Add to Bring action buttons
- Two separate white cards:
  - **Ingredients card** — 2-column grid on desktop, 1-column on mobile, with indigo dot bullets
  - **Instructions card** — numbered steps (indigo `01 02 03` labels)
- Add-to-Bring uses the existing Bring widget script
- Mobile: sticky header with back arrow (`←`) to return to the recipe list

### ✅ 7. Import modals

Convert the two Bootstrap modals to shadcn/ui `<Dialog>`:
- `ImportPhotoModal` — file input + camera capture → POST `/api/parse-photo`
- `ImportUrlModal` — URL + note → POST `/api/parse-url`
- After success, open preview then redirect to new recipe detail

### ✅ 8. Edit recipe page

`EditRecipePage.tsx` — form with:
- Name, servings, time fields (`<Input>`)
- Ingredients: one per line textarea (or dynamic list)
- Instructions: textarea (or dynamic list)
- Save → PATCH `/api/recipes/:id`

### ✅ 9. Docker / nginx wiring

Update `docker-compose.yml` nginx volume:
```yaml
- ./frontend-react/dist:/usr/share/nginx/html:ro
```

Add a pre-build step to CI (`npm run build` in `frontend-react/`) so the dist is always fresh on deploy.

Update deploy workflow to run `npm ci && npm run build` in `frontend-react/` before `docker compose up`.

### ✅ 10. Cleanup

- Remove old `frontend/` directory (after confirming new app works end-to-end)
- Update `AGENTS.md` repo map
- Rename `frontend-react/` → `frontend/` and update all docker-compose paths

## Out of scope (this PR)

- Pagination / infinite scroll on recipe list
- Tags / categories
- Recipe image upload
- Offline mode / service worker (can be added after)

## Notes

- The Bring widget (`https://platform.getbring.com/widgets/import.js`) is loaded as a `<script>` in `index.html` — same as before.
- Keep `window.ENV` / nginx sub_filter approach unchanged — no Vite env var magic at build time for secrets.
- `manifest.json` and PWA icons go in `public/` and are served as-is by nginx.
