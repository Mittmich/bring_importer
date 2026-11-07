import { useState } from 'react'

/**
 * Local editable copy of a saved value (e.g. an input that commits on blur).
 * When the saved value changes from outside, the draft follows it — adjusted
 * during render, React's recommended alternative to syncing in an effect.
 */
export function useDraft<T>(value: T): [T, (v: T) => void] {
  const [draft, setDraft] = useState(value)
  const [prev, setPrev] = useState(value)
  if (prev !== value) {
    setPrev(value)
    setDraft(value)
  }
  return [draft, setDraft]
}
