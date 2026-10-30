/* reusable quiz widget. three flavours, all driven by data attributes.
   numeric:  <div class="quiz" data-answer="117440512" data-tol="0.01"> ... <input> ...
   text:     <div class="quiz" data-text="[1, 2, 3]||[1,2,3]"> ... <textarea> or <input> ...
             compared ignoring whitespace and treating ' and " alike; || separates accepted answers
   choice:   <div class="quiz"> ... <button class="opt" data-correct="1">
   every .quiz needs a .verdict div and (optionally) an .explain div. */
(function () {
  function reveal(q, ok, msg) {
    var v = q.querySelector('.verdict');
    v.className = 'verdict ' + (ok ? 'ok' : 'no');
    v.textContent = msg;
    var e = q.querySelector('.explain');
    if (e) e.classList.add('show');
  }
  function parseNum(s) {
    s = String(s).trim().toLowerCase().replace(/[_,\s]/g, '');
    var m = s.match(/^(-?[\d.]+(?:e-?\d+)?)(kib|mib|gib|tib|kb|mb|gb|tb|k|m|g|t|b)?$/);
    if (!m) return NaN;
    var x = parseFloat(m[1]);
    var u = { b: 1, k: 1e3, kb: 1e3, m: 1e6, mb: 1e6, g: 1e9, gb: 1e9, t: 1e12, tb: 1e12,
              kib: 1024, mib: 1048576, gib: 1073741824, tib: 1099511627776 }[m[2] || 'b'];
    return x * u;
  }
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('button');
    if (!btn) return;
    var q = btn.closest('.quiz');
    if (!q) return;

    if (btn.classList.contains('opt')) {
      var ok = btn.dataset.correct === '1';
      q.querySelectorAll('button.opt').forEach(function (b) { b.disabled = true; });
      reveal(q, ok, ok ? 'correct.' : 'no.');
      return;
    }
    if (btn.classList.contains('check') && q.dataset.text !== undefined) {
      var norm = function (x) { return String(x).replace(/\s+/g, '').replace(/"/g, "'"); };
      var field = q.querySelector('textarea, input[type=text]');
      var accepted = q.dataset.text.split('||').map(norm);
      var okText = accepted.indexOf(norm(field.value)) !== -1;
      reveal(q, okText, okText ? 'correct.' : (field.value.trim() ? 'no.' : 'type what it prints first.'));
      return;
    }
    if (btn.classList.contains('check')) {
      var input = q.querySelector('input[type=text]');
      var got = parseNum(input.value);
      var want = parseFloat(q.dataset.answer);
      var tol = parseFloat(q.dataset.tol || '0.01');
      var ok2 = isFinite(got) && Math.abs(got - want) <= Math.abs(want) * tol;
      reveal(q, ok2, ok2 ? 'correct.' : (isFinite(got) ? 'no. you said ' + got.toExponential(3) : "couldn't parse that."));
      return;
    }
    if (btn.classList.contains('show')) { reveal(q, false, 'answer shown, no credit.'); }
  });
})();
