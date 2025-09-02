// namespaced ratings_tab.js
function fadeInAverageRating() {
  const el = document.querySelector('.ratings-tab #average-rating-text');
  if (!el) return;
  el.classList.remove('show');
  void el.offsetWidth;  // reflow
  setTimeout(() => el.classList.add('show'), 100);
}

document.addEventListener('DOMContentLoaded', () => {
  fadeInAverageRating();
});

// expose if needed elsewhere
window.fadeInAverageRating = fadeInAverageRating;
