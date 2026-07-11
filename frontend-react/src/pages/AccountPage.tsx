import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { ChevronRight, Tag, Users } from 'lucide-react'
import { api } from '@/lib/api'
import { getUserEmail, logout } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function AccountPage() {
  const email = getUserEmail()

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      <div className="max-w-sm mx-auto w-full p-4 md:p-6 space-y-4 pt-8 pb-10">
        <div className="bg-white rounded-xl border border-border p-5">
          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-1">
            Signed in as
          </p>
          <p className="text-sm font-semibold text-foreground">{email}</p>
        </div>
        <Link
          to="/account/friends"
          className="flex items-center gap-3 bg-white rounded-xl border border-border p-5 hover:bg-muted/40 transition-colors"
        >
          <Users className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Friends</span>
          <ChevronRight className="w-4 h-4 text-muted-foreground/50 ml-auto" />
        </Link>
        <Link
          to="/account/tags"
          className="flex items-center gap-3 bg-white rounded-xl border border-border p-5 hover:bg-muted/40 transition-colors"
        >
          <Tag className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Manage tags</span>
          <ChevronRight className="w-4 h-4 text-muted-foreground/50 ml-auto" />
        </Link>

        <ChangePasswordCard />

        <Button variant="outline" className="w-full text-destructive hover:text-destructive" onClick={logout}>
          Log out
        </Button>
      </div>
    </div>
  )
}

function ChangePasswordCard() {
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
      setError('New password must be at least 8 characters')
      return
    }
    if (next !== confirm) {
      setError('New passwords do not match')
      return
    }
    setError(null)
    mutation.mutate()
  }

  return (
    <form onSubmit={submit} className="bg-white rounded-xl border border-border p-5 space-y-3">
      <p className="text-sm font-medium text-foreground">Change password</p>
      <Input
        type="password"
        placeholder="Current password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        autoComplete="current-password"
      />
      <Input
        type="password"
        placeholder="New password"
        value={next}
        onChange={(e) => setNext(e.target.value)}
        autoComplete="new-password"
      />
      <Input
        type="password"
        placeholder="Confirm new password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        autoComplete="new-password"
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {done && <p className="text-sm text-emerald-600">Password changed.</p>}
      <Button
        type="submit"
        className="w-full"
        disabled={mutation.isPending || !current || !next || !confirm}
      >
        {mutation.isPending ? 'Changing…' : 'Change password'}
      </Button>
    </form>
  )
}
