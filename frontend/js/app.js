// Register service worker for PWA
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then(registration => {
        console.log('ServiceWorker registration successful with scope:', registration.scope);
      })
      .catch(error => {
        console.error('ServiceWorker registration failed:', error);
      });
  });
}

// Check authentication status
document.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('auth_token');
  if (!token) {
    // Not logged in, redirect to login page
    window.location.href = 'login.html';
    return;
  }
  
  // Try to get user info from the token (JWT)
  try {
    const tokenPayload = JSON.parse(atob(token.split('.')[1]));
    const userEmail = tokenPayload.sub;
    document.querySelector('#userEmail span').textContent = userEmail;
  } catch (e) {
    console.error('Error parsing token:', e);
  }
});

// Initialize Bootstrap modal
const userModal = new bootstrap.Modal(document.getElementById('userModal'), {
  keyboard: false
});

// Get DOM elements
const userBtn = document.getElementById('userBtn');
const logoutBtn = document.getElementById('logoutBtn');
const photoInput = document.getElementById('photo');
const parseBtn = document.getElementById('parseBtn');
const outputDiv = document.getElementById('output');
const outputJson = document.getElementById('outputJson');
const recipeHtmlContainer = document.getElementById('recipe-html-container');
const viewJsonBtn = document.getElementById('viewJsonBtn');
const viewFullRecipeBtn = document.getElementById('viewFullRecipeBtn');
const bringImportCard = document.getElementById('bringImportCard');

// Event listeners
userBtn.addEventListener('click', () => {
  userModal.show();
});

logoutBtn.addEventListener('click', () => {
  localStorage.removeItem('auth_token');
  window.location.href = 'login.html';
});

// Toggle JSON visibility
viewJsonBtn.addEventListener('click', () => {
  const isHidden = outputJson.classList.contains('d-none');
  if (isHidden) {
    outputJson.classList.remove('d-none');
    viewJsonBtn.textContent = 'Hide JSON';
  } else {
    outputJson.classList.add('d-none');
    viewJsonBtn.textContent = 'Show JSON';
  }
});

parseBtn.addEventListener('click', async () => {
  const file = photoInput.files[0];
  if (!file) {
    alert('Please select an image file');
    return;
  }
  
  // Show loading state
  parseBtn.disabled = true;
  parseBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Parsing...';
  
  // Reset output container
  outputDiv.classList.add('d-none');
  recipeHtmlContainer.innerHTML = '';
  outputJson.textContent = '';
  viewJsonBtn.textContent = 'Show JSON';
  
  try {
    // Convert image to base64
    const base64Image = await fileToBase64(file);
    
    // Get token for authentication
    const token = localStorage.getItem('auth_token');
    if (!token) {
      throw new Error('Not authenticated. Please log in.');
    }
    
    // Send to backend API
    // The API expects the image as form data
    const formData = new FormData();
    formData.append('image', base64Image);
    
    const response = await fetch(`${config.apiUrl}/recipes/parse`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to parse recipe');
    }
    
    const result = await response.json();
    
    if (result && result.uuid) {
      // Get full recipe data as JSON
      const recipeResponse = await fetch(`${config.apiUrl}/recipes/${result.uuid}.json`);
      const recipeData = await recipeResponse.json();
      
      // Store the recipe JSON data
      outputJson.textContent = JSON.stringify(recipeData, null, 2);
      outputJson.classList.add('d-none'); // Make sure JSON is initially hidden
      
      // Try to get the HTML content
      try {
        const htmlResponse = await fetch(`${config.apiUrl}/recipes/${result.uuid}.html`);
        
        if (htmlResponse.ok) {
          // Get the HTML content as text
          const htmlContent = await htmlResponse.text();
          
          // Display the HTML content in the container
          recipeHtmlContainer.innerHTML = htmlContent;
          
          // Set up the full recipe view button
          viewFullRecipeBtn.href = `recipe-data.html?id=${result.uuid}`;
        } else {
          // If HTML content is not available, display a simplified version
          recipeHtmlContainer.innerHTML = createSimpleRecipeHtml(recipeData);
          viewFullRecipeBtn.href = `recipe-data.html?id=${result.uuid}`;
        }
      } catch (htmlError) {
        console.error('Error fetching HTML content:', htmlError);
        recipeHtmlContainer.innerHTML = createSimpleRecipeHtml(recipeData);
        viewFullRecipeBtn.href = `recipe-data.html?id=${result.uuid}`;
      }
      
      // Display the output container
      outputDiv.classList.remove('d-none');
      
      // Show Bring widget with recipe URL
      showBringWidget(result.uuid);
    } else {
      alert('Failed to parse the recipe. Please try again with a clearer image.');
    }
  } catch (error) {
    console.error('Error parsing recipe:', error);
    alert('Error: ' + error.message);
    
    // If unauthorized, redirect to login
    if (error.message.includes('authenticated') || error.message.includes('401')) {
      localStorage.removeItem('auth_token');
      window.location.href = 'login.html';
    }
  } finally {
    resetParseButton();
  }
});

