// Groundtruth application logic.
(function () {
  if (!GT.isAuthed()) { location.href = 'login.html'; return; }

  const state = {
    config: null,
    me: null,
    template: 'invoice',
    templates: [],
    result: null,
    view: 'extract',
  };

  const $ = (id) => document.getElementById(id);
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // ---- boot ----
  async function boot() {
    try {
      state.config = await GT.config();
      state.me = await GT.me();
    } catch (e) {
      GT.clearToken();
      location.href = 'login.html';
      return;
    }
    state.templates = state.config.templates;
    renderTemplates();
    renderPlanPill();
    refreshUsage();
    setupApiView();
    wireEvents();
    handleCheckoutRedirect();
    if (!state.config.llm_enabled) {
      const b = $('modeBanner');
      b.classList.remove('hidden');
      b.innerHTML = '⚡ <strong>Demo mode:</strong> this server has no LLM key configured, so extraction uses the built-in heuristic engine. It still grounds every field to the source. Add a Gemini/OpenAI key to enable full AI extraction.';
    }
  }

  function renderPlanPill() {
    const pill = $('planPill');
    pill.textContent = state.me.plan;
  }

  async function refreshUsage() {
    try {
      const u = await GT.usage();
      $('usageText').textContent = u.used + ' / ' + u.quota;
      $('usageSub').textContent = 'pages used · ' + u.remaining + ' left';
      const pct = Math.min(100, u.percent_used);
      const fill = $('meterFill');
      fill.style.width = pct + '%';
      fill.classList.toggle('warn', pct >= 80 && pct < 100);
      fill.classList.toggle('full', pct >= 100);
    } catch (e) { /* ignore */ }
  }

  // ---- templates ----
  function renderTemplates() {
    const grid = $('templateGrid');
    grid.innerHTML = '';
    state.templates.forEach((t) => {
      const div = document.createElement('div');
      div.className = 'tpl' + (t.key === state.template ? ' active' : '');
      div.dataset.key = t.key;
      div.innerHTML = '<div class="ti">' + t.icon + '</div><div class="tn">' + esc(t.name) + '</div><div class="td">' + esc(t.description) + '</div>';
      div.addEventListener('click', () => selectTemplate(t.key));
      grid.appendChild(div);
    });
  }

  function selectTemplate(key) {
    state.template = key;
    document.querySelectorAll('.tpl').forEach((el) => el.classList.toggle('active', el.dataset.key === key));
    $('customFieldsWrap').classList.toggle('hidden', key !== 'custom');
  }

  // ---- extraction ----
  function currentCustomFields() {
    const raw = $('customFields').value.trim();
    if (!raw) return null;
    return raw.split(',').map((s) => s.trim()).filter(Boolean);
  }

  async function runExtraction() {
    const runBtn = $('runBtn');
    const status = $('runStatus');
    const file = $('fileInput').files[0];
    const text = $('pasteText').value.trim();

    if (!file && !text) { status.textContent = 'Add a file or paste some text first.'; return; }
    if (state.template === 'custom' && !currentCustomFields()) {
      status.textContent = 'Describe at least one field for custom extraction.';
      return;
    }

    runBtn.disabled = true;
    status.innerHTML = '<span class="spinner"></span> Extracting…';

    try {
      let result;
      if (file) {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('template', state.template);
        const cf = currentCustomFields();
        if (cf) fd.append('custom_fields', cf.join(','));
        result = await GT.extractFile(fd);
      } else {
        result = await GT.extract({ text, template: state.template, custom_fields: currentCustomFields() });
      }
      state.result = result;
      renderResult(result);
      status.textContent = '';
      refreshUsage();
    } catch (e) {
      if (e.status === 402) {
        status.innerHTML = '';
        showQuotaBlock(e.detail && e.detail.usage);
      } else {
        status.textContent = e.message || 'Extraction failed.';
      }
    } finally {
      runBtn.disabled = false;
    }
  }

  function showQuotaBlock(usage) {
    const b = $('modeBanner');
    b.className = 'notice err';
    b.classList.remove('hidden');
    b.innerHTML = '🚫 <strong>Monthly quota reached.</strong> You\'ve used all your pages for this cycle. <a href="pricing.html">Upgrade your plan</a> to keep extracting.';
    b.scrollIntoView({ behavior: 'smooth' });
  }

  // ---- render grounded result ----
  function buildHighlightedDoc(text, extractions) {
    // Sort by start; drop unlocated (-1) and overlapping spans.
    const spans = extractions
      .map((e, idx) => ({ ...e, idx }))
      .filter((e) => Number.isInteger(e.start) && Number.isInteger(e.end) && e.start >= 0 && e.end > e.start)
      .sort((a, b) => a.start - b.start);

    let html = '';
    let cursor = 0;
    let lastEnd = -1;
    for (const s of spans) {
      if (s.start < lastEnd) continue; // skip overlap
      if (s.start > cursor) html += esc(text.slice(cursor, s.start));
      html += '<mark data-idx="' + s.idx + '" title="' + esc(s.extraction_class) + '">' + esc(text.slice(s.start, s.end)) + '</mark>';
      cursor = s.end;
      lastEnd = s.end;
    }
    html += esc(text.slice(cursor));
    return html;
  }

  function renderResult(r) {
    $('results').classList.remove('hidden');
    const modeEl = $('resultMode');
    modeEl.textContent = r.mode === 'llm' ? 'AI · ' + (r.model || '') : 'Demo engine';
    modeEl.className = 'badge-mode ' + (r.mode === 'llm' ? 'llm' : 'demo');
    $('resultMeta').textContent = r.extractions.length + ' fields · ' + r.pages_charged + ' page(s) · ' + esc(r.source_name || '');

    const warn = $('resultWarning');
    if (r.warning) { warn.classList.remove('hidden'); warn.textContent = '⚠️ ' + r.warning; }
    else warn.classList.add('hidden');

    // Grounded doc
    $('docView').innerHTML = buildHighlightedDoc(r.text, r.extractions) || '<span class="muted">No text.</span>';

    // Fields list
    const fv = $('fieldsView');
    fv.innerHTML = '';
    if (r.extractions.length === 0) {
      fv.innerHTML = '<div style="padding:16px" class="muted">No fields found. Try a different template or describe custom fields.</div>';
    }
    r.extractions.forEach((e, idx) => {
      const row = document.createElement('div');
      row.className = 'field-row';
      row.dataset.idx = idx;
      const located = Number.isInteger(e.start) && e.start >= 0;
      const attrs = e.attributes && Object.keys(e.attributes).length
        ? '<div class="attrs">' + esc(Object.entries(e.attributes).map(([k, v]) => k + ': ' + v).join(' · ')) + '</div>' : '';
      row.innerHTML =
        '<div><div class="k">' + esc(e.extraction_class) + '</div><div class="v">' + esc(e.extraction_text) + '</div>' + attrs + '</div>' +
        '<div class="muted" style="font-size:.7rem">' + (located ? '🔗 source' : '—') + '</div>';
      row.addEventListener('click', () => focusField(idx));
      fv.appendChild(row);
    });

    // Table
    const tb = $('tableBody');
    tb.innerHTML = '';
    r.extractions.forEach((e) => {
      const tr = document.createElement('tr');
      const attrs = e.attributes && Object.keys(e.attributes).length ? esc(Object.entries(e.attributes).map(([k, v]) => k + ': ' + v).join(', ')) : '';
      tr.innerHTML = '<td><code>' + esc(e.extraction_class) + '</code></td><td>' + esc(e.extraction_text) + '</td><td class="muted">' + attrs + '</td>';
      tb.appendChild(tr);
    });

    // Cross-link marks -> fields
    $('docView').querySelectorAll('mark').forEach((m) => {
      m.addEventListener('click', () => focusField(parseInt(m.dataset.idx, 10)));
    });

    $('results').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function focusField(idx) {
    document.querySelectorAll('#fieldsView .field-row').forEach((el) => el.classList.toggle('active', el.dataset.idx == idx));
    document.querySelectorAll('#docView mark').forEach((el) => el.classList.remove('active'));
    const mark = document.querySelector('#docView mark[data-idx="' + idx + '"]');
    if (mark) { mark.classList.add('active'); mark.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
    const row = document.querySelector('#fieldsView .field-row[data-idx="' + idx + '"]');
    if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  // ---- authenticated download ----
  async function download(fmt) {
    if (!state.result) return;
    const res = await fetch(GT.exportUrl(state.result.job_id, fmt), {
      headers: { Authorization: 'Bearer ' + GT.token() },
    });
    if (!res.ok) { alert('Export failed.'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'groundtruth-' + state.result.job_id + '.' + fmt;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }

  // ---- history ----
  async function loadHistory() {
    const list = $('historyList');
    list.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const { jobs } = await GT.jobs();
      if (!jobs.length) { list.innerHTML = '<p class="muted">No extractions yet.</p>'; return; }
      list.innerHTML = '';
      jobs.forEach((j) => {
        const card = document.createElement('div');
        card.className = 'card';
        card.style.cssText = 'margin-bottom:10px;padding:14px 18px;display:flex;justify-content:space-between;align-items:center;cursor:pointer';
        const date = j.created_at ? new Date(j.created_at).toLocaleString() : '';
        card.innerHTML = '<div><strong>' + esc(j.source_name) + '</strong><div class="muted" style="font-size:.82rem">' +
          esc(j.template) + ' · ' + j.count + ' fields · ' + j.pages_charged + ' page(s) · ' + esc(date) + '</div></div>' +
          '<span class="badge-mode ' + (j.mode === 'llm' ? 'llm' : 'demo') + '">' + (j.mode === 'llm' ? 'AI' : 'Demo') + '</span>';
        card.addEventListener('click', () => openJob(j.id));
        list.appendChild(card);
      });
    } catch (e) { list.innerHTML = '<p class="muted">Could not load history.</p>'; }
  }

  async function openJob(id) {
    try {
      const job = await GT.job(id);
      switchView('extract');
      state.result = { ...job, pages_charged: '—', model: null, warning: null };
      renderResult(state.result);
    } catch (e) { alert('Could not open job.'); }
  }

  // ---- api view ----
  function setupApiView() {
    $('apiKeyField').value = state.me.api_key;
    updateCurl();
  }
  function updateCurl() {
    const base = location.origin;
    $('curlExample').textContent =
      'curl -X POST ' + base + '/api/extract \\\n' +
      '  -H "X-API-Key: ' + state.me.api_key + '" \\\n' +
      '  -H "Content-Type: application/json" \\\n' +
      "  -d '{\"template\":\"invoice\",\"text\":\"Invoice #INV-2045 ... Total Due: $1,320.00\"}'";
  }

  // ---- views ----
  function switchView(view) {
    state.view = view;
    ['extract', 'history', 'api'].forEach((v) => $('view-' + v).classList.toggle('hidden', v !== view));
    document.querySelectorAll('.side-link[data-view]').forEach((el) => el.classList.toggle('active', el.dataset.view === view));
    if (view === 'history') loadHistory();
  }

  function handleCheckoutRedirect() {
    const p = new URLSearchParams(location.search);
    if (p.get('checkout') === 'success') {
      const b = $('modeBanner');
      b.className = 'notice info';
      b.classList.remove('hidden');
      b.innerHTML = '🎉 <strong>Payment received.</strong> Your plan is being activated — usage limits update within a few seconds.';
      setTimeout(async () => { state.me = await GT.me(); renderPlanPill(); refreshUsage(); }, 3000);
      history.replaceState({}, '', 'app.html');
    }
  }

  // ---- events ----
  function wireEvents() {
    $('runBtn').addEventListener('click', runExtraction);
    $('exportJson').addEventListener('click', () => download('json'));
    $('exportCsv').addEventListener('click', () => download('csv'));

    $('viewToggle').addEventListener('click', () => {
      const grounded = $('groundedView'), table = $('tableView'), btn = $('viewToggle');
      const showTable = table.classList.contains('hidden');
      table.classList.toggle('hidden', !showTable);
      grounded.classList.toggle('hidden', showTable);
      btn.textContent = showTable ? 'Grounded view' : 'Table view';
    });

    document.querySelectorAll('.side-link[data-view]').forEach((el) =>
      el.addEventListener('click', () => switchView(el.dataset.view)));

    $('logoutBtn').addEventListener('click', (e) => { e.preventDefault(); GT.clearToken(); location.href = '/'; });

    // dropzone
    const dz = $('dropzone'), fi = $('fileInput');
    dz.addEventListener('click', () => fi.click());
    fi.addEventListener('change', () => { if (fi.files[0]) { dz.querySelector('div:nth-child(3)').textContent = fi.files[0].name; $('pasteText').value = ''; } });
    ['dragover', 'dragenter'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
    dz.addEventListener('drop', (e) => { if (e.dataTransfer.files[0]) { fi.files = e.dataTransfer.files; dz.querySelector('div:nth-child(3)').textContent = fi.files[0].name; } });
    $('pasteText').addEventListener('input', () => { if ($('pasteText').value) { fi.value = ''; dz.querySelector('div:nth-child(3)').textContent = 'Drop a PDF or text file, or click to browse'; } });

    // api key
    $('copyKey').addEventListener('click', () => { navigator.clipboard.writeText(state.me.api_key); $('copyKey').textContent = 'Copied!'; setTimeout(() => $('copyKey').textContent = 'Copy', 1500); });
    $('rotateKey').addEventListener('click', async () => {
      if (!confirm('Rotate your API key? The current key stops working immediately.')) return;
      const { api_key } = await GT.rotateKey();
      state.me.api_key = api_key;
      $('apiKeyField').value = api_key;
      updateCurl();
    });
  }

  boot();
})();
