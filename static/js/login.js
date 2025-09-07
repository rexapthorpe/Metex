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
  let isSignup = false;

  // Open Sign-up side automatically when visiting /login?mode=signup
  try {
    const params = new URLSearchParams(window.location.search);
    if ((params.get('mode') || '').toLowerCase() === 'signup') {
      isSignup = true;
    }
  } catch (_) {}

  function render(){
    // When isSignup=true, we add .signup-mode (CSS moves overlay LEFT)
    card.classList.toggle('signup-mode', isSignup);

    // Opposite action on the overlay button
    overlayBtn.textContent = isSignup ? 'Log In' : 'Sign Up';
    overlayBtn.setAttribute('aria-label', isSignup ? 'Go to Login' : 'Go to Sign Up');

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
