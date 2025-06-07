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
const cameraBtn = document.getElementById('cameraBtn');
const parseBtn = document.getElementById('parseBtn');
const outputDiv = document.getElementById('output');
const outputJson = document.getElementById('outputJson');
const recipeHtmlContainer = document.getElementById('recipe-html-container');
const viewJsonBtn = document.getElementById('viewJsonBtn');
const viewFullRecipeBtn = document.getElementById('viewFullRecipeBtn');
const bringImportCard = document.getElementById('bringImportCard');

// Check for camera support
const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
const hasMediaDevices = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
const isiOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
const isAndroid = /Android/.test(navigator.userAgent);

// Update UI based on device capabilities
document.addEventListener('DOMContentLoaded', () => {
  if (isMobileDevice && hasMediaDevices) {
    // Show camera hint for mobile devices with camera support
    document.querySelector('.text-muted.mt-1').style.display = 'block';
    cameraBtn.style.display = 'block';
  } else {
    // Hide camera hint for desktop devices
    document.querySelector('.text-muted.mt-1').style.display = 'none';
  }
});

// Event listeners
userBtn.addEventListener('click', () => {
  userModal.show();
});

logoutBtn.addEventListener('click', () => {
  localStorage.removeItem('auth_token');
  window.location.href = 'login.html';
});

// Camera button functionality
cameraBtn.addEventListener('click', () => {
  // For devices with camera support, trigger the file input with capture
  if (isMobileDevice && hasMediaDevices) {
    // Create a temporary input with capture attribute for taking a photo
    const tempInput = document.createElement('input');
    tempInput.type = 'file';
    tempInput.accept = 'image/*';
    tempInput.capture = 'environment'; // Use the back camera
    
    // Handle the file selection
    tempInput.addEventListener('change', (event) => {
      if (event.target.files && event.target.files[0]) {
        // Copy the selected file to the main file input
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(event.target.files[0]);
        photoInput.files = dataTransfer.files;
        
        // Show a preview if desired
        showImagePreview(event.target.files[0]);
      }
    });
    
    // Trigger the file selection dialog
    tempInput.click();
  } else {
    // For desktop or unsupported devices, just click the regular file input
    photoInput.click();
  }
});

// Preview the selected image
function showImagePreview(file) {
  // Create or get the preview element
  let previewContainer = document.getElementById('image-preview-container');
  if (!previewContainer) {
    previewContainer = document.createElement('div');
    previewContainer.id = 'image-preview-container';
    previewContainer.className = 'mt-3 text-center';
    photoInput.parentNode.parentNode.appendChild(previewContainer);
  }
  
  // Clear any previous preview
  previewContainer.innerHTML = `
    <div class="spinner-border text-primary" role="status">
      <span class="visually-hidden">Loading...</span>
    </div>
    <div class="text-muted small mt-2">Processing image...</div>
  `;
  
  // Process the image through our optimization function for preview
  fileToBase64(file)
    .then(optimizedImage => {
      previewContainer.innerHTML = `
        <div class="position-relative d-inline-block">
          <img src="${optimizedImage}" alt="Recipe preview" style="max-height: 200px; max-width: 100%;" class="rounded shadow-sm">
          <button type="button" class="btn btn-sm btn-light position-absolute top-0 end-0 m-1" id="remove-preview">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
            </svg>
          </button>
        </div>
        <div class="text-muted small mt-1">Image optimized for processing</div>
      `;
      
      // Add click handler to the remove button
      document.getElementById('remove-preview').addEventListener('click', () => {
        previewContainer.innerHTML = '';
        photoInput.value = ''; // Clear the file input
        
        // Also remove any reduction message
        if (window.sizeReductionMessage && window.sizeReductionMessage.parentNode) {
          window.sizeReductionMessage.parentNode.removeChild(window.sizeReductionMessage);
          window.sizeReductionMessage = null;
        }
      });
    })
    .catch(error => {
      previewContainer.innerHTML = `
        <div class="alert alert-danger">
          <p>Error processing image preview: ${error.message}</p>
          <button class="btn btn-sm btn-outline-danger" id="clear-error-preview">Try Again</button>
        </div>
      `;
      
      document.getElementById('clear-error-preview').addEventListener('click', () => {
        previewContainer.innerHTML = '';
        photoInput.value = '';
      });
    });
}

