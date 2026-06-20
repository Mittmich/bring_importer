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

export interface RecipeListItem {
  uuid: string
  title: string
  datePublished?: string
  createdAt?: string
  source: { kind: string; value: string }
}

export interface Ingredient {
  amount: string  // "2 cups", "200 g", "" for "to taste"
  name: string
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

  listRecipes() {
    return request<RecipeListItem[]>('/recipes')
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
}