// Helper functions
function resetParseButton() {
  parseBtn.disabled = false;
  parseBtn.innerHTML = 'Parse Recipe';
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      // Get the base64 string without the metadata prefix
      const base64String = reader.result;
      // The backend expects the full data URL
      resolve(base64String);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function showBringWidget(recipeUuid) {
  // Get the elements we need to update
  const bringImportCard = document.getElementById('bringImportCard');
  
  // Set the recipe URL for the Bring widget
  const recipeUrl = `${config.frontendUrl}/api/recipes/${recipeUuid}.html`;
  bringImportCard.setAttribute('data-bring-import', recipeUrl);
  window.bringwidgets.import.setUrl(recipeUrl)
  
  // Show the card
  bringImportCard.style.display = 'block';
  bringImportCard.classList.remove('d-none');
  
  // Force widget to reload with new data
  if (window.bringUpdateWidgets) {
    window.bringUpdateWidgets();
  } else {
    // Fallback: reload the Bring widget script
    const oldScript = document.querySelector('script[src*="platform.getbring.com"]');
    if (oldScript) {
      oldScript.remove();
    }
    
    const newScript = document.createElement('script');
    newScript.async = true;
    newScript.src = 'https://platform.getbring.com/widgets/import.js';
    document.head.appendChild(newScript);
  }
}



function showToast(message) {
  const toastContainer = document.createElement('div');
  toastContainer.className = 'position-fixed bottom-0 end-0 p-3';
  toastContainer.style.zIndex = '5000';
  
  toastContainer.innerHTML = `
    <div class="toast show" role="alert" aria-live="assertive" aria-atomic="true">
      <div class="toast-header">
        <strong class="me-auto">Recipe to Bring</strong>
        <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body">
        ${message}
      </div>
    </div>
  `;
  
  document.body.appendChild(toastContainer);
  
  setTimeout(() => {
    document.body.removeChild(toastContainer);
  }, 3000);
}

// Helper function to create a simple recipe HTML from JSON data
function createSimpleRecipeHtml(recipeData) {
  let html = `
    <div itemscope itemtype="http://schema.org/Recipe" class="recipe-container">
      <h2 itemprop="name">${recipeData.name || 'Recipe'}</h2>
      
      <div class="recipe-yield mb-3">
        <strong>Serves:</strong> <span itemprop="recipeYield">${recipeData.recipeYield || '4 servings'}</span>
      </div>`;
      
  if (recipeData.description) {
    html += `
      <div class="recipe-description mb-3">
        <h4>Description</h4>
        <p itemprop="description">${recipeData.description}</p>
      </div>`;
  }
  
  if (recipeData.recipeIngredient && recipeData.recipeIngredient.length) {
    html += `
      <div class="recipe-ingredients mb-3">
        <h4>Ingredients</h4>
        <ul>`;
        
    recipeData.recipeIngredient.forEach(ingredient => {
      html += `<li itemprop="recipeIngredient">${ingredient}</li>`;
    });
    
    html += `
        </ul>
      </div>`;
  }
  
  html += `</div>`;
  
  return html;
}

// Make sure the Bring widget is initialized when the page loads
window.addEventListener('DOMContentLoaded', () => {
  // Hide the import card initially
  const bringImportCard = document.getElementById('bringImportCard');
  if (bringImportCard) {
    bringImportCard.classList.add('d-none');
  }
});
