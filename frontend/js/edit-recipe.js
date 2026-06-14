// frontend/js/edit-recipe.js
//
// Loads the recipe from the backend, prefills the form, and PUTs back
// the structured fields on save. The original html_content is round-
// tripped as a hidden form field so the editor doesn't accidentally
// drop it.

(function () {
  const token = localStorage.getItem('auth_token');
  if (!token) {
    window.location.href = 'login.html';
    return;
  }

  const params = new URLSearchParams(window.location.search);
  const uuid = params.get('id');
  if (!uuid) {
    document.getElementById('loading').textContent = 'No recipe id in URL.';
    return;
  }

  const loading = document.getElementById('loading');
  const form = document.getElementById('editForm');
  const errorEl = document.getElementById('editError');
  const saveBtn = document.getElementById('saveBtn');

  const fields = {
    uuid: document.getElementById('recipeUuid'),
    html: document.getElementById('htmlContent'),
    title: document.getElementById('title'),
    yield: document.getElementById('recipeYield'),
    description: document.getElementById('description'),
    ingredients: document.getElementById('ingredients'),
    note: document.getElementById('note'),
  };

  function parseIngredients(arr) {
    if (Array.isArray(arr)) return arr.join('\n');
    return '';
  }

  async function load() {
    try {
      const resp = await fetch(`${config.apiUrl}/recipes/${uuid}.json`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.status === 401) {
        localStorage.removeItem('auth_token');
        window.location.href = 'login.html';
        return;
      }
      if (!resp.ok) {
        throw new Error(`Could not load recipe (HTTP ${resp.status}).`);
      }
      const data = await resp.json();
      fields.uuid.value = data['@type'] === 'Recipe' || data.name ? uuid : uuid;
      fields.uuid.value = uuid;
      fields.html.value = data.html_content || '';
      fields.title.value = data.name || '';
      fields.yield.value = data.recipeYield || '';
      fields.description.value = data.description || '';
      fields.ingredients.value = parseIngredients(data.recipeIngredient);
      fields.note.value = data.note || '';

      loading.classList.add('d-none');
      form.classList.remove('d-none');
    } catch (err) {
      loading.textContent = err.message;
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorEl.classList.add('d-none');
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Saving…';

    const body = {
      title: fields.title.value.trim(),
      recipeIngredient: fields.ingredients.value
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
      recipeYield: fields.yield.value.trim() || '4 servings',
      description: fields.description.value.trim() || undefined,
      note: fields.note.value.trim() || undefined,
      html_content: fields.html.value || undefined,
    };

    try {
      const resp = await fetch(`${config.apiUrl}/recipes/${uuid}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const detail = (await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`;
        throw new Error(detail);
      }
      window.location.href = `recipe-data.html?id=${uuid}`;
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('d-none');
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save';
    }
  });

  load();
})();
