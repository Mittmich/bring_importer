import { config } from './config'
import { getLanguage } from '@/i18n/current'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${config.apiUrl}${path}`, {
    ...init,
    headers: {
      // FormData (file uploads) sets its own multipart Content-Type with the boundary.
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      // The backend localizes recipe content (titles, ingredients, steps) to this.
      'Accept-Language': getLanguage(),
      ...authHeaders(),
      ...init?.headers,
    },
  })
  if (res.status === 401) {
    localStorage.removeItem('auth_token')
    window.location.href = '/login'
    throw new ApiError(401, 'Unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body?.detail ?? `HTTP ${res.status}`)
  }
  return res
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init)
  if (res.status === 204) return undefined as T
  return res.json()
}

/** The filename from a Content-Disposition header (prefers the RFC 5987 UTF-8 form). */
function dispositionFilename(header: string | null, fallback: string): string {
  if (!header) return fallback
  const utf8 = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1])
    } catch {
      // fall through to the ASCII name
    }
  }
  return header.match(/filename="([^"]+)"/i)?.[1] ?? fallback
}

/** A tag as it appears embedded on a recipe — name plus optional explicit colour. */
export interface RecipeTag {
  name: string
  color: string | null
}

export interface RecipeListItem {
  uuid: string
  title: string
  datePublished?: string
  createdAt?: string
  source: { kind: string; value: string }
  is_public: boolean
  has_image?: boolean
  /** Relative path to the hero image (needs config.apiUrl prefix), or null. */
  image_url?: string | null
  tags?: RecipeTag[]
  /** False when the recipe is shared with me by someone else. */
  owned?: boolean
  /** Email of the recipe's owner (for "shared by …" labels). */
  owner_email?: string
  /** Display name of the owner (falls back to email server-side). */
  owner_name?: string
  /** Language of `title` (null = unknown legacy recipe). */
  language?: string | null
}

export interface TagInfo {
  id: number
  name: string
  count: number
  color: string | null
}

/** A cookbook role, weakest → strongest. */
export type CookbookRole = 'viewer' | 'editor' | 'manager' | 'owner'

export interface Cookbook {
  id: number
  name: string
  recipe_count: number
  cover_image_url?: string | null
  role?: CookbookRole
  shared?: boolean
  /** 'all' = an auto cookbook of every recipe its owner has. */
  kind?: string
  /** Only present when listCookbooks is called with a recipeUuid. */
  contains?: boolean
}

export interface CookbookDetail {
  id: number
  name: string
  recipe_count: number
  recipes: RecipeListItem[]
  role?: CookbookRole
  kind?: string
}

export interface CookbookMember {
  user_id: number
  email: string
  display_name?: string
  role: 'viewer' | 'editor' | 'manager'
  status: 'pending' | 'accepted'
}

export interface CookbookMembers {
  owner: { user_id: number; email: string; display_name?: string }
  members: CookbookMember[]
}

export interface CookbookInvitation {
  cookbook_id: number
  name: string
  owner_email: string
  owner_name?: string
  role: string
}

export interface Profile {
  email: string
  display_name: string
  /** Preferred UI/recipe language code, or null if never chosen. */
  language: string | null
  /** May open the admin area (/admin). */
  is_admin?: boolean
}

/** Friendly name for a person: their display name if set, else their email. */
export function personName(displayName?: string | null, email?: string): string {
  const n = (displayName ?? '').trim()
  return n || email || ''
}

export interface Friend {
  user_id: number
  email: string
  display_name?: string
}

export interface FriendRequest {
  id: number
  user_id: number
  email: string
  display_name?: string
  direction: 'incoming' | 'outgoing'
  created_at?: string
}

export interface RecipeListPage {
  items: RecipeListItem[]
  total: number
  limit: number
  offset: number
}

export interface ListRecipesParams {
  limit?: number
  offset?: number
  q?: string
  tags?: string[]
}

export interface Ingredient {
  amount: string  // "2 cups", "200 g", "" for "to taste"
  name: string
}

export interface MealPlanEntry {
  id: number
  date: string  // ISO 'YYYY-MM-DD'
  recipe_uuid: string
  recipe_title: string
  position: number
}

export interface ShoppingListResult {
  token: string
  items: Ingredient[]
}

export interface GoogleStatus {
  configured: boolean
  connected: boolean
  calendar_id: string | null
}

export interface GoogleCalendar {
  id: string
  summary: string
  primary?: boolean
}

export type EntrySyncState = 'synced' | 'missing' | 'unsynced'

export interface WeekSyncStatus {
  connected: boolean
  /** True when the stored Google authorization has lapsed and needs reconnecting. */
  needs_reconnect?: boolean
  statuses: Record<string, EntrySyncState>
}

export interface InstructionStep {
  text: string
  ingredients: number[]  // zero-based indices into Recipe.ingredients
}

export interface RecipeUpdate {
  title?: string
  ingredients?: Ingredient[]
  instructions?: InstructionStep[]
  recipeYield?: string
  description?: string
  note?: string
  is_public?: boolean
  tags?: string[]
  training_verified?: boolean
  /** Which language variant the content fields belong to (the loaded `language`). */
  language?: string
  /** Declare the language the base recipe is written in. */
  inLanguage?: string
  /** Optimistic concurrency: the updated_at the client loaded (409 if stale). */
  base_updated_at?: string
}

export interface Recipe {
  name: string
  ingredients: Ingredient[]
  instructions: InstructionStep[]
  recipeYield?: string
  description?: string
  source?: { kind: string; value: string }
  note?: string
  datePublished?: string
  is_public?: boolean
  owned?: boolean
  tags?: RecipeTag[]
  training_verified?: boolean
  has_image?: boolean
  /** Relative path to the hero image (needs config.apiUrl prefix), or null. */
  image_url?: string | null
  /** The viewer's role over this recipe (owner/editor/viewer/…), for gating edit UI. */
  role?: CookbookRole
  /** Email of the recipe's owner (for "shared by …" labels). */
  owner_email?: string
  /** Display name of the owner (falls back to email server-side). */
  owner_name?: string
  /** Version for optimistic-concurrency checks on save. */
  updated_at?: string
  /** Language of the base (original) content; null/absent = unknown. */
  inLanguage?: string | null
  /** Language of the content in this payload; null = unknown legacy base. */
  language?: string | null
  /** The language that was requested (the UI language). */
  requested_language?: string | null
  /** Every language this recipe has content in. */
  available_languages?: string[]
  /** False when the recipe is known to have no version in the requested language. */
  translation_available?: boolean
}

/** A user as the admin area lists them. */
export interface AdminUser {
  id: number
  email: string
  display_name: string
  is_admin: boolean
  disabled: boolean
  /** ISO timestamps; null for users created before this was tracked / never logged in. */
  created_at: string | null
  last_login_at: string | null
  /** Email of the admin whose invite they used. */
  invited_by: string | null
  recipe_count: number
  /** The admin looking at the list. */
  is_self: boolean
}

export type InviteStatus = 'active' | 'used' | 'expired' | 'revoked'

export interface Invite {
  id: number
  /** Locked to this address, or null for an open invite. */
  email: string | null
  note: string
  created_at: string
  expires_at: string
  created_by: string | null
  used_by: string | null
  used_at: string | null
  status: InviteStatus
}

/** What a one-time link is for (public, before signing up / resetting). */
export interface LinkInfo {
  kind: 'signup' | 'reset'
  email: string | null
}

// --- Menus with prep planning ------------------------------------------------
// Times are minutes after midnight; durations and leads are minutes.

export type PlannerMode = 'weekly' | 'menus'

export interface Features {
  planner: PlannerMode
}

export type Equipment = '' | 'oven' | 'stove' | 'fridge'

export interface MenuCourse {
  id: number
  recipe_uuid: string
  recipe_title: string
  recipe_yield: string
  /** Servings the recipe is written for (parsed from its yield). */
  servings: number
  name: string
  serve: number
  position: number
}

export interface MenuStep {
  id: number
  course_id: number
  name: string
  duration: number
  /** 0 = cooking day, -1 = the day before. */
  day: 0 | -1
  /** Day 0: minutes before the course is served by which the step must be finished. */
  lead: number
  /** Day -1: start time. */
  at: number | null
  hands: boolean
  equipment: Equipment
  temp: number | null
  done: boolean
  position: number
}

export interface Menu {
  id: number
  title: string
  date: string | null
  guests: number
  updated_at: string
  courses: MenuCourse[]
  steps: MenuStep[]
}

export interface MenuSummary {
  id: number
  title: string
  date: string | null
  guests: number
  updated_at: string
  courses: Array<{ name: string; serve: number; recipe_title: string }>
}

export type MenuStepPatch = Partial<
  Pick<MenuStep, 'name' | 'duration' | 'day' | 'lead' | 'at' | 'hands' | 'equipment' | 'temp' | 'done'>
>

export const api = {
  login(email: string, password: string) {
    const form = new URLSearchParams({ username: email, password })
    return request<{ access_token: string; token_type: string }>('/token', {
      method: 'POST',
      body: form,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },

  listRecipes(params: ListRecipesParams = {}) {
    const qs = new URLSearchParams()
    if (params.limit != null) qs.set('limit', String(params.limit))
    if (params.offset != null) qs.set('offset', String(params.offset))
    if (params.q) qs.set('q', params.q)
    for (const t of params.tags ?? []) qs.append('tag', t)
    const suffix = qs.toString() ? `?${qs}` : ''
    return request<RecipeListPage>(`/recipes${suffix}`)
  },

  getTags(scope?: 'mine' | 'filter') {
    return request<TagInfo[]>(`/recipes/tags${scope ? `?scope=${scope}` : ''}`)
  },

  updateTag(id: number, body: { name?: string; color?: string | null }) {
    return request<TagInfo>(`/recipes/tags/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
  },

  deleteTag(id: number) {
    return request<void>(`/recipes/tags/${id}`, { method: 'DELETE' })
  },

  getRecipe(uuid: string) {
    return request<Recipe>(`/recipes/${uuid}.json`)
  },

  updateRecipe(uuid: string, body: RecipeUpdate) {
    return request<Recipe>(`/recipes/${uuid}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    })
  },

  deleteRecipe(uuid: string) {
    return request<void>(`/recipes/${uuid}`, { method: 'DELETE' })
  },

  /** Changes the password. The server logs out every other session and returns
   *  a fresh token for this one, which replaces the stored token. */
  async changePassword(currentPassword: string, newPassword: string) {
    const res = await request<{ access_token: string }>('/account/password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    })
    localStorage.setItem('auth_token', res.access_token)
  },

  // --- One-time links (public) ---

  describeLink(token: string) {
    return request<LinkInfo>(`/auth/links/${encodeURIComponent(token)}`)
  },

  signup(body: { token: string; email: string; password: string; display_name?: string; language?: string }) {
    return request<{ access_token: string }>('/auth/signup', { method: 'POST', body: JSON.stringify(body) })
  },

  resetPassword(token: string, password: string) {
    return request<{ access_token: string }>('/auth/reset', {
      method: 'POST',
      body: JSON.stringify({ token, password }),
    })
  },

  // --- Admin ---

  adminListUsers() {
    return request<AdminUser[]>('/admin/users')
  },

  adminUpdateUser(id: number, body: { is_admin?: boolean; disabled?: boolean }) {
    return request<void>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
  },

  adminLogoutUser(id: number) {
    return request<void>(`/admin/users/${id}/logout`, { method: 'POST' })
  },

  adminResetLink(id: number) {
    return request<{ token: string; expires_at: string; email: string }>(`/admin/users/${id}/reset-link`, {
      method: 'POST',
    })
  },

  adminDeleteUser(id: number, confirmEmail: string) {
    return request<void>(`/admin/users/${id}?confirm=${encodeURIComponent(confirmEmail)}`, { method: 'DELETE' })
  },

  adminListInvites() {
    return request<Invite[]>('/admin/invites')
  },

  adminCreateInvite(body: { email?: string; note?: string; expires_in_days: number }) {
    return request<Invite & { token: string }>('/admin/invites', { method: 'POST', body: JSON.stringify(body) })
  },

  adminRevokeInvite(id: number) {
    return request<void>(`/admin/invites/${id}`, { method: 'DELETE' })
  },

  getProfile() {
    return request<Profile>('/account/profile')
  },

  /** Partial profile update — omitted fields are left unchanged. */
  updateProfile(body: { display_name?: string; language?: string }) {
    return request<Profile>('/account/profile', {
      method: 'PUT',
      body: JSON.stringify(body),
    })
  },

  /** LLM-translate a recipe into `language`; returns the recipe in that language. */
  translateRecipe(uuid: string, language: string) {
    return request<Recipe>(`/recipes/${uuid}/translate`, {
      method: 'POST',
      body: JSON.stringify({ language }),
    })
  },

  /** Upload (or replace) a recipe's hero image. `imageBase64` is a cropped JPEG. */
  setRecipeImage(uuid: string, imageBase64: string) {
    return request<{ has_image: boolean; image_url: string | null }>(
      `/recipes/${uuid}/image`,
      { method: 'PUT', body: JSON.stringify({ image: imageBase64 }) },
    )
  },

  deleteRecipeImage(uuid: string) {
    return request<void>(`/recipes/${uuid}/image`, { method: 'DELETE' })
  },

  /**
   * Extract a recipe from one or more photos of the same recipe (in order), written in
   * `language` (default: UI language).
   */
  parsePhoto(imagesBase64: string | string[], language?: string) {
    const form = new URLSearchParams()
    for (const image of Array.isArray(imagesBase64) ? imagesBase64 : [imagesBase64]) form.append('image', image)
    if (language) form.set('language', language)
    return request<{ uuid: string; url: string }>('/recipes/parse', {
      method: 'POST',
      body: form,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },

  /** Extract a recipe from a PDF document, written in `language` (default: UI language). */
  importDocument(file: File, language?: string, note?: string) {
    const form = new FormData()
    form.append('file', file)
    if (language) form.append('language', language)
    if (note) form.append('note', note)
    return request<{ uuid: string; url: string }>('/recipes/import-document', { method: 'POST', body: form })
  },

  /** Import a recipe page, translated into `language` (default: UI language). */
  importUrl(url: string, note?: string, language?: string) {
    return request<{ uuid: string; url: string }>('/recipes/import-url', {
      method: 'POST',
      body: JSON.stringify({ url, note, language }),
    })
  },

  /** Render the recipe as a PDF (in the UI language, scaled to `servings`). */
  async downloadRecipePdf(uuid: string, servings?: number) {
    const qs = servings ? `?servings=${servings}` : ''
    const res = await send(`/recipes/${uuid}.pdf${qs}`)
    return {
      blob: await res.blob(),
      filename: dispositionFilename(res.headers.get('Content-Disposition'), 'recipe.pdf'),
    }
  },

  /** Create a recipe by hand (the editor's first save of a new draft). */
  createRecipe(body: {
    title: string
    recipeYield?: string
    description?: string
    note?: string
    language?: string
    ingredients?: Ingredient[]
    instructions?: InstructionStep[]
    tags?: string[]
    is_public?: boolean
    /** One ingredient per line, split into amount/name server-side. */
    ingredients_text?: string
  }) {
    return request<{ uuid: string; url: string }>('/recipes', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  /** Copy a recipe the user can see into their collection (duplicate when it's their own). */
  cloneRecipe(uuid: string) {
    return request<{ uuid: string; url: string }>(`/recipes/${uuid}/clone`, { method: 'POST' })
  },

  // --- Cookbooks ---

  listCookbooks(recipeUuid?: string) {
    const qs = recipeUuid ? `?recipe_uuid=${encodeURIComponent(recipeUuid)}` : ''
    return request<Cookbook[]>(`/cookbooks${qs}`)
  },

  getCookbook(id: number) {
    return request<CookbookDetail>(`/cookbooks/${id}`)
  },

  createCookbook(name: string) {
    return request<Cookbook>('/cookbooks', { method: 'POST', body: JSON.stringify({ name }) })
  },

  /** Find or create the auto "All my recipes" cookbook (share it to share everything). */
  createAllCookbook() {
    return request<Cookbook>('/cookbooks/all', { method: 'POST' })
  },

  renameCookbook(id: number, name: string) {
    return request<{ id: number; name: string }>(`/cookbooks/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    })
  },

  deleteCookbook(id: number) {
    return request<void>(`/cookbooks/${id}`, { method: 'DELETE' })
  },

  addRecipeToCookbook(id: number, recipeUuid: string) {
    return request<{ ok: boolean }>(`/cookbooks/${id}/recipes`, {
      method: 'POST',
      body: JSON.stringify({ recipe_uuid: recipeUuid }),
    })
  },

  removeRecipeFromCookbook(id: number, recipeUuid: string) {
    return request<void>(`/cookbooks/${id}/recipes/${recipeUuid}`, { method: 'DELETE' })
  },

  /** Add many recipes to a cookbook at once — an explicit set, or everything
   *  matching a search (q/tags). Returns how many matched and were newly added. */
  bulkAddToCookbook(
    cookbookId: number,
    opts: { q?: string; tags?: string[]; recipeUuids?: string[] },
  ) {
    const body: Record<string, unknown> = {}
    if (opts.q) body.q = opts.q
    if (opts.tags?.length) body.tags = opts.tags
    if (opts.recipeUuids) body.recipe_uuids = opts.recipeUuids
    return request<{ matched: number; added: number }>(`/cookbooks/${cookbookId}/recipes/bulk`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  // --- Cookbook sharing ---

  getCookbookMembers(id: number) {
    return request<CookbookMembers>(`/cookbooks/${id}/members`)
  },

  inviteCookbookMember(id: number, friendId: number, role: string) {
    return request<{ ok: boolean }>(`/cookbooks/${id}/members`, {
      method: 'POST',
      body: JSON.stringify({ friend_id: friendId, role }),
    })
  },

  updateCookbookMemberRole(id: number, userId: number, role: string) {
    return request<{ ok: boolean }>(`/cookbooks/${id}/members/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    })
  },

  removeCookbookMember(id: number, userId: number) {
    return request<void>(`/cookbooks/${id}/members/${userId}`, { method: 'DELETE' })
  },

  listCookbookInvitations() {
    return request<CookbookInvitation[]>('/cookbooks/invitations')
  },

  acceptCookbookInvitation(cookbookId: number) {
    return request<{ status: string }>(`/cookbooks/invitations/${cookbookId}/accept`, {
      method: 'POST',
    })
  },

  declineCookbookInvitation(cookbookId: number) {
    return request<void>(`/cookbooks/invitations/${cookbookId}/decline`, { method: 'POST' })
  },

  /** Quick-share a single recipe with a friend (wraps it in a quickshare cookbook). */
  shareRecipe(uuid: string, friendId: number, role: string) {
    return request<{ cookbook_id: number }>(`/recipes/${uuid}/share`, {
      method: 'POST',
      body: JSON.stringify({ friend_id: friendId, role }),
    })
  },

  // --- Friends ---

  listFriends() {
    return request<Friend[]>('/friends')
  },

  listFriendRequests(direction: 'incoming' | 'outgoing') {
    return request<FriendRequest[]>(`/friends/requests?direction=${direction}`)
  },

  sendFriendRequest(email: string) {
    return request<{ status: 'pending' | 'accepted'; user: { id: number; email: string } }>(
      '/friends/requests',
      { method: 'POST', body: JSON.stringify({ email }) },
    )
  },

  acceptFriendRequest(id: number) {
    return request<{ status: string }>(`/friends/requests/${id}/accept`, { method: 'POST' })
  },

  declineFriendRequest(id: number) {
    return request<void>(`/friends/requests/${id}/decline`, { method: 'POST' })
  },

  unfriend(userId: number) {
    return request<void>(`/friends/${userId}`, { method: 'DELETE' })
  },

  getMealPlan(start: string, end: string) {
    const qs = new URLSearchParams({ start, end })
    return request<MealPlanEntry[]>(`/meal-plan?${qs}`)
  },

  addMealPlanEntry(date: string, recipeUuid: string) {
    return request<MealPlanEntry>('/meal-plan', {
      method: 'POST',
      body: JSON.stringify({ date, recipe_uuid: recipeUuid }),
    })
  },

  deleteMealPlanEntry(entryId: number) {
    return request<void>(`/meal-plan/${entryId}`, { method: 'DELETE' })
  },

  buildShoppingList(start: string, end: string) {
    return request<ShoppingListResult>('/meal-plan/shopping-list', {
      method: 'POST',
      body: JSON.stringify({ start, end }),
    })
  },

  // --- Google Calendar (server-side) ---

  googleStatus() {
    return request<GoogleStatus>('/integrations/google/status')
  },

  googleConnectUrl() {
    return request<{ url: string }>('/integrations/google/connect')
  },

  googleCalendars() {
    return request<GoogleCalendar[]>('/integrations/google/calendars')
  },

  setGoogleCalendar(calendarId: string) {
    return request<void>('/integrations/google/calendar', {
      method: 'PUT',
      body: JSON.stringify({ calendar_id: calendarId }),
    })
  },

  googleDisconnect() {
    return request<void>('/integrations/google/connect', { method: 'DELETE' })
  },

  syncWeek(start: string, end: string) {
    return request<{ created: number; recreated: number; total: number }>('/meal-plan/sync', {
      method: 'POST',
      body: JSON.stringify({ start, end }),
    })
  },

  weekSyncStatus(start: string, end: string) {
    return request<WeekSyncStatus>('/meal-plan/sync-status', {
      method: 'POST',
      body: JSON.stringify({ start, end }),
    })
  },

  getFeatures() {
    return request<Features>('/features')
  },

  adminSetFeatures(body: Partial<Features>) {
    return request<Features>('/admin/features', { method: 'PUT', body: JSON.stringify(body) })
  },

  listMenus() {
    return request<MenuSummary[]>('/menus')
  },

  createMenu(body: { title: string; date?: string | null; guests?: number }) {
    return request<Menu>('/menus', { method: 'POST', body: JSON.stringify(body) })
  },

  getMenu(id: number) {
    return request<Menu>(`/menus/${id}`)
  },

  /** `date: ''` clears the date. */
  updateMenu(id: number, body: { title?: string; date?: string; guests?: number }) {
    return request<Menu>(`/menus/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
  },

  deleteMenu(id: number) {
    return request<void>(`/menus/${id}`, { method: 'DELETE' })
  },

  /** Add a recipe as a course; the server drafts its prep steps (takes a few seconds). */
  addMenuCourse(id: number, body: { recipe_uuid: string; name?: string; serve?: number; instructions?: string }) {
    return request<Menu>(`/menus/${id}/courses`, { method: 'POST', body: JSON.stringify(body) })
  },

  updateMenuCourse(id: number, courseId: number, body: { name?: string; serve?: number; position?: number }) {
    return request<Menu>(`/menus/${id}/courses/${courseId}`, { method: 'PATCH', body: JSON.stringify(body) })
  },

  deleteMenuCourse(id: number, courseId: number) {
    return request<Menu>(`/menus/${id}/courses/${courseId}`, { method: 'DELETE' })
  },

  redraftMenuCourse(id: number, courseId: number, instructions?: string) {
    return request<Menu>(`/menus/${id}/courses/${courseId}/redraft`, {
      method: 'POST',
      body: JSON.stringify({ instructions: instructions || null }),
    })
  },

  /** All the menu's course ids in their new order. */
  reorderMenuCourses(id: number, courseIds: number[]) {
    return request<Menu>(`/menus/${id}/courses/order`, { method: 'PUT', body: JSON.stringify({ course_ids: courseIds }) })
  },

  /** Let the AI edit the whole plan from a request in plain words. */
  reviseMenu(id: number, requestText: string) {
    return request<Menu>(`/menus/${id}/revise`, { method: 'POST', body: JSON.stringify({ request: requestText }) })
  },

  addMenuStep(id: number, body: { course_id: number; name: string } & MenuStepPatch) {
    return request<Menu>(`/menus/${id}/steps`, { method: 'POST', body: JSON.stringify(body) })
  },

  updateMenuStep(id: number, stepId: number, body: MenuStepPatch) {
    return request<Menu>(`/menus/${id}/steps/${stepId}`, { method: 'PATCH', body: JSON.stringify(body) })
  },

  deleteMenuStep(id: number, stepId: number) {
    return request<Menu>(`/menus/${id}/steps/${stepId}`, { method: 'DELETE' })
  },

  buildMenuShoppingList(id: number) {
    return request<ShoppingListResult>(`/menus/${id}/shopping-list`, { method: 'POST' })
  },

  /** The menu and its prep plan as a PDF (in the UI language), optionally with the recipes. */
  async downloadMenuPdf(id: number, withRecipes = false) {
    const res = await send(`/menus/${id}/plan.pdf${withRecipes ? '?recipes=true' : ''}`)
    return {
      blob: await res.blob(),
      filename: dispositionFilename(res.headers.get('Content-Disposition'), 'menu.pdf'),
    }
  },
}
