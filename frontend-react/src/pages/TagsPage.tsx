import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, Trash2 } from 'lucide-react'
import { api, type TagInfo } from '@/lib/api'
import { Input } from '@/components/ui/input'
import { TagChip } from '@/components/ui/tag-chip'
import { TAG_PALETTE, tagColor } from '@/lib/tagColors'
import { cn } from '@/lib/utils'
import { useI18n } from '@/i18n'

export function TagsPage() {
  const { data: tags = [], isLoading } = useQuery({ queryKey: ['tags'], queryFn: () => api.getTags() })
  const { t } = useI18n()

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      <div className="max-w-xl mx-auto w-full p-4 md:p-6 space-y-4 pt-6 pb-8">
        <Link
          to="/account"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> {t('tags.back')}
        </Link>

        <div>
          <h1 className="text-lg font-semibold text-foreground">{t('tags.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('tags.subtitle')}</p>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
        {!isLoading && tags.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('tags.empty')}</p>
        )}

        <div className="space-y-3">
          {tags.map((tag) => (
            <TagRow key={tag.id} tag={tag} />
          ))}
        </div>
      </div>
    </div>
  )
}

function TagRow({ tag }: { tag: TagInfo }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(tag.name)
  const [error, setError] = useState<string | null>(null)
  const { t, tp } = useI18n()

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['tags'] })
    queryClient.invalidateQueries({ queryKey: ['recipes'] })
  }

  const update = useMutation({
    mutationFn: (body: { name?: string; color?: string | null }) => api.updateTag(tag.id, body),
    onSuccess: () => {
      setError(null)
      invalidate()
    },
    onError: (e: Error) => setError(e.message),
  })

  const remove = useMutation({
    mutationFn: () => api.deleteTag(tag.id),
    onSuccess: invalidate,
  })

  function commitName() {
    const trimmed = name.trim()
    if (!trimmed || trimmed === tag.name) {
      setName(tag.name)
      setError(null)
      return
    }
    update.mutate({ name: trimmed })
  }

  const activeColor = tagColor(tag.name, tag.color)

  return (
    <div className="bg-white rounded-xl border border-border p-4 space-y-3">
      <div className="flex items-center gap-3">
        <TagChip name={name || tag.name} color={tag.color} />
        <span className="text-xs text-muted-foreground">
          {tp('common.recipes', tag.count)}
        </span>
        <button
          type="button"
          onClick={() => {
            if (confirm(t('tags.confirmDelete', { name: tag.name }))) {
              remove.mutate()
            }
          }}
          aria-label={t('tags.deleteLabel', { name: tag.name })}
          className="ml-auto text-muted-foreground hover:text-destructive transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <Input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={commitName}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commitName()
          }
        }}
        aria-label={t('tags.renameLabel', { name: tag.name })}
      />
      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex flex-wrap gap-1.5">
        {TAG_PALETTE.map((swatch) => {
          const selected = activeColor.toLowerCase() === swatch.toLowerCase()
          return (
            <button
              key={swatch}
              type="button"
              onClick={() => update.mutate({ color: swatch })}
              aria-label={t('tags.colorLabel', { color: swatch })}
              className={cn(
                'h-6 w-6 rounded-full flex items-center justify-center ring-offset-2 transition-shadow',
                selected && 'ring-2 ring-foreground/30',
              )}
              style={{ backgroundColor: swatch }}
            >
              {selected && <Check className="w-3.5 h-3.5 text-white" />}
            </button>
          )
        })}
      </div>
    </div>
  )
}
