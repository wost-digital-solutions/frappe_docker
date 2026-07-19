// Login / signup page logic.
(function () {
  const params = new URLSearchParams(location.search);
  let mode = params.get('mode') === 'signup' ? 'signup' : 'login';

  const els = {
    title: document.getElementById('authTitle'),
    sub: document.getElementById('authSub'),
    tabLogin: document.getElementById('tabLogin'),
    tabSignup: document.getElementById('tabSignup'),
    nameField: document.getElementById('nameField'),
    pwHint: document.getElementById('pwHint'),
    submit: document.getElementById('submitBtn'),
    form: document.getElementById('authForm'),
    email: document.getElementById('email'),
    password: document.getElementById('password'),
    fullName: document.getElementById('fullName'),
    error: document.getElementById('formError'),
  };

  // If already logged in, go straight to the app.
  if (GT.isAuthed()) { location.href = 'app.html'; return; }

  function render() {
    const signup = mode === 'signup';
    els.title.textContent = signup ? 'Create your account' : 'Welcome back';
    els.sub.textContent = signup ? 'Start extracting free — 25 pages a month, no card.' : 'Log in to your Groundtruth account';
    els.tabLogin.classList.toggle('active', !signup);
    els.tabSignup.classList.toggle('active', signup);
    els.nameField.style.display = signup ? 'block' : 'none';
    els.pwHint.style.display = signup ? 'block' : 'none';
    els.password.setAttribute('autocomplete', signup ? 'new-password' : 'current-password');
    els.submit.textContent = signup ? 'Create account' : 'Log in';
    els.error.textContent = '';
  }

  els.tabLogin.addEventListener('click', () => { mode = 'login'; render(); });
  els.tabSignup.addEventListener('click', () => { mode = 'signup'; render(); });
  render();

  function nextDestination() {
    // After auth: if they came from pricing to buy a plan, kick off checkout.
    if (params.get('next') === 'pricing' && params.get('plan')) {
      return { checkout: params.get('plan') };
    }
    return { app: true };
  }

  els.form.addEventListener('submit', async (e) => {
    e.preventDefault();
    els.error.textContent = '';
    els.submit.disabled = true;
    const original = els.submit.textContent;
    els.submit.textContent = 'Please wait…';
    try {
      const body = { email: els.email.value.trim(), password: els.password.value };
      let res;
      if (mode === 'signup') {
        body.full_name = els.fullName.value.trim();
        if (window.GTA) body.anon_id = GTA.anonId();
        res = await GT.signup(body);
      } else {
        res = await GT.login(body);
      }
      GT.setToken(res.access_token);

      const dest = nextDestination();
      if (dest.checkout) {
        try {
          const { url } = await GT.checkout(dest.checkout);
          location.href = url;
          return;
        } catch (err) {
          // Billing may be disabled; just land in the app.
          location.href = 'app.html';
          return;
        }
      }
      location.href = 'app.html';
    } catch (err) {
      els.error.textContent = err.message || 'Something went wrong.';
      els.submit.disabled = false;
      els.submit.textContent = original;
    }
  });
})();
