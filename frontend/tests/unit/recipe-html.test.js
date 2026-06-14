// Vitest unit tests for the pure helpers exposed by
// `frontend/js/lib/recipe-html.js` via `globalThis.recipeLib`.
//
// These are deliberately framework-free: they load the shim file and
// assert on its public surface. No DOM, no fetch, no async.

import { describe, it, expect, beforeAll } from 'vitest';

beforeAll(async () => {
  // Load the UMD-ish shim. It attaches `globalThis.recipeLib`.
  await import('../../js/lib/recipe-html.js');
});

// ---------------------------------------------------------------------------
// createSimpleRecipeHtml
// ---------------------------------------------------------------------------

describe('createSimpleRecipeHtml', () => {
  it('renders all fields when data is complete', () => {
    const html = globalThis.recipeLib.createSimpleRecipeHtml({
      name: 'Pancakes',
      recipeYield: '4 servings',
      description: 'Light and fluffy.',
      recipeIngredient: ['1 cup flour', '2 eggs'],
    });
    expect(html).toContain('Pancakes');
    expect(html).toContain('4 servings');
    expect(html).toContain('Light and fluffy.');
    expect(html).toContain('1 cup flour');
    expect(html).toContain('2 eggs');
    expect(html).toContain('itemtype="http://schema.org/Recipe"');
    expect(html).toContain('recipeIngredient');
  });

  it('uses "Recipe" as the default title and "4 servings" as the default yield when fields are missing', () => {
    const html = globalThis.recipeLib.createSimpleRecipeHtml({});
    expect(html).toContain('Recipe');
    expect(html).toContain('4 servings');
    // No ingredients block when the array is empty/missing.
    expect(html).not.toContain('<ul>');
  });

  it('escapes special characters to prevent HTML injection', () => {
    const html = globalThis.recipeLib.createSimpleRecipeHtml({
      name: '<script>alert("xss")</script>',
      description: 'A & B < C',
      recipeIngredient: ['1 tsp <salt> & pepper'],
    });
    expect(html).not.toContain('<script>alert');
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('A &amp; B &lt; C');
    expect(html).toContain('1 tsp &lt;salt&gt; &amp; pepper');
  });

  it('renders emoji and unicode literally (no surrogate handling needed)', () => {
    const html = globalThis.recipeLib.createSimpleRecipeHtml({
      name: 'Pancakes 🥞',
      description: 'café au lait',
    });
    expect(html).toContain('Pancakes 🥞');
    expect(html).toContain('café au lait');
  });

  it('returns an empty string for non-object input', () => {
    expect(globalThis.recipeLib.createSimpleRecipeHtml(null)).toBe('');
    expect(globalThis.recipeLib.createSimpleRecipeHtml('nope')).toBe('');
    expect(globalThis.recipeLib.createSimpleRecipeHtml(undefined)).toBe('');
  });
});

// ---------------------------------------------------------------------------
// parseIngredientsTextarea
// ---------------------------------------------------------------------------

describe('parseIngredientsTextarea', () => {
  it('splits a one-per-line input into an array of trimmed lines', () => {
    expect(globalThis.recipeLib.parseIngredientsTextarea('flour\neggs\nmilk')).toEqual([
      'flour',
      'eggs',
      'milk',
    ]);
  });

  it('drops blank lines and surrounding whitespace', () => {
    const input = '  flour  \n\n   \neggs\n   \nmilk\n';
    expect(globalThis.recipeLib.parseIngredientsTextarea(input)).toEqual(['flour', 'eggs', 'milk']);
  });

  it('returns an empty array for an empty string or non-string input', () => {
    expect(globalThis.recipeLib.parseIngredientsTextarea('')).toEqual([]);
    expect(globalThis.recipeLib.parseIngredientsTextarea('   \n\n   ')).toEqual([]);
    expect(globalThis.recipeLib.parseIngredientsTextarea(null)).toEqual([]);
    expect(globalThis.recipeLib.parseIngredientsTextarea(undefined)).toEqual([]);
    expect(globalThis.recipeLib.parseIngredientsTextarea(42)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// isLikelyRecipeUrl
// ---------------------------------------------------------------------------

describe('isLikelyRecipeUrl', () => {
  it('accepts plain https URLs', () => {
    expect(globalThis.recipeLib.isLikelyRecipeUrl('https://example.com/cookies')).toBe(true);
    expect(globalThis.recipeLib.isLikelyRecipeUrl('http://example.com/cookies')).toBe(true);
  });

  it('rejects non-URL strings', () => {
    expect(globalThis.recipeLib.isLikelyRecipeUrl('not-a-url')).toBe(false);
    expect(globalThis.recipeLib.isLikelyRecipeUrl('example.com/cookies')).toBe(false);
  });

  it('rejects javascript: and file: schemes', () => {
    expect(globalThis.recipeLib.isLikelyRecipeUrl('javascript:alert(1)')).toBe(false);
    expect(globalThis.recipeLib.isLikelyRecipeUrl('file:///etc/passwd')).toBe(false);
    expect(globalThis.recipeLib.isLikelyRecipeUrl('  javascript:alert(1)')).toBe(false);
  });

  it('rejects empty and whitespace-only input', () => {
    expect(globalThis.recipeLib.isLikelyRecipeUrl('')).toBe(false);
    expect(globalThis.recipeLib.isLikelyRecipeUrl('   ')).toBe(false);
  });

  it('rejects non-string input', () => {
    expect(globalThis.recipeLib.isLikelyRecipeUrl(null)).toBe(false);
    expect(globalThis.recipeLib.isLikelyRecipeUrl(undefined)).toBe(false);
    expect(globalThis.recipeLib.isLikelyRecipeUrl(42)).toBe(false);
  });
});
