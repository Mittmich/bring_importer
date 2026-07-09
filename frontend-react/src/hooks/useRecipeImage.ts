import { useEffect, useState } from 'react'
import { config } from '@/lib/config'

/**
 * Resolve a recipe hero image URL into a displayable `src`.
 *
 * Hero images are auth-protected like the recipe JSON, so a bare `<img src>`
 * won't do — the browser wouldn't attach the bearer token. We fetch the bytes
 * (with auth when a token is present) and hand back an object URL, revoking it
 * on cleanup. On the public share page there's no token; the request is then
 * anonymous, which the backend allows for public recipes.
 *
 * `imageUrl` is the relative path returned by the API (e.g.
 * `/recipes/<uuid>/image?v=...`); pass `null`/`undefined` when there's no image.
 */
export function useRecipeImage(imageUrl?: string | null): string | undefined {
  const [src, setSrc] = useState<string>()

  useEffect(() => {
    if (!imageUrl) {
      setSrc(undefined)
      return
    }
    let cancelled = false
    let objectUrl: string | undefined
    const token = localStorage.getItem('auth_token')

    fetch(`${config.apiUrl}${imageUrl}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => (res.ok ? res.blob() : Promise.reject(new Error(String(res.status)))))
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setSrc(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setSrc(undefined)
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [imageUrl])

  return src
}
