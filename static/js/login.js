// Show exactly one form at every width; reserve the height of the taller form.
(function () {
  const card = document.getElementById('authCard');
  if (!card) return;
  const page = card.closest('.login-page');
  const panes = {login: document.getElementById('login-pane'), signup: document.getElementById('signup-pane')};
  const controls = card.querySelectorAll('[data-swap]');
  let mode = page.classList.contains('is-signup') ? 'signup' : 'login';
  let switching = false;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  async function change(next) {
    if (next === mode || switching) return;
    switching = true;
    controls.forEach(button => { button.disabled = true; });
    const previous = panes[mode];
    previous.inert = true;
    page.classList.toggle('is-signup', next === 'signup');
    try {
      if (!reduced.matches) await previous.animate([{transform:'translateX(0)',opacity:1},{transform:'translateX(-70px)',opacity:0}],{duration:180,easing:'ease-in',fill:'forwards'}).finished;
      previous.hidden = true;
      previous.getAnimations().forEach(animation => animation.cancel());
      panes[next].hidden = false;
      panes[next].inert = false;
      mode = next;
      controls.forEach(button => button.setAttribute('aria-pressed',String(button.dataset.swap === mode)));
      const url = new URL(window.location.href);
      if (mode === 'signup') url.searchParams.set('mode','signup'); else url.searchParams.delete('mode');
      window.history.replaceState(null,'',url);
      if (!reduced.matches) await panes[next].animate([{transform:'translateX(70px)',opacity:0},{transform:'translateX(0)',opacity:1}],{duration:240,easing:'ease-out'}).finished;
    } finally {
      switching = false;
      controls.forEach(button => { button.disabled = false; });
      card.querySelector(`[data-swap="${mode}"]`).focus({preventScroll:true});
    }
  }
  controls.forEach(button => button.addEventListener('click',() => change(button.dataset.swap)));
  [['togglePassword','password'],['togglePasswordSignup','new_password']].forEach(([buttonId,inputId]) => {
    const button = document.getElementById(buttonId), input = document.getElementById(inputId);
    if (!button || !input) return;
    button.addEventListener('click',() => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.textContent = show ? 'Hide' : 'Show';
      button.setAttribute('aria-pressed',String(show));
    });
  });
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
      .then(async resp => {
        // Redirect only after an explicit successful JSON response. This keeps
        // proxy, database, and application errors from looking like a login.
        const contentType = resp.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
          const data = await resp.json();
          if (!resp.ok) {
            throw new Error(data.message || data.error || 'Sign-in is temporarily unavailable.');
          }
          return data;
        }

        const text = await resp.text();
        if (!resp.ok) {
          throw new Error(text.includes('Invalid')
            ? 'Invalid username or password'
            : 'Sign-in is temporarily unavailable. Please try again shortly.');
        }
        throw new Error('The sign-in service returned an unexpected response.');
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
