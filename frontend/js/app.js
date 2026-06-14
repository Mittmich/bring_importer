// Register service worker for PWA
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/service-worker.js')
      .then((reg) => console.log('ServiceWorker registered:', reg.scope))
      .catch((err) => console.error('ServiceWorker registration failed:', err));
  });
}

// ----- Auth gate -----
const token = localStorage.getItem('auth_token');
let currentUserEmail = '';
if (!token) {
  window.location.href = 'login.html';
} else {
  try {
    currentUserEmail = JSON.parse(atob(token.split('.')[1])).sub || '';
  } catch (e) {
    console.error('Error parsing token:', e);
  }
}

// ----- DOM refs -----
const userBtn = document.getElementById('userBtn');
const logoutBtn = document.getElementById('logoutBtn');
const userModalEl = document.getElementById('userModal');
const userModal = new bootstrap.Modal(userModalEl, { keyboard: false });
const installBtn = document.getElementById('installBtn');
const recipeListEl = document.getElementById('recipe-list');
const recipeListEmptyEl = document.getElementById('recipe-list-empty');
const seeAllLink = document.getElementById('seeAllLink');

if (currentUserEmail && document.querySelector('#userEmail span')) {
  document.querySelector('#userEmail span').textContent = currentUserEmail;
}

// ----- Recipe list (load on page open) -----
async function loadRecipeList() {
  recipeListEmptyEl.textContent = 'Loading…';
  try {
    const resp = await fetch(`${config.apiUrl}/recipes`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (resp.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = 'login.html';
      return;
    }
    if (!resp.ok) {
      throw new Error(`Server returned ${resp.status}`);
    }
    const recipes = await resp.json();
    renderRecipeList(recipes);
  } catch (err) {
    recipeListEmptyEl.textContent = 'Could not load recipes. Pull to retry.';
    console.error(err);
  }
}

function renderRecipeList(recipes) {
  recipeListEl.innerHTML = '';
  if (!recipes || recipes.length === 0) {
    recipeListEmptyEl.textContent = 'No recipes yet — import one to get started.';
    recipeListEl.appendChild(recipeListEmptyEl);
    seeAllLink.style.display = 'none';
    return;
  }
  const recent = recipes.slice(0, 10);
  for (const r of recent) {
    const a = document.createElement('a');
    a.href = `recipe-data.html?id=${r.uuid}`;
    a.className =
      'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
    a.innerHTML = `
      <div>
        <div class="fw-semibold">${escapeHtml(r.title || 'Untitled')}</div>
        <div class="small text-muted">${formatSource(r.source)}</div>
      </div>
      <span class="badge bg-light text-secondary">${formatDate(r.datePublished)}</span>
    `;
    recipeListEl.appendChild(a);
  }
  seeAllLink.style.display = recipes.length > 10 ? 'inline-block' : 'none';
}

function formatSource(source) {
  if (!source) return '';
  if (source.kind === 'image') return 'Imported from photo';
  if (source.kind === 'url') return `From ${truncate(source.value || '', 40)}`;
  return 'Imported';
}

function formatDate(d) {
  if (!d) return '';
  // datePublished is YYYY-MM-DD; render as Mon DD
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  const parts = d.split('-');
  if (parts.length !== 3) return d;
  return `${months[parseInt(parts[1], 10) - 1]} ${parseInt(parts[2], 10)}`;
}

function truncate(s, n) {
  if (!s) return '';
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ----- User / install -----
userBtn.addEventListener('click', () => userModal.show());
logoutBtn.addEventListener('click', () => {
  localStorage.removeItem('auth_token');
  window.location.href = 'login.html';
});

let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  if (installBtn) installBtn.classList.remove('d-none');
});
if (installBtn) {
  installBtn.addEventListener('click', async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null;
    installBtn.classList.add('d-none');
  });
}

// ----- Import from photo -----
const photoInput = document.getElementById('photo');
const cameraBtn = document.getElementById('cameraBtn');
const photoParseBtn = document.getElementById('photoParseBtn');
const cameraHint = document.getElementById('cameraHint');
const photoModalError = document.getElementById('photoModalError');
const previewModalEl = document.getElementById('previewModal');
const previewModal = new bootstrap.Modal(previewModalEl);
const previewHtml = document.getElementById('previewHtml');
const saveToLibraryBtn = document.getElementById('saveToLibraryBtn');
const addToBringBtn = document.getElementById('addToBringBtn');
const photoModalEl = document.getElementById('importPhotoModal');

const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
  navigator.userAgent,
);
const hasMediaDevices = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

if (!isMobileDevice || !hasMediaDevices) {
  if (cameraHint) cameraHint.style.display = 'none';
  if (cameraBtn) cameraBtn.style.display = 'none';
}

cameraBtn.addEventListener('click', () => {
  if (isMobileDevice && hasMediaDevices) {
    const temp = document.createElement('input');
    temp.type = 'file';
    temp.accept = 'image/*';
    temp.capture = 'environment';
    temp.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        const dt = new DataTransfer();
        dt.items.add(e.target.files[0]);
        photoInput.files = dt.files;
        showImagePreview(e.target.files[0]);
      }
    });
    temp.click();
  } else {
    photoInput.click();
  }
});

photoInput.addEventListener('change', (e) => {
  if (e.target.files && e.target.files[0]) showImagePreview(e.target.files[0]);
});

