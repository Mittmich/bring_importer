// Config file for environment variables
const config = {
  // API backend URL with fallback to /api/ for Nginx reverse proxy
  apiUrl: window.ENV && window.ENV.API_URL ? window.ENV.API_URL : localStorage.getItem('API_URL') || 'http://localhost:8001',
  
  // Frontend URL with fallback to current origin
  frontendUrl: window.ENV && window.ENV.FRONTEND_URL ? window.ENV.FRONTEND_URL : localStorage.getItem('FRONTEND_URL') || window.location.origin,
  
  // App version
  version: window.ENV && window.ENV.APP_VERSION ? window.ENV.APP_VERSION : '1.0.0'
};

// Freeze the config object to prevent modifications
Object.freeze(config);
