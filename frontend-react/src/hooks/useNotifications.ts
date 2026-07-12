import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

/**
 * Counts for the nav badges: pending incoming friend requests and pending
 * cookbook invitations. Polled periodically so badges stay roughly live.
 */
export function useNotifications() {
  const { data: friendRequests = [] } = useQuery({
    queryKey: ['friendRequests', 'incoming'],
    queryFn: () => api.listFriendRequests('incoming'),
    refetchInterval: 60_000,
  })
  const { data: cookbookInvitations = [] } = useQuery({
    queryKey: ['cookbookInvitations'],
    queryFn: api.listCookbookInvitations,
    refetchInterval: 60_000,
  })
  return {
    friendRequests: friendRequests.length,
    cookbookInvites: cookbookInvitations.length,
  }
}
