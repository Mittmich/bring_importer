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

  // Public Google OAuth Client ID for on-demand Calendar export. NOT a secret —
  // a Web OAuth client ID is meant to ship in client code; it's protected by the
  // Authorized JavaScript origins setting, not by secrecy. An env var (if set)
  // overrides this default; empty hides the "Export to calendar" button.
  GOOGLE_CLIENT_ID:
    '{{GOOGLE_CLIENT_ID}}' ||
    '822441136350-akcd6d6q5s2uj02ng3e2cjvc79j168cr.apps.googleusercontent.com',
};

// Migrate any existing localStorage config
if (localStorage.getItem('API_URL') && window.ENV.API_URL === '') {
  window.ENV.API_URL = localStorage.getItem('API_URL');
}

if (localStorage.getItem('FRONTEND_URL') && window.ENV.FRONTEND_URL === '') {
  window.ENV.FRONTEND_URL = localStorage.getItem('FRONTEND_URL');
}

if (localStorage.getItem('GOOGLE_CLIENT_ID') && !window.ENV.GOOGLE_CLIENT_ID) {
  window.ENV.GOOGLE_CLIENT_ID = localStorage.getItem('GOOGLE_CLIENT_ID');
}
