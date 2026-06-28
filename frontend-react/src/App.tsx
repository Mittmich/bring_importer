import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isAuthenticated } from '@/hooks/useAuth'
import { AppShell } from '@/components/AppShell'
import { LoginPage } from '@/pages/LoginPage'
import { HomePage } from '@/pages/HomePage'
import { RecipesPage } from '@/pages/RecipesPage'
import { EditRecipePage } from '@/pages/EditRecipePage'
import { AccountPage } from '@/pages/AccountPage'
import { TagsPage } from '@/pages/TagsPage'
import { PublicRecipePage } from '@/pages/PublicRecipePage'
import { WeeklyPlanPage } from '@/pages/WeeklyPlanPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

function AuthGuard({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (!isAuthenticated()) {
      navigate('/login', { replace: true, state: { from: location.pathname } })
    }
  }, [location.pathname, navigate])

  if (!isAuthenticated()) return null
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/share/:uuid" element={<PublicRecipePage />} />
          <Route
            path="/"
            element={
              <AuthGuard>
                <AppShell />
              </AuthGuard>
            }
          >
            <Route index element={<HomePage />} />
            <Route path="plan" element={<WeeklyPlanPage />} />
            <Route path="recipes" element={<RecipesPage />} />
            <Route path="recipes/:uuid" element={<RecipesPage />} />
            <Route path="recipes/:uuid/edit" element={<EditRecipePage />} />
            <Route path="account" element={<AccountPage />} />
            <Route path="account/tags" element={<TagsPage />} />
            <Route path="import" element={<Navigate to="/" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
