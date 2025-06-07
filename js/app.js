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

// Initialize Bootstrap modal
const settingsModal = new bootstrap.Modal(document.getElementById('settingsModal'), {
  keyboard: false
});

// Get DOM elements
const settingsBtn = document.getElementById('settingsBtn');
const apiKeyInput = document.getElementById('apiKey');
const saveKeyBtn = document.getElementById('saveKey');
const photoInput = document.getElementById('photo');
const parseBtn = document.getElementById('parseBtn');
const outputDiv = document.getElementById('output');
const outputJson = document.getElementById('outputJson');
const bringWidgetDiv = document.getElementById('bringWidget');

// Load API key from localStorage
const savedApiKey = localStorage.getItem('openai_api_key');
if (savedApiKey) {
  apiKeyInput.value = savedApiKey;
  updateParseButtonState();
}

// Event listeners
settingsBtn.addEventListener('click', () => {
  settingsModal.show();
});

saveKeyBtn.addEventListener('click', () => {
  const apiKey = apiKeyInput.value.trim();
  if (apiKey) {
    localStorage.setItem('openai_api_key', apiKey);
    updateParseButtonState();
    settingsModal.hide();
    showToast('API key saved successfully');
  } else {
    alert('Please enter a valid API key');
  }
});

photoInput.addEventListener('change', updateParseButtonState);

parseBtn.addEventListener('click', async () => {
  const file = photoInput.files[0];
  if (!file) return;
  
  // Show loading state
  parseBtn.disabled = true;
  parseBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Parsing...';
  outputDiv.classList.add('d-none');
  
  // Get API key from localStorage
  const apiKey = localStorage.getItem('openai_api_key');
  if (!apiKey) {
    alert('Please set your OpenAI API key in the settings');
    resetParseButton();
    return;
  }
  
  try {
    // Convert image to base64
    const base64Image = await fileToBase64(file);
    
    // Send to OpenAI API
    const recipe = await parseRecipeFromImage(base64Image, apiKey);
    
    if (recipe) {
      // Display the parsed recipe
      outputDiv.classList.remove('d-none');
      outputJson.textContent = JSON.stringify(recipe, null, 2);
      
      // Show Bring widget
      showBringWidget(recipe.items);
    } else {
      alert('Failed to parse the recipe. Please try again with a clearer image.');
    }
  } catch (error) {
    console.error('Error parsing recipe:', error);
    alert('Error: ' + error.message);
  } finally {
    resetParseButton();
  }
});

// Helper functions
function updateParseButtonState() {
  const hasApiKey = !!localStorage.getItem('openai_api_key');
  const hasPhoto = photoInput.files.length > 0;
  parseBtn.disabled = !(hasApiKey && hasPhoto);
}

function resetParseButton() {
  parseBtn.disabled = false;
  parseBtn.innerHTML = 'Parse Recipe';
  updateParseButtonState();
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const base64String = reader.result.split(',')[1];
      resolve(base64String);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function parseRecipeFromImage(base64Image, apiKey) {
  try {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: 'gpt-4o',
        messages: [
          {
            role: 'system',
            content: 'You are a helpful assistant that extracts recipe information from images.'
          },
          {
            role: 'user',
            content: [
              { 
                type: 'text', 
                text: 'Extract the recipe information from this image. Return a JSON with these fields: title (string), items (array of strings, each representing one ingredient with quantity). Format the items so they can be directly imported into a shopping list.' 
              },
              { 
                type: 'image_url', 
                image_url: { 
                  url: `data:image/jpeg;base64,${base64Image}` 
                } 
              }
            ]
          }
        ],
        max_tokens: 1000
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error?.message || 'API request failed');
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content;
    
    if (!content) {
      throw new Error('No content in response');
    }

    // Extract JSON object from the response
    const jsonMatch = content.match(/```json\n([\s\S]*?)\n```/) || content.match(/\{[\s\S]*\}/);
    const jsonContent = jsonMatch ? jsonMatch[1] || jsonMatch[0] : content;
    
    return JSON.parse(jsonContent);
  } catch (error) {
    console.error('OpenAI API error:', error);
    throw error;
  }
}

function showBringWidget(items) {
  if (!items || !items.length) {
    bringWidgetDiv.innerHTML = '<div class="alert alert-warning">No ingredients found to import</div>';
    return;
  }

  // Format items for Bring API
  const encodedItems = encodeURIComponent(items.join('\n'));
  
  // Create Bring API button
  bringWidgetDiv.innerHTML = `
    <div class="card mt-3">
      <div class="card-header bg-success text-white">
        Import to Bring
      </div>
      <div class="card-body">
        <p>${items.length} items ready to import</p>
        <a href="https://web.getbring.com/import/items/${encodedItems}" 
           target="_blank" 
           class="btn btn-success">Import to Bring</a>
      </div>
    </div>
  `;
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
