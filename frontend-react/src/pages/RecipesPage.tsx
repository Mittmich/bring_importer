import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { RecipeListPanel } from '@/components/RecipeListPanel'
import { RecipeDetail } from '@/components/RecipeDetail'
import { useI18n } from '@/i18n'

export function RecipesPage() {
  const { uuid } = useParams<{ uuid?: string }>()
  const { t } = useI18n()

  const { data: recipe, isLoading, error } = useQuery({
    queryKey: ['recipe', uuid],
    queryFn: () => api.getRecipe(uuid!),
    enabled: !!uuid,
  })

  return (
    <div className="flex h-full">
      {/* List panel — hidden on mobile when a recipe is open */}
      <div className={uuid ? 'hidden md:flex' : 'flex w-full md:w-auto'}>
        <RecipeListPanel activeUuid={uuid} />
      </div>

      {/* Detail pane */}
      <div className={`flex-1 overflow-hidden ${uuid ? 'flex' : 'hidden md:flex'}`}>
        {!uuid ? (
          <div className="hidden md:flex flex-1 items-center justify-center text-sm text-muted-foreground bg-[#F8FAFC]">
            {t('list.selectRecipe')}
          </div>
        ) : isLoading ? (
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground bg-[#F8FAFC]">
            {t('common.loading')}
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center text-sm text-destructive bg-[#F8FAFC]">
            {t('list.recipeLoadFailed')}
          </div>
        ) : recipe ? (
          <div className="flex-1 overflow-hidden">
            <RecipeDetail key={uuid} uuid={uuid} recipe={recipe} />
          </div>
        ) : null}
      </div>
    </div>
  )
}
