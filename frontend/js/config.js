// Config file for environment variables
const config = {
  // API backend URL with fallback to localhost
  apiUrl: localStorage.getItem('API_URL') || 'http://localhost:8001',
  
  // Frontend URL with fallback to localhost
  frontendUrl: localStorage.getItem('FRONTEND_URL') || 'http://localhost:8000'
};

// Freeze the config object to prevent modifications
Object.freeze(config);