// Handle file selection from the regular input
photoInput.addEventListener('change', (event) => {
  if (event.target.files && event.target.files[0]) {
    showImagePreview(event.target.files[0]);
  }
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
    alert('Please select an image file or take a photo');
    return;
  }
  
  // Show loading state
  parseBtn.disabled = true;
  parseBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Parsing...';
  
  // Hide the preview while processing
  const previewContainer = document.getElementById('image-preview-container');
  if (previewContainer) {
    previewContainer.style.opacity = '0.5';
  }
  
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
      
      // Keep size reduction message visible for a while then fade it out
      if (window.sizeReductionMessage) {
        window.sizeReductionMessage.style.display = 'block';
        
        // Add a specific class for styling
        window.sizeReductionMessage.classList.add('processing-complete');
        
        // Remove the message after 12 seconds with a fade effect
        setTimeout(() => {
          if (window.sizeReductionMessage) {
            window.sizeReductionMessage.style.opacity = '0';
            window.sizeReductionMessage.style.transition = 'opacity 1s';
            
            setTimeout(() => {
              if (window.sizeReductionMessage && window.sizeReductionMessage.parentNode) {
                window.sizeReductionMessage.parentNode.removeChild(window.sizeReductionMessage);
              }
              window.sizeReductionMessage = null;
            }, 1000);
          }
        }, 12000);
      }
      
      // Show Bring widget with recipe URL
      showBringWidget(result.uuid);
    } else {
      alert('Failed to parse the recipe. Please try again with a clearer image.');
    }
  } catch (error) {
    console.error('Error parsing recipe:', error);
    
    // Display a better error message for image processing issues
    if (error.message.includes('image') || error.message.includes('file')) {
      // Create a structured error message for image-related errors
      const errorContainer = document.createElement('div');
      errorContainer.className = 'alert alert-danger mt-3';
      errorContainer.innerHTML = `
        <h5>Image Processing Error</h5>
        <p>${error.message}</p>
        <p>Please try with a different image or take a clearer photo.</p>
      `;
      
      // Replace any existing notification with the error
      if (window.sizeReductionMessage && window.sizeReductionMessage.parentNode) {
        window.sizeReductionMessage.parentNode.removeChild(window.sizeReductionMessage);
      }
      window.sizeReductionMessage = errorContainer;
      document.querySelector('#photo').parentNode.parentNode.appendChild(errorContainer);
      
      // Remove error after 15 seconds
      setTimeout(() => {
        if (errorContainer.parentNode) {
          errorContainer.parentNode.removeChild(errorContainer);
        }
        window.sizeReductionMessage = null;
      }, 15000);
    } else {
      // For other errors, use a simpler alert
      alert('Error: ' + error.message);
    }
    
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
  
  // Restore preview opacity
  const previewContainer = document.getElementById('image-preview-container');
  if (previewContainer) {
    previewContainer.style.opacity = '1';
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    // Check if file is an image
    if (!file.type.match('image.*')) {
      return resolve(null);
    }
    
    const reader = new FileReader();
    reader.onload = (event) => {
      const img = new Image();
      img.onload = () => {
        // Max dimensions for the image
        const MAX_WIDTH = 1200;
        const MAX_HEIGHT = 1200;
        // Quality setting for JPEG compression (0.0 to 1.0)
        const QUALITY = 0.85;
        
        let width = img.width;
        let height = img.height;
        let resized = false;
        let sizeReduction = '';
        
        // Calculate original image size in KB
        const originalSize = Math.round(file.size / 1024);
        
        // Always resize images to reasonable dimensions if they're large
        if (width > MAX_WIDTH || height > MAX_HEIGHT) {
          if (width > height) {
            // Landscape image
            if (width > MAX_WIDTH) {
              height = Math.round(height * (MAX_WIDTH / width));
              width = MAX_WIDTH;
              resized = true;
            }
          } else {
            // Portrait image
            if (height > MAX_HEIGHT) {
              width = Math.round(width * (MAX_HEIGHT / height));
              height = MAX_HEIGHT;
              resized = true;
            }
          }
        }
        
        // Create canvas and resize image
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = "white"; // Use white background
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, width, height);
        
        // Get resized image as base64 string with quality setting
        const fileType = file.type === 'image/png' ? 'image/png' : 'image/jpeg';
        const base64String = canvas.toDataURL(fileType, QUALITY);
        
        // Estimate the new size in KB (very rough approximation)
        const base64Data = base64String.split(',')[1];
        const newSizeBytes = Math.round((base64Data.length * 3) / 4);
        const newSize = Math.round(newSizeBytes / 1024);
        
        // Create notification about the processing
        const processingInfo = resized ? 
          `Image resized from ${img.width}×${img.height} to ${width}×${height}` :
          `Image processed at ${width}×${height}`;
          
        const sizeInfo = `Size: ~${originalSize}KB → ~${newSize}KB`;
        sizeReduction = `${processingInfo}<br>${sizeInfo}`;
        
        // Always show notification about the processing
        if (!window.sizeReductionMessage) {
          window.sizeReductionMessage = document.createElement('div');
          window.sizeReductionMessage.className = 'alert alert-info mt-2';
          window.sizeReductionMessage.style.display = 'block';
          document.querySelector('#photo').parentNode.parentNode.appendChild(window.sizeReductionMessage);
        }
        window.sizeReductionMessage.innerHTML = sizeReduction;
        
        resolve(base64String);
      };
      
      img.onerror = () => {
        reject(new Error('Failed to load image'));
      };
      
      img.src = event.target.result;
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
