import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useI18n } from '@/i18n'
import { BrandMark } from '@/components/BrandMark'

export function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t, lang, setLanguage } = useI18n()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const result = await api.login(email, password)
      localStorage.setItem('auth_token', result.access_token)
      navigate('/')
    } catch (e: any) {
      setError(e.message ?? t('login.failed'))
      setLoading(false)
    }
  }

  return (
    <div className="min-h-dvh flex items-center justify-center bg-[#F8FAFC] p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="inline-flex items-center gap-2 text-lg font-bold text-foreground">
            <BrandMark className="w-8 h-8" />
            {t('common.appName')}
          </span>
          <p className="text-sm text-muted-foreground mt-2">{t('login.subtitle')}</p>
        </div>

        <div className="bg-white rounded-xl border border-border shadow-sm p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">{t('login.email')}</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                autoComplete="email"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">{t('login.password')}</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">
                {error}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? t('login.signingIn') : t('login.signIn')}
            </Button>
          </form>
        </div>

        <div className="mt-4 flex justify-center">
          <LanguageSelect
            value={lang}
            onChange={(l) => setLanguage(l)}
            aria-label={t('account.language')}
          />
        </div>
      </div>
    </div>
  )
}
