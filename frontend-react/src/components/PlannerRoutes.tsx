import { Navigate } from 'react-router-dom'
import { useFeatures } from '@/hooks/useFeatures'
import { WeeklyPlanPage } from '@/pages/WeeklyPlanPage'
import { MenusPage } from '@/pages/MenusPage'

/** `/plan` shows the weekly plan or the menus, depending on the `planner` feature flag. */
export function PlannerSwitch() {
  const { features } = useFeatures()
  if (!features) return null
  return features.planner === 'menus' ? <MenusPage /> : <WeeklyPlanPage />
}

/** Menu pages only exist while the flag is on; otherwise send people to the weekly plan. */
export function MenusOnly({ children }: { children: React.ReactNode }) {
  const { features } = useFeatures()
  if (!features) return null
  return features.planner === 'menus' ? <>{children}</> : <Navigate to="/plan" replace />
}
