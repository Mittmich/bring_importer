// Environment configuration for Recipe to Bring

// This file is processed by nginx's server-side rendering
// Values in {{ENV_VARIABLE}} format will be replaced with actual environment variables

window.ENV = {
  // API backend URL
  API_URL: '{{API_URL}}' || 'http://localhost:8001',

  // Frontend URL
  FRONTEND_URL: '{{FRONTEND_URL}}' || window.location.origin,

  // Application version
  APP_VERSION: '{{APP_VERSION}}' || '1.0.0',
};

// Migrate any existing localStorage config
if (localStorage.getItem('API_URL') && window.ENV.API_URL === '') {
  window.ENV.API_URL = localStorage.getItem('API_URL');
}

if (localStorage.getItem('FRONTEND_URL') && window.ENV.FRONTEND_URL === '') {
  window.ENV.FRONTEND_URL = localStorage.getItem('FRONTEND_URL');
}
