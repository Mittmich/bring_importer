import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useFeatures } from '@/hooks/useFeatures'

/**
 * Counts for the nav badges: pending incoming friend requests and pending
 * cookbook and menu invitations. Polled periodically so badges stay roughly live.
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
  const { features } = useFeatures()
  const { data: menuInvitations = [] } = useQuery({
    queryKey: ['menuInvitations'],
    queryFn: api.listMenuInvitations,
    refetchInterval: 60_000,
    enabled: features?.planner === 'menus',
  })
  return {
    friendRequests: friendRequests.length,
    cookbookInvites: cookbookInvitations.length,
    menuInvites: features?.planner === 'menus' ? menuInvitations.length : 0,
  }
}
