// Config file for environment variables
const config = {
  // API backend URL with fallback to /api/ for Nginx reverse proxy
  apiUrl: localStorage.getItem('API_URL') || 'http://localhost:8001',
  
  // Frontend URL with fallback to current origin
  frontendUrl: localStorage.getItem('FRONTEND_URL') || window.location.origin
};

// Freeze the config object to prevent modifications
Object.freeze(config);
