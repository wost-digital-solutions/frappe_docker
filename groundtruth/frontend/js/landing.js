// Interactive source-grounding demo on the landing page.
(function () {
  const fields = document.querySelectorAll('#demoFields .field-chip');
  const marks = document.querySelectorAll('#demoDoc .mark');

  function activate(f) {
    fields.forEach((c) => c.classList.toggle('active', c.dataset.f === f));
    marks.forEach((m) => m.classList.toggle('active', m.dataset.src === f));
    const mark = document.querySelector('#demoDoc .mark[data-src="' + f + '"]');
    if (mark) mark.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  fields.forEach((c) => c.addEventListener('click', () => activate(c.dataset.f)));
  marks.forEach((m) => m.addEventListener('click', () => activate(m.dataset.src)));

  // Auto-cycle to hint the interaction, stop once the user interacts.
  const order = ['f1', 'f2', 'f3', 'f4', 'f5'];
  let i = 0, auto = true;
  document.getElementById('demo').addEventListener('click', () => { auto = false; });
  activate('f1');
  setInterval(() => { if (auto) { i = (i + 1) % order.length; activate(order[i]); } }, 1800);
})();
