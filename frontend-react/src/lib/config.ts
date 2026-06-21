declare global {
  interface Window {
    ENV?: {
      API_URL?: string
      FRONTEND_URL?: string
      APP_VERSION?: string
      GOOGLE_CLIENT_ID?: string
    }
  }
}

function readEnv(key: keyof NonNullable<Window['ENV']>, fallback: string): string {
  const val = window.ENV?.[key]
  if (val && !/^\{\{/.test(val)) return val.replace(/\/$/, '')
  return localStorage.getItem(key) ?? fallback
}

export const config = {
  apiUrl: readEnv('API_URL', 'http://localhost:8001'),
  frontendUrl: readEnv('FRONTEND_URL', window.location.origin),
  version: readEnv('APP_VERSION', '1.0.0'),
  // Public OAuth Client ID for the on-demand Google Calendar export. Not a
  // secret; empty by default — the export button hides itself when unset.
  googleClientId: readEnv('GOOGLE_CLIENT_ID', ''),
}
