import { useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Menu, type MenuStepPatch } from '@/lib/api'

/**
 * One menu plus its edits. Every edit endpoint returns the whole menu, which
 * replaces the cached copy. Small edits (step fields, serving times, guests) are
 * applied to the cache first so dragging and typing feel instant; while several
 * edits are in flight only the last response is applied, so an older response
 * can't undo a newer edit. A failed edit reloads the menu.
 */
export function useMenu(id: number) {
  const qc = useQueryClient()
  const key = ['menu', id]
  const pending = useRef(0)
  const query = useQuery({ queryKey: key, queryFn: () => api.getMenu(id), enabled: id > 0 })

  const mutation = useMutation({
    mutationFn: (call: () => Promise<Menu>) => call(),
    onMutate: () => {
      pending.current += 1
    },
    onSuccess: (menu) => {
      if (pending.current === 1) qc.setQueryData(key, menu)
    },
    onError: () => qc.invalidateQueries({ queryKey: key }),
    onSettled: () => {
      pending.current -= 1
      qc.invalidateQueries({ queryKey: ['menus'] })
    },
  })

  const optimistic = (update: (m: Menu) => Menu) =>
    qc.setQueryData<Menu>(key, (m) => (m ? update(m) : m))

  return {
    menu: query.data,
    isLoading: query.isLoading,
    error: query.error,
    saving: mutation.isPending,
    /** Run an edit that returns the menu (no optimistic update). */
    run: (call: () => Promise<Menu>) => mutation.mutateAsync(call),
    updateStep(stepId: number, patch: MenuStepPatch) {
      optimistic((m) => ({ ...m, steps: m.steps.map((s) => (s.id === stepId ? { ...s, ...patch } : s)) }))
      mutation.mutate(() => api.updateMenuStep(id, stepId, patch))
    },
    updateCourse(courseId: number, patch: { name?: string; serve?: number }) {
      optimistic((m) => ({
        ...m,
        courses: m.courses.map((c) => (c.id === courseId ? { ...c, ...patch } : c)),
      }))
      mutation.mutate(() => api.updateMenuCourse(id, courseId, patch))
    },
    /** Put the courses in this order (every course id once). */
    reorderCourses(courseIds: number[]) {
      optimistic((m) => ({
        ...m,
        courses: m.courses.map((c) => ({ ...c, position: courseIds.indexOf(c.id) })),
      }))
      mutation.mutate(() => api.reorderMenuCourses(id, courseIds))
    },
    updateMenu(patch: { title?: string; date?: string; guests?: number }) {
      optimistic((m) => ({
        ...m,
        ...(patch.title !== undefined && { title: patch.title }),
        ...(patch.guests !== undefined && { guests: patch.guests }),
        ...(patch.date !== undefined && { date: patch.date || null }),
      }))
      mutation.mutate(() => api.updateMenu(id, patch))
    },
  }
}

export type MenuApi = ReturnType<typeof useMenu>
