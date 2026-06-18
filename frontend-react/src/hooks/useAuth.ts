export function getToken(): string | null {
  return localStorage.getItem('auth_token')
}

export function getUserEmail(): string {
  const token = getToken()
  if (!token) return ''
  try {
    return JSON.parse(atob(token.split('.')[1])).sub ?? ''
  } catch {
    return ''
  }
}

export function logout() {
  localStorage.removeItem('auth_token')
  window.location.href = '/login'
}

export function isAuthenticated(): boolean {
  return !!getToken()
}
