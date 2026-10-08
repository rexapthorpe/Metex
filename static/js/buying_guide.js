/* Keep the native disclosure accessible while easing its opening height. */
(() => {
  const guide = document.querySelector('.lp-how-it-works details');
  if (!guide) return;
  let opening;
  guide.addEventListener('toggle', () => {
    if (opening) opening.cancel();
    if (!guide.open || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const summaryHeight = guide.querySelector('summary').getBoundingClientRect().height;
    const fullHeight = guide.getBoundingClientRect().height;
    opening = guide.animate([
      { height: `${summaryHeight}px`, overflow: 'hidden' },
      { height: `${fullHeight}px`, overflow: 'hidden' }
    ], { duration: 280, easing: 'cubic-bezier(0.2, 0, 0, 1)' });
  });
})();
