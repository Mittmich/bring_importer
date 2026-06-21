import type { Ingredient } from '@/lib/api'

export function parseServings(recipeYield?: string): number {
  if (!recipeYield) return 4
  const m = recipeYield.match(/\d+/)
  return m ? parseInt(m[0], 10) : 4
}

export function servingsUnit(recipeYield?: string): string {
  if (!recipeYield) return 'servings'
  return recipeYield.replace(/^\d+\s*/, '').trim() || 'servings'
}

// Scale a number to a readable form, using Unicode fraction symbols for
// common values (½, ⅓, ¼ …) and one decimal place otherwise.
export function formatAmount(n: number): string {
  n = Math.round(n * 100) / 100
  const whole = Math.floor(n)
  const frac = n - whole
  const FRACS: [number, string][] = [
    [1 / 4, '¼'], [1 / 3, '⅓'], [1 / 2, '½'], [2 / 3, '⅔'], [3 / 4, '¾'],
  ]
  for (const [val, sym] of FRACS) {
    if (Math.abs(frac - val) < 0.06) return whole > 0 ? `${whole}${sym}` : sym
  }
  if (frac < 0.05) return String(whole)
  const fixed = Math.round(n * 10) / 10
  return fixed % 1 === 0 ? String(fixed) : fixed.toFixed(1)
}

// Scale all numbers in a string by `factor`.
// Handles: integers ("2"), decimals ("1.5", "1,5"), fractions ("1/2"),
// and mixed numbers ("1 1/2").
export function scaleText(text: string, factor: number): string {
  if (Math.abs(factor - 1) < 0.001) return text
  return text.replace(
    /(\d+)\s+(\d+)\s*\/\s*(\d+)|(\d+)\s*\/\s*(\d+)|(\d+(?:[.,]\d+)?)/g,
    (_m, mW, mN, mD, fN, fD, num) => {
      const value =
        mW !== undefined ? parseInt(mW) + parseInt(mN) / parseInt(mD)
        : fN !== undefined ? parseInt(fN) / parseInt(fD)
        : parseFloat(num.replace(',', '.'))
      return formatAmount(value * factor)
    },
  )
}

export function formatIngredient(ing: Ingredient, scale: number): string {
  const scaledAmount = scaleText(ing.amount, scale)
  return `${scaledAmount} ${ing.name}`.trim()
}
