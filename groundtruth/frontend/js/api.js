// Shared API client + auth helpers for the Groundtruth frontend.
window.GT = (function () {
  const TOKEN_KEY = 'gt_token';

  function token() { return localStorage.getItem(TOKEN_KEY); }
  function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
  function clearToken() { localStorage.removeItem(TOKEN_KEY); }
  function isAuthed() { return !!token(); }

  async function req(path, opts = {}) {
    const headers = opts.headers || {};
    if (!(opts.body instanceof FormData) && opts.body) headers['Content-Type'] = 'application/json';
    if (token()) headers['Authorization'] = 'Bearer ' + token();
    const res = await fetch('/api' + path, { ...opts, headers });
    let data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) {
      const detail = data && data.detail ? data.detail : ('Request failed (' + res.status + ')');
      const err = new Error(typeof detail === 'string' ? detail : (detail.message || 'Error'));
      err.status = res.status;
      err.detail = detail;
      throw err;
    }
    return data;
  }

  return {
    token, setToken, clearToken, isAuthed,
    config: () => req('/config'),
    signup: (body) => req('/auth/signup', { method: 'POST', body: JSON.stringify(body) }),
    login: (body) => req('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
    me: () => req('/me'),
    usage: () => req('/usage'),
    extract: (body) => req('/extract', { method: 'POST', body: JSON.stringify(body) }),
    extractFile: (formData) => req('/extract/file', { method: 'POST', body: formData }),
    jobs: () => req('/jobs'),
    job: (id) => req('/jobs/' + id),
    rotateKey: () => req('/api-key/rotate', { method: 'POST' }),
    checkout: (plan) => req('/billing/checkout', { method: 'POST', body: JSON.stringify({ plan }) }),
    portal: () => req('/billing/portal', { method: 'POST' }),
    exportUrl: (id, fmt) => '/api/jobs/' + id + '/export.' + fmt,
  };
})();
