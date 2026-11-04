import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Tag, Users } from 'lucide-react'
import { api } from '@/lib/api'
import { getUserEmail, logout } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useI18n } from '@/i18n'

export function AccountPage() {
  const email = getUserEmail()
  const { t } = useI18n()

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      <div className="max-w-sm mx-auto w-full p-4 md:p-6 space-y-4 pt-8 pb-10">
        <div className="bg-white rounded-xl border border-border p-5">
          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-1">
            {t('account.signedInAs')}
          </p>
          <p className="text-sm font-semibold text-foreground">{email}</p>
        </div>
        <Link
          to="/account/friends"
          className="flex items-center gap-3 bg-white rounded-xl border border-border p-5 hover:bg-muted/40 transition-colors"
        >
          <Users className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">{t('account.friends')}</span>
          <ChevronRight className="w-4 h-4 text-muted-foreground/50 ml-auto" />
        </Link>
        <Link
          to="/account/tags"
          className="flex items-center gap-3 bg-white rounded-xl border border-border p-5 hover:bg-muted/40 transition-colors"
        >
          <Tag className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">{t('account.manageTags')}</span>
          <ChevronRight className="w-4 h-4 text-muted-foreground/50 ml-auto" />
        </Link>

        <LanguageCard />

        <DisplayNameCard />

        <ChangePasswordCard />

        <Button variant="outline" className="w-full text-destructive hover:text-destructive" onClick={logout}>
          {t('nav.logout')}
        </Button>
      </div>
    </div>
  )
}

function LanguageCard() {
  const { t, lang, setLanguage } = useI18n()
  return (
    <div className="bg-white rounded-xl border border-border p-5 space-y-3">
      <div>
        <label htmlFor="ui-language" className="text-sm font-medium text-foreground">
          {t('account.language')}
        </label>
        <p className="text-xs text-muted-foreground mt-0.5">{t('account.languageHint')}</p>
      </div>
      <LanguageSelect
        id="ui-language"
        value={lang}
        onChange={(l) => setLanguage(l, { persist: true })}
        className="w-full"
      />
    </div>
  )
}

function DisplayNameCard() {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: api.getProfile })
  const [name, setName] = useState('')
  const [done, setDone] = useState(false)

  // Seed the field once the profile loads.
  useEffect(() => {
    if (profile) setName(profile.display_name)
  }, [profile])

  const save = useMutation({
    mutationFn: (n: string) => api.updateProfile({ display_name: n }),
    onSuccess: () => {
      setDone(true)
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['friends'] })
    },
  })

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        setDone(false)
        save.mutate(name.trim())
      }}
      className="bg-white rounded-xl border border-border p-5 space-y-3"
    >
      <div>
        <p className="text-sm font-medium text-foreground">{t('account.displayName')}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{t('account.displayNameHint')}</p>
      </div>
      <Input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={t('account.displayNamePlaceholder')}
        maxLength={60}
      />
      {done && <p className="text-sm text-emerald-600">{t('common.saved')}</p>}
      <Button type="submit" className="w-full" disabled={save.isPending}>
        {save.isPending ? t('common.saving') : t('common.save')}
      </Button>
    </form>
  )
}

function ChangePasswordCard() {
  const { t } = useI18n()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const mutation = useMutation({
    mutationFn: () => api.changePassword(current, next),
    onSuccess: () => {
      setError(null)
      setDone(true)
      setCurrent('')
      setNext('')
      setConfirm('')
    },
    onError: (e: Error) => {
      setDone(false)
      setError(e.message)
    },
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setDone(false)
    if (next.length < 8) {
      setError(t('account.passwordTooShort'))
      return
    }
    if (next !== confirm) {
      setError(t('account.passwordMismatch'))
      return
    }
    setError(null)
    mutation.mutate()
  }

  return (
    <form onSubmit={submit} className="bg-white rounded-xl border border-border p-5 space-y-3">
      <p className="text-sm font-medium text-foreground">{t('account.changePassword')}</p>
      <Input
        type="password"
        placeholder={t('account.currentPassword')}
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        autoComplete="current-password"
      />
      <Input
        type="password"
        placeholder={t('account.newPassword')}
        value={next}
        onChange={(e) => setNext(e.target.value)}
        autoComplete="new-password"
      />
      <Input
        type="password"
        placeholder={t('account.confirmPassword')}
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        autoComplete="new-password"
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {done && <p className="text-sm text-emerald-600">{t('account.passwordChanged')}</p>}
      <Button
        type="submit"
        className="w-full"
        disabled={mutation.isPending || !current || !next || !confirm}
      >
        {mutation.isPending ? t('account.changingPassword') : t('account.changePassword')}
      </Button>
    </form>
  )
}
