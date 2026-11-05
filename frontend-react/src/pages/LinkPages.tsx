import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useI18n } from '@/i18n'
import { BrandMark } from '@/components/BrandMark'

const MIN_PASSWORD = 8

/**
 * Public pages behind admin-issued one-time links:
 * `/signup/:token` (create an account) and `/reset/:token` (new password).
 * Both check the link first, then log the user in on success.
 */

function useLink(kind: 'signup' | 'reset') {
  const { token = '' } = useParams<{ token: string }>()
  const query = useQuery({
    queryKey: ['link', token],
    queryFn: () => api.describeLink(token),
    retry: false,
    staleTime: Infinity,
  })
  const valid = query.data?.kind === kind
  return { token, info: valid ? query.data : undefined, loading: query.isLoading, invalid: !query.isLoading && !valid }
}

/** Log in with a fresh token and start the app from scratch (no stale cache). */
function enterApp(accessToken: string) {
  localStorage.setItem('auth_token', accessToken)
  window.location.replace('/')
}

function Shell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  const { t, lang, setLanguage } = useI18n()
  return (
    <div className="min-h-dvh flex items-center justify-center bg-[#F8FAFC] p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="inline-flex items-center gap-2 text-lg font-bold text-foreground">
            <BrandMark className="w-8 h-8" />
            {t('common.appName')}
          </span>
          <h1 className="text-base font-semibold text-foreground mt-4">{title}</h1>
          {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
        </div>
        <div className="bg-white rounded-xl border border-border shadow-sm p-6">{children}</div>
        <div className="mt-4 flex justify-center">
          <LanguageSelect value={lang} onChange={(l) => setLanguage(l)} aria-label={t('account.language')} />
        </div>
      </div>
    </div>
  )
}

function LinkState({ loading }: { loading: boolean }) {
  const { t } = useI18n()
  if (loading) {
    return (
      <Shell title={t('link.checking')}>
        <p className="text-sm text-muted-foreground text-center">{t('common.loading')}</p>
      </Shell>
    )
  }
  return (
    <Shell title={t('link.invalid')} subtitle={t('link.invalidHint')}>
      <Link to="/login" className="block">
        <Button className="w-full">{t('link.toLogin')}</Button>
      </Link>
    </Shell>
  )
}

function PasswordFields({
  password,
  confirm,
  onPassword,
  onConfirm,
}: {
  password: string
  confirm: string
  onPassword: (v: string) => void
  onConfirm: (v: string) => void
}) {
  const { t } = useI18n()
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="new-password">{t('link.password')}</Label>
        <Input
          id="new-password"
          type="password"
          value={password}
          onChange={(e) => onPassword(e.target.value)}
          autoComplete="new-password"
          required
        />
        <p className="text-xs text-muted-foreground">{t('link.passwordHint')}</p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="confirm-password">{t('link.confirmPassword')}</Label>
        <Input
          id="confirm-password"
          type="password"
          value={confirm}
          onChange={(e) => onConfirm(e.target.value)}
          autoComplete="new-password"
          required
        />
      </div>
    </>
  )
}

function passwordProblem(password: string, confirm: string, t: ReturnType<typeof useI18n>['t']) {
  if (password.length < MIN_PASSWORD) return t('link.passwordTooShort')
  if (password !== confirm) return t('link.passwordMismatch')
  return null
}

export function SignupPage() {
  const { t, lang } = useI18n()
  const { token, info, loading, invalid } = useLink('signup')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading || invalid || !info) return <LinkState loading={loading} />
  const lockedEmail = info.email

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const problem = passwordProblem(password, confirm, t)
    if (problem) return setError(problem)
    setBusy(true)
    setError(null)
    try {
      const result = await api.signup({
        token,
        email: (lockedEmail ?? email).trim(),
        password,
        display_name: name.trim() || undefined,
        language: lang,
      })
      enterApp(result.access_token)
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : t('signup.failed'))
      setBusy(false)
    }
  }

  return (
    <Shell title={t('signup.title')} subtitle={t('signup.subtitle', { app: t('common.appName') })}>
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="signup-email">{t('login.email')}</Label>
          <Input
            id="signup-email"
            type="email"
            value={lockedEmail ?? email}
            readOnly={!!lockedEmail}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            autoFocus={!lockedEmail}
            required
            className={lockedEmail ? 'bg-muted/50' : undefined}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="signup-name">{t('signup.name')}</Label>
          <Input
            id="signup-name"
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('signup.namePlaceholder')}
            autoComplete="name"
          />
        </div>
        <PasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
        {error && <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? t('signup.submitting') : t('signup.submit')}
        </Button>
      </form>
    </Shell>
  )
}

export function ResetPasswordPage() {
  const { t } = useI18n()
  const { token, info, loading, invalid } = useLink('reset')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading || invalid || !info) return <LinkState loading={loading} />

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const problem = passwordProblem(password, confirm, t)
    if (problem) return setError(problem)
    setBusy(true)
    setError(null)
    try {
      const result = await api.resetPassword(token, password)
      enterApp(result.access_token)
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : t('reset.failed'))
      setBusy(false)
    }
  }

  return (
    <Shell title={t('reset.title')} subtitle={t('reset.subtitle', { email: info.email ?? '' })}>
      <form onSubmit={submit} className="space-y-4">
        {/* Lets password managers pair the new password with the account. */}
        <input type="email" value={info.email ?? ''} autoComplete="username" readOnly hidden />
        <PasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
        {error && <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? t('reset.submitting') : t('reset.submit')}
        </Button>
      </form>
    </Shell>
  )
}
