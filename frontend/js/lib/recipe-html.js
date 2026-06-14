// frontend/js/lib/recipe-html.js
//
// Pure helpers used across the frontend for rendering and validating
// recipe-shaped data. Loaded before app.js so it attaches to
// `globalThis.recipeLib` (a tiny UMD-ish shim).
//
// The functions here are deliberately small and dependency-free so
// they're trivial to unit-test under Vitest (step 13).

(function (root) {
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function createSimpleRecipeHtml(data) {
    if (!data || typeof data !== 'object') return '';
    const name = escapeHtml(data.name || 'Recipe');
    const yieldText = escapeHtml(data.recipeYield || '4 servings');
    const description = data.description ? `<p>${escapeHtml(data.description)}</p>` : '';
    const ingredients = Array.isArray(data.recipeIngredient) ? data.recipeIngredient : [];
    const ingredientList = ingredients.length
      ? '<ul>' +
        ingredients.map((i) => `<li itemprop="recipeIngredient">${escapeHtml(i)}</li>`).join('') +
        '</ul>'
      : '';

    return `<div itemscope itemtype="http://schema.org/Recipe" class="recipe-container">
  <h2 itemprop="name">${name}</h2>
  <p><strong>Serves:</strong> <span itemprop="recipeYield">${yieldText}</span></p>
  ${description}
  ${ingredientList}
</div>`;
  }

  function parseIngredientsTextarea(text) {
    if (typeof text !== 'string') return [];
    return text
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
  }

  function isLikelyRecipeUrl(url) {
    if (typeof url !== 'string') return false;
    const trimmed = url.trim();
    if (!trimmed) return false;
    if (trimmed.startsWith('javascript:')) return false;
    if (trimmed.startsWith('file:')) return false;
    // require an http(s) scheme
    return /^https?:\/\//i.test(trimmed);
  }

  root.recipeLib = {
    createSimpleRecipeHtml,
    parseIngredientsTextarea,
    isLikelyRecipeUrl,
    // Exposed for the unit tests; same impl as the private copy above.
    _escapeHtml: escapeHtml,
  };
})(typeof window !== 'undefined' ? window : globalThis);
