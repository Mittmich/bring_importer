import { config } from './config'

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${config.apiUrl}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
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
  if (res.status === 204) return undefined as T
  return res.json()
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
  /** Only present when listCookbooks is called with a recipeUuid. */
  contains?: boolean
}

export interface CookbookDetail {
  id: number
  name: string
  recipe_count: number
  recipes: RecipeListItem[]
  role?: CookbookRole
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
}

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

  changePassword(currentPassword: string, newPassword: string) {
    return request<void>('/account/password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    })
  },

  getProfile() {
    return request<Profile>('/account/profile')
  },

  updateProfile(displayName: string) {
    return request<Profile>('/account/profile', {
      method: 'PUT',
      body: JSON.stringify({ display_name: displayName }),
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

  parsePhoto(imageBase64: string) {
    const form = new URLSearchParams({ image: imageBase64 })
    return request<{ uuid: string; url: string }>('/recipes/parse', {
      method: 'POST',
      body: form,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },

  importUrl(url: string, note?: string) {
    return request<{ uuid: string; url: string }>('/recipes/import-url', {
      method: 'POST',
      body: JSON.stringify({ url, note }),
    })
  },

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
}
