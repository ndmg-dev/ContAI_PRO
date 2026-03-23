// Global frontend helpers (no framework).
(() => {
  const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  window.CSRF_TOKEN = token;

  window.csrfFetch = function csrfFetch(url, options = {}) {
    const opts = options || {};
    opts.headers = Object.assign({}, opts.headers || {});
    const method = (opts.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && window.CSRF_TOKEN) {
      opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
    }
    return fetch(url, opts);
  };

  document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide?.createIcons) window.lucide.createIcons();
    if (window.feather?.replace) window.feather.replace();
  });
})();

