// Slide-over state & opposite CTA text
(function(){
  const card = document.getElementById('authCard');
  const overlayBtn = document.getElementById('overlayToggle');
  const overlayTitle = document.getElementById('overlayTitle');
  const overlayText  = document.getElementById('overlayText');

  // Guard if this page isn't the auth page
  if (!card || !overlayBtn || !overlayTitle || !overlayText) return;

  const swapLinks = document.querySelectorAll('[data-swap]');

  // DEFAULT: show LOGIN (left) with overlay on the RIGHT
  let isSignup = true;

  // Open Sign-up side automatically when visiting /login?mode=signup
  try {
    const params = new URLSearchParams(window.location.search);
    if ((params.get('mode') || '').toLowerCase() === 'signup') {
      isSignup = false;
    }
  } catch (_) {}

  function render(){
    // When isSignup=true, we add .signup-mode (CSS moves overlay RIGHT to show login)
    card.classList.toggle('signup-mode', isSignup);

    // Opposite action on the overlay button
    overlayBtn.textContent = isSignup ? 'Sign Up' : 'Log In';
    overlayBtn.setAttribute('aria-label', isSignup ? 'Go to Sign Up' : 'Go to Login');

    // Overlay copy
    overlayTitle.textContent = isSignup ? 'Hello!' : 'Welcome Back!';
    overlayText.textContent  = isSignup
      ? 'Enter your details to create an account.'
      : 'Enter your details to sign in.';
  }

  function toggle(){
    isSignup = !isSignup;
    render();
  }

  overlayBtn.addEventListener('click', toggle);

  swapLinks.forEach(el => el.addEventListener('click', (e)=>{
    e.preventDefault();
    const target = el.getAttribute('data-swap'); // 'signup' | 'login'
    isSignup = (target === 'signup');
    render();
  }));

  // Show/Hide password in Login pane
  const togglePwd = document.getElementById('togglePassword');
  const pwd = document.getElementById('password');
  if (togglePwd && pwd){
    togglePwd.addEventListener('click', ()=>{
      const isPwd = pwd.type === 'password';
      pwd.type = isPwd ? 'text' : 'password';
      togglePwd.textContent = isPwd ? 'Hide' : 'Show';
      togglePwd.setAttribute('aria-pressed', String(isPwd));
    });
  }

  // Show/Hide password in Sign-up pane
  const togglePwd2 = document.getElementById('togglePasswordSignup');
  const pwd2 = document.getElementById('new_password');
  if (togglePwd2 && pwd2){
    togglePwd2.addEventListener('click', ()=>{
      const isPwd = pwd2.type === 'password';
      pwd2.type = isPwd ? 'text' : 'password';
      togglePwd2.textContent = isPwd ? 'Hide' : 'Show';
      togglePwd2.setAttribute('aria-pressed', String(isPwd));
    });
  }

  // Initial paint
  render();
})();

// Handle login form submission via AJAX
document.addEventListener('DOMContentLoaded', function() {
  const loginForm = document.querySelector('.login-form');

  if (loginForm) {
    loginForm.addEventListener('submit', function(e) {
      e.preventDefault();

      const formData = new FormData(loginForm);

      fetch('/login', {
        method: 'POST',
        body: formData,
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
      .then(resp => {
        // Check if response is JSON or plain text
        const contentType = resp.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
          return resp.json();
        } else {
          // Handle plain text error response
          return resp.text().then(text => {
            if (text.includes('Invalid')) {
              throw new Error('Invalid username or password');
            }
            // If it's not an error, it might be a redirect page - reload to follow it
            window.location.href = '/buy';
          });
        }
      })
      .then(data => {
        if (data && data.success) {
          window.location.href = data.redirect || '/buy';
        } else if (data && !data.success) {
          openErrorNotificationModal(data.message || 'Invalid username or password', 'Login Failed');
        }
      })
      .catch(err => {
        openErrorNotificationModal(err.message || 'Invalid username or password', 'Login Failed');
      });
    });
  }

  // Handle signup form submission via AJAX
  const signupForm = document.querySelector('.signup-form');

  if (signupForm) {
    signupForm.addEventListener('submit', function(e) {
      e.preventDefault();

      const formData = new FormData(signupForm);

      fetch('/register', {
        method: 'POST',
        body: formData,
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
      .then(resp => {
        const contentType = resp.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
          return resp.json();
        } else {
          return resp.text().then(text => {
            if (text.includes('already exists') || text.includes('already taken')) {
              throw new Error(text);
            }
            // If it's not an error, redirect
            window.location.href = '/buy';
          });
        }
      })
      .then(data => {
        if (data && data.success) {
          window.location.href = data.redirect || '/buy';
        } else if (data && !data.success) {
          // Show specific error modal based on the field
          if (data.field === 'email') {
            openErrorNotificationModal(data.message, 'Email Already Registered');
          } else if (data.field === 'username') {
            openErrorNotificationModal(data.message, 'Username Taken');
          } else {
            openErrorNotificationModal(data.message || 'Registration failed', 'Registration Error');
          }
        }
      })
      .catch(err => {
        openErrorNotificationModal(err.message || 'Registration failed. Please try again.', 'Registration Error');
      });
    });
  }
});
