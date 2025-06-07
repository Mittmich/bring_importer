// auth.js
document.addEventListener('DOMContentLoaded', () => {
  // Check if already logged in
  const token = localStorage.getItem('auth_token');
  if (token) {
    window.location.href = 'index.html'; // Redirect to main app if already logged in
  }

  // DOM elements
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const loginLink = document.getElementById('login-link');
  const registerLink = document.getElementById('register-link');
  const loginBtn = document.getElementById('loginBtn');
  const registerBtn = document.getElementById('registerBtn');

  // Toggle between login and register forms
  registerLink.addEventListener('click', (e) => {
    e.preventDefault();
    loginForm.style.display = 'none';
    registerForm.style.display = 'block';
  });

  loginLink.addEventListener('click', (e) => {
    e.preventDefault();
    registerForm.style.display = 'none';
    loginForm.style.display = 'block';
  });

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
      const response = await fetch('http://localhost:8001/token', {
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

  // Handle registration
  registerBtn.addEventListener('click', async () => {
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value.trim();
    const confirmPassword = document.getElementById('reg-confirm-password').value.trim();

    if (!email || !password || !confirmPassword) {
      showMessage('Please fill in all fields', 'danger');
      return;
    }

    if (password !== confirmPassword) {
      showMessage('Passwords do not match', 'danger');
      return;
    }

    registerBtn.disabled = true;
    registerBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Registering...';

    try {
      const response = await fetch('http://localhost:8001/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          password
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Registration failed');
      }

      showMessage('Registration successful! You can now login.', 'success');
      
      // Switch to login form
      registerForm.style.display = 'none';
      loginForm.style.display = 'block';
      document.getElementById('email').value = email;
      document.getElementById('password').value = '';
      
    } catch (error) {
      showMessage(error.message, 'danger');
    } finally {
      registerBtn.disabled = false;
      registerBtn.textContent = 'Register';
    }
  });

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
