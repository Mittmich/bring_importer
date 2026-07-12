import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, UserPlus, X } from 'lucide-react'
import { api, personName, type Friend, type FriendRequest } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function FriendsPage() {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const { data: friends = [] } = useQuery({ queryKey: ['friends'], queryFn: api.listFriends })
  const { data: incoming = [] } = useQuery({
    queryKey: ['friendRequests', 'incoming'],
    queryFn: () => api.listFriendRequests('incoming'),
  })
  const { data: outgoing = [] } = useQuery({
    queryKey: ['friendRequests', 'outgoing'],
    queryFn: () => api.listFriendRequests('outgoing'),
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['friends'] })
    queryClient.invalidateQueries({ queryKey: ['friendRequests'] })
  }

  const send = useMutation({
    mutationFn: (addr: string) => api.sendFriendRequest(addr),
    onSuccess: (res) => {
      setError(null)
      setEmail('')
      setNotice(
        res.status === 'accepted'
          ? `You're now friends with ${res.user.email}.`
          : `Request sent to ${res.user.email}.`,
      )
      invalidate()
    },
    onError: (e: Error) => {
      setNotice(null)
      setError(e.message)
    },
  })

  const accept = useMutation({
    mutationFn: (id: number) => api.acceptFriendRequest(id),
    onSuccess: invalidate,
  })
  const decline = useMutation({
    mutationFn: (id: number) => api.declineFriendRequest(id),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (userId: number) => api.unfriend(userId),
    onSuccess: invalidate,
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const addr = email.trim()
    if (addr) send.mutate(addr)
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      <div className="max-w-xl mx-auto w-full p-4 md:p-6 space-y-5 pt-6 pb-8">
        <Link
          to="/account"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Account
        </Link>

        <div>
          <h1 className="text-lg font-semibold text-foreground">Friends</h1>
          <p className="text-sm text-muted-foreground">
            Add friends by email so you can share recipes with them.
          </p>
        </div>

        {/* Add a friend */}
        <form onSubmit={submit} className="bg-white rounded-xl border border-border p-4 space-y-3">
          <label htmlFor="friend-email" className="text-sm font-medium text-foreground">
            Add a friend
          </label>
          <div className="flex gap-2">
            <Input
              id="friend-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="friend@example.com"
              autoComplete="off"
            />
            <Button type="submit" disabled={send.isPending || !email.trim()}>
              <UserPlus className="w-4 h-4 mr-1.5" />
              {send.isPending ? 'Sending…' : 'Send'}
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {notice && <p className="text-sm text-emerald-600">{notice}</p>}
        </form>

        {/* Incoming requests */}
        {incoming.length > 0 && (
          <Section title="Requests received">
            {incoming.map((r) => (
              <RequestRow key={r.id} req={r}>
                <Button
                  size="sm"
                  onClick={() => accept.mutate(r.id)}
                  disabled={accept.isPending}
                >
                  <Check className="w-4 h-4 mr-1" /> Accept
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => decline.mutate(r.id)}
                  disabled={decline.isPending}
                >
                  <X className="w-4 h-4" />
                </Button>
              </RequestRow>
            ))}
          </Section>
        )}

        {/* Outgoing requests */}
        {outgoing.length > 0 && (
          <Section title="Requests sent">
            {outgoing.map((r) => (
              <RequestRow key={r.id} req={r}>
                <span className="text-xs text-muted-foreground">Pending</span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => remove.mutate(r.user_id)}
                  disabled={remove.isPending}
                >
                  Cancel
                </Button>
              </RequestRow>
            ))}
          </Section>
        )}

        {/* Friends */}
        <Section title={`Friends${friends.length ? ` (${friends.length})` : ''}`}>
          {friends.length === 0 ? (
            <p className="text-sm text-muted-foreground px-1 py-2">No friends yet.</p>
          ) : (
            friends.map((f) => (
              <FriendRow key={f.user_id} friend={f}>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => remove.mutate(f.user_id)}
                  disabled={remove.isPending}
                >
                  Remove
                </Button>
              </FriendRow>
            ))
          )}
        </Section>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
        {title}
      </h2>
      <div className="bg-white rounded-xl border border-border divide-y divide-border/50 overflow-hidden">
        {children}
      </div>
    </div>
  )
}

function PersonRow({
  displayName,
  email,
  children,
}: {
  displayName?: string
  email: string
  children: React.ReactNode
}) {
  const name = personName(displayName, email)
  return (
    <div className="flex items-center gap-2 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground truncate">{name}</p>
        {name !== email && <p className="text-xs text-muted-foreground truncate">{email}</p>}
      </div>
      {children}
    </div>
  )
}

function RequestRow({ req, children }: { req: FriendRequest; children: React.ReactNode }) {
  return (
    <PersonRow displayName={req.display_name} email={req.email}>
      {children}
    </PersonRow>
  )
}

function FriendRow({ friend, children }: { friend: Friend; children: React.ReactNode }) {
  return (
    <PersonRow displayName={friend.display_name} email={friend.email}>
      {children}
    </PersonRow>
  )
}