function showImagePreview(file) {
  const container = document.getElementById('image-preview-container');
  container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
  fileToBase64(file)
    .then((b64) => {
      if (!b64) {
        container.innerHTML = '';
        return;
      }
      container.innerHTML = `
        <div class="text-center">
          <img src="${b64}" alt="preview" class="rounded shadow-sm" style="max-height:200px;max-width:100%;">
        </div>`;
    })
    .catch((err) => {
      photoModalError.textContent = err.message || 'Could not process the image.';
      photoModalError.classList.remove('d-none');
    });
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    if (!file.type.match('image.*')) return resolve(null);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        const MAX = 1200;
        let w = img.width,
          h = img.height;
        if (w > MAX || h > MAX) {
          if (w > h) {
            h = Math.round(h * (MAX / w));
            w = MAX;
          } else {
            w = Math.round(w * (MAX / h));
            h = MAX;
          }
        }
        const c = document.createElement('canvas');
        c.width = w;
        c.height = h;
        const ctx = c.getContext('2d');
        ctx.fillStyle = 'white';
        ctx.fillRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);
        resolve(c.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = () => reject(new Error('Failed to load image'));
      img.src = ev.target.result;
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsDataURL(file);
  });
}

photoParseBtn.addEventListener('click', async () => {
  const file = photoInput.files[0];
  if (!file) {
    photoModalError.textContent = 'Please choose an image first.';
    photoModalError.classList.remove('d-none');
    return;
  }
  photoModalError.classList.add('d-none');
  photoParseBtn.disabled = true;
  photoParseBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Parsing…';

  try {
    const b64 = await fileToBase64(file);
    const fd = new FormData();
    fd.append('image', b64);
    const resp = await fetch(`${config.apiUrl}/recipes/parse`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    });
    if (!resp.ok) {
      const detail = (await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`;
      throw new Error(detail);
    }
    const r = await resp.json();
    // Fetch the JSON + HTML for preview.
    const jsonResp = await fetch(`${config.apiUrl}/recipes/${r.uuid}.json`);
    const jsonData = await jsonResp.json();
    const htmlResp = await fetch(`${config.apiUrl}/recipes/${r.uuid}.html`);
    const htmlContent = htmlResp.ok ? await htmlResp.text() : '';

    previewHtml.innerHTML =
      htmlContent ||
      (window.recipeLib && window.recipeLib.createSimpleRecipeHtml
        ? window.recipeLib.createSimpleRecipeHtml(jsonData)
        : `<p>${escapeHtml(jsonData.name || 'Recipe')}</p>`);
    previewHtml.dataset.uuid = r.uuid;

    // Close the photo modal, open the preview modal.
    bootstrap.Modal.getInstance(photoModalEl).hide();
    previewModal.show();
  } catch (err) {
    photoModalError.textContent = err.message;
    photoModalError.classList.remove('d-none');
  } finally {
    photoParseBtn.disabled = false;
    photoParseBtn.textContent = 'Parse Recipe';
  }
});

// ----- Import from URL -----
const importUrlInput = document.getElementById('importUrlInput');
const importUrlNote = document.getElementById('importUrlNote');
const urlImportBtn = document.getElementById('urlImportBtn');
const urlModalError = document.getElementById('urlModalError');
const urlModalLoading = document.getElementById('urlModalLoading');
const urlModalEl = document.getElementById('importUrlModal');

urlImportBtn.addEventListener('click', async () => {
  const url = (importUrlInput.value || '').trim();
  if (!url) {
    urlModalError.textContent = 'Please paste a URL.';
    urlModalError.classList.remove('d-none');
    return;
  }
  if (
    window.recipeLib &&
    window.recipeLib.isLikelyRecipeUrl &&
    !window.recipeLib.isLikelyRecipeUrl(url)
  ) {
    urlModalError.textContent = "That doesn't look like a recipe page URL.";
    urlModalError.classList.remove('d-none');
    return;
  }
  urlModalError.classList.add('d-none');
  urlModalLoading.classList.remove('d-none');
  urlImportBtn.disabled = true;

  try {
    const resp = await fetch(`${config.apiUrl}/recipes/import-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ url, note: importUrlNote.value || '' }),
    });
    if (!resp.ok) {
      const detail = (await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`;
      throw new Error(detail);
    }
    const r = await resp.json();
    const jsonResp = await fetch(`${config.apiUrl}/recipes/${r.uuid}.json`);
    const jsonData = await jsonResp.json();
    previewHtml.innerHTML =
      window.recipeLib && window.recipeLib.createSimpleRecipeHtml
        ? window.recipeLib.createSimpleRecipeHtml(jsonData)
        : `<p>${escapeHtml(jsonData.name || 'Recipe')}</p>`;
    previewHtml.dataset.uuid = r.uuid;

    bootstrap.Modal.getInstance(urlModalEl).hide();
    previewModal.show();
  } catch (err) {
    urlModalError.textContent = err.message;
    urlModalError.classList.remove('d-none');
  } finally {
    urlModalLoading.classList.add('d-none');
    urlImportBtn.disabled = false;
  }
});

// ----- Preview modal actions -----
saveToLibraryBtn.addEventListener('click', () => {
  // The recipe is already saved on parse/import-url. Just close and refresh.
  previewModal.hide();
  showToast('Saved');
  loadRecipeList();
});

addToBringBtn.addEventListener('click', () => {
  const uuid = previewHtml.dataset.uuid;
  if (!uuid || typeof showBringWidget !== 'function') return;
  previewModal.hide();
  showBringWidget(uuid);
});

// ----- Toast -----
function showToast(message) {
  const host = document.getElementById('toastHost');
  if (!host) return;
  const el = document.createElement('div');
  el.className = 'position-fixed bottom-0 end-0 p-3';
  el.style.zIndex = '5000';
  el.innerHTML = `
    <div class="toast show" role="alert">
      <div class="toast-body">${escapeHtml(message)}</div>
    </div>`;
  host.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ----- Initial load -----
loadRecipeList();
