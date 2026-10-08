/* Animate both directions while retaining native summary keyboard behavior. */
(() => {
  const guide = document.querySelector('.lp-how-it-works details');
  if (!guide) return;
  const summary = guide.querySelector('summary');
  let animation;
  let expanded = guide.open;
  summary.addEventListener('click', (event) => {
    event.preventDefault();
    expanded = !expanded;
    const from = guide.getBoundingClientRect().height;
    if (animation) animation.cancel();
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      guide.open = expanded;
      return;
    }
    guide.open = true;
    const to = expanded ? guide.getBoundingClientRect().height : summary.getBoundingClientRect().height;
    animation = guide.animate([
      { height: `${from}px`, overflow: 'hidden' },
      { height: `${to}px`, overflow: 'hidden' }
    ], { duration: 280, easing: 'cubic-bezier(0.2, 0, 0, 1)' });
    const current = animation;
    current.onfinish = () => {
      if (animation !== current) return;
      guide.open = expanded;
      animation = null;
    };
  });
})();
