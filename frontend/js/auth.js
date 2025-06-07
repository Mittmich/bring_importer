// auth.js
document.addEventListener('DOMContentLoaded', () => {
  // Check if already logged in
  const token = localStorage.getItem('auth_token');
  if (token) {
    window.location.href = 'index.html'; // Redirect to main app if already logged in
  }

  // DOM elements
  const loginForm = document.getElementById('login-form');
  const loginBtn = document.getElementById('loginBtn');

  // Handle login
  loginBtn.addEventListener('click', async () => {
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value.trim();

    if (!email || !password) {
      showMessage('Please fill in all fields', 'danger');
      return;
    }

    loginBtn.disabled = true;
    loginBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Loading...';

    try {
      const response = await fetch(`${config.apiUrl}/token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({
          'username': email, // FastAPI OAuth expects 'username' not 'email'
          'password': password
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }

      // Store token and redirect
      localStorage.setItem('auth_token', data.access_token);
      window.location.href = 'index.html';
    } catch (error) {
      showMessage(error.message, 'danger');
      loginBtn.disabled = false;
      loginBtn.textContent = 'Login';
    }
  });

  // Registration functionality has been removed

  // Helper function to show messages
  function showMessage(message, type = 'info') {
    // Check if a message container already exists and remove it
    const existingAlert = document.querySelector('.alert');
    if (existingAlert) {
      existingAlert.remove();
    }

    // Create new alert
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} mt-3`;
    alertDiv.role = 'alert';
    alertDiv.textContent = message;

    // Add alert before the form
    const cardBody = document.querySelector('.card-body');
    cardBody.insertBefore(alertDiv, cardBody.firstChild);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      alertDiv.remove();
    }, 5000);
  }
});
