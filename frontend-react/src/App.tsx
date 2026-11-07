import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isAuthenticated } from '@/hooks/useAuth'
import { I18nProvider } from '@/i18n'
import { AppShell } from '@/components/AppShell'
import { LoginPage } from '@/pages/LoginPage'
import { HomePage } from '@/pages/HomePage'
import { RecipesPage } from '@/pages/RecipesPage'
import { EditRecipePage } from '@/pages/EditRecipePage'
import { AccountPage } from '@/pages/AccountPage'
import { TagsPage } from '@/pages/TagsPage'
import { FriendsPage } from '@/pages/FriendsPage'
import { CookbooksPage } from '@/pages/CookbooksPage'
import { CookbookDetailPage } from '@/pages/CookbookDetailPage'
import { PublicRecipePage } from '@/pages/PublicRecipePage'
import { MenuPage } from '@/pages/MenuPage'
import { CookModePage } from '@/pages/CookModePage'
import { MenusOnly, PlannerSwitch } from '@/components/PlannerRoutes'
import { AdminPage } from '@/pages/AdminPage'
import { ResetPasswordPage, SignupPage } from '@/pages/LinkPages'

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
      <I18nProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/share/:uuid" element={<PublicRecipePage />} />
          <Route path="/signup/:token" element={<SignupPage />} />
          <Route path="/reset/:token" element={<ResetPasswordPage />} />
          <Route
            path="/"
            element={
              <AuthGuard>
                <AppShell />
              </AuthGuard>
            }
          >
            <Route index element={<HomePage />} />
            <Route path="plan" element={<PlannerSwitch />} />
            <Route path="menus/:id" element={<MenusOnly><MenuPage /></MenusOnly>} />
            <Route path="menus/:id/cook" element={<MenusOnly><CookModePage /></MenusOnly>} />
            <Route path="recipes" element={<RecipesPage />} />
            <Route path="recipes/:uuid" element={<RecipesPage />} />
            <Route path="recipes/new" element={<EditRecipePage />} />
            <Route path="recipes/:uuid/edit" element={<EditRecipePage />} />
            <Route path="cookbooks" element={<CookbooksPage />} />
            <Route path="cookbooks/:id" element={<CookbookDetailPage />} />
            <Route path="account" element={<AccountPage />} />
            <Route path="account/tags" element={<TagsPage />} />
            <Route path="account/friends" element={<FriendsPage />} />
            <Route path="admin" element={<AdminPage />} />
            <Route path="import" element={<Navigate to="/" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  )
}
