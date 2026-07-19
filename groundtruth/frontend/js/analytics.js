// Lightweight first-party funnel tracking. No third parties, no cookies banner.
window.GTA = (function () {
  const KEY = 'gt_anon';
  function anonId() {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = 'a_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(KEY, id);
    }
    return id;
  }
  function track(name, meta) {
    try {
      fetch('/api/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, anon_id: anonId(), meta: meta || {} }),
        keepalive: true,
      }).catch(function () {});
    } catch (e) {}
  }
  return { anonId: anonId, track: track };
})();

// Auto-fire a page visit on load.
document.addEventListener('DOMContentLoaded', function () {
  GTA.track('visit', { path: location.pathname });
});
