import { useCallback, useRef } from 'react'
import { config } from '@/lib/config'

const GIS_SRC = 'https://accounts.google.com/gsi/client'
const SCOPE = 'https://www.googleapis.com/auth/calendar'

// Minimal shape of the Google Identity Services token client we use.
interface TokenResponse {
  access_token?: string
  error?: string
}
interface TokenClient {
  requestAccessToken: (opts?: { prompt?: string }) => void
  callback: (resp: TokenResponse) => void
}
declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2: {
          initTokenClient: (cfg: {
            client_id: string
            scope: string
            callback: (resp: TokenResponse) => void
          }) => TokenClient
        }
      }
    }
  }
}

export interface GoogleCalendar {
  id: string
  summary: string
  primary?: boolean
}

let gisScriptPromise: Promise<void> | null = null

export function loadGis(): Promise<void> {
  if (window.google?.accounts?.oauth2) return Promise.resolve()
  if (!gisScriptPromise) {
    gisScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = GIS_SRC
      script.async = true
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('Failed to load Google Identity Services'))
      document.head.appendChild(script)
    })
  }
  return gisScriptPromise
}

/**
 * On-demand Google Calendar access. Calling `requestAccess()` (must be inside a
 * user click handler so the consent popup isn't blocked) triggers the Google
 * OAuth consent for calendar read/write and resolves with a short-lived access
 * token. The token is used to call the Calendar API directly from the browser —
 * nothing is sent to our backend or persisted.
 */
export function useGoogleCalendar() {
  const supported = !!config.googleClientId
  const tokenRef = useRef<string | null>(null)

  const requestAccess = useCallback(async (): Promise<string> => {
    if (!config.googleClientId) {
      throw new Error('Google Calendar is not configured (missing client ID).')
    }
    await loadGis()
    return new Promise<string>((resolve, reject) => {
      const client = window.google!.accounts.oauth2.initTokenClient({
        client_id: config.googleClientId,
        scope: SCOPE,
        callback: (resp) => {
          if (resp.error || !resp.access_token) {
            reject(new Error(resp.error || 'Authorization failed'))
            return
          }
          tokenRef.current = resp.access_token
          resolve(resp.access_token)
        },
      })
      client.requestAccessToken()
    })
  }, [])

  const listCalendars = useCallback(async (token: string): Promise<GoogleCalendar[]> => {
    const res = await fetch('https://www.googleapis.com/calendar/v3/users/me/calendarList', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`Could not list calendars (HTTP ${res.status})`)
    const data = await res.json()
    return (data.items ?? []).map((c: { id: string; summary: string; primary?: boolean }) => ({
      id: c.id,
      summary: c.summary,
      primary: c.primary,
    }))
  }, [])

  // Insert an all-day event. Google treats `end.date` as exclusive, so it is
  // the day after `date`.
  const insertEvent = useCallback(
    async (token: string, calendarId: string, summary: string, date: string): Promise<void> => {
      const end = new Date(`${date}T00:00:00Z`)
      end.setUTCDate(end.getUTCDate() + 1)
      const endDate = end.toISOString().slice(0, 10)
      const res = await fetch(
        `https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/events`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            summary,
            start: { date },
            end: { date: endDate },
          }),
        },
      )
      if (!res.ok) throw new Error(`Could not create event (HTTP ${res.status})`)
    },
    [],
  )

  return { supported, requestAccess, listCalendars, insertEvent, tokenRef }
}
