/* Animate navigation into authentication; ordinary navigation remains the fallback. */
(function () {
  const content = document.querySelector('body > main.container');
  if (!content) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let entered = false;
  try { entered = sessionStorage.getItem('metex-auth-entry') === window.location.pathname; sessionStorage.removeItem('metex-auth-entry'); } catch (_) {}
  if (entered && !reduced.matches) {
    content.animate([{transform:'translateX(80px)',opacity:0},{transform:'translateX(0)',opacity:1}],{duration:300,easing:'ease-out'});
    const curves = content.querySelector('.auth-curves');
    if (curves) curves.animate([{transform:'translateY(30px) rotate(-5deg)'},{transform:'translateY(0) rotate(0)'}],{duration:600,easing:'ease-out'});
  }
  window.addEventListener('pageshow',event => {
    if (event.persisted) content.getAnimations().forEach(animation => animation.cancel());
  });
  let navigating = false;
  document.addEventListener('click',async event => {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
    const destination = new URL(link.href,window.location.href);
    if (destination.origin !== window.location.origin || destination.pathname !== '/login' || reduced.matches) return;
    if (destination.href === window.location.href) return;
    event.preventDefault();
    if (navigating) return;
    navigating = true;
    try {
      sessionStorage.setItem('metex-auth-entry',destination.pathname);
      await content.animate([{transform:'translateX(0)',opacity:1},{transform:'translateX(-80px)',opacity:0}],{duration:220,easing:'ease-in',fill:'forwards'}).finished;
    } catch (_) { /* Navigation must work even when animation/storage is unavailable. */ }
    window.location.assign(destination.href);
  });
})();
