/* edu4self calculator: a small panel in the answer form, shown only for tasks whose state.json entry
   says calculator: true. It reads expressions with its own tokenizer and recursive-descent parser
   (never eval or Function; the page's CSP forbids them anyway).
   EduCalc.evaluate(text) returns a number or throws an Error with a short plain message.
   EduCalc.format(number) returns { exact, short, text } for showing a result.
   EduCalc.mount(el, history) draws the panel into el; history is a list of {expr, result, value}
   that the panel appends to, newest last. */
(function () {
  "use strict";

  // byte units: KiB, MiB, GiB, TiB are powers of 1024; KB, MB, GB, TB powers of 1000
  var UNITS = { kib: Math.pow(1024, 1), mib: Math.pow(1024, 2), gib: Math.pow(1024, 3), tib: Math.pow(1024, 4),
    kb: 1e3, mb: 1e6, gb: 1e9, tb: 1e12 };
  var BIN = [["TiB", Math.pow(1024, 4)], ["GiB", Math.pow(1024, 3)], ["MiB", Math.pow(1024, 2)], ["KiB", 1024]];
  var MAX_LEN = 200;

  function fail(msg) { var e = new Error(msg); e.calc = true; throw e; }

  // ---------------------------------------------------------------- tokenizer
  function tokenize(src) {
    var out = [], i = 0, m;
    while (i < src.length) {
      var c = src[i], rest = src.slice(i);
      if (/\s/.test(c)) { i++; continue; }
      if ((m = /^(\d+\.?\d*|\.\d+)(e[+-]?\d+)?/i.exec(rest))) { out.push({ t: "num", v: parseFloat(m[0]), s: m[0] }); i += m[0].length; continue; }
      if ((m = /^[A-Za-z]+/.exec(rest))) {
        var u = UNITS[m[0].toLowerCase()];
        if (u === undefined) fail("Couldn't read that: \"" + m[0] + "\" isn't a number or a unit.");
        out.push({ t: "num", v: u, s: m[0] }); i += m[0].length; continue;
      }
      if (rest.slice(0, 2) === "**") { out.push({ t: "^" }); i += 2; continue; }
      if ("+-*/%^()".indexOf(c) >= 0) { out.push({ t: c }); i++; continue; }
      if (c === "×") { out.push({ t: "*" }); i++; continue; }   // × and ÷, pasted from a page
      if (c === "÷") { out.push({ t: "/" }); i++; continue; }
      if (c === "−") { out.push({ t: "-" }); i++; continue; }   // a typographic minus
      fail("Couldn't read that: \"" + c + "\" isn't something I can work with.");
    }
    return out;
  }

  // ---------------------------------------------------------------- parser
  // sum   := term (("+" | "-") term)*
  // term  := unary (("*" | "/" | "%") unary | atom-after-number)*   "4 KiB" multiplies
  // unary := ("-" | "+") unary | power
  // power := atom ("^" unary)?                                       right to left: 2^3^2 = 2^9
  // atom  := number | unit | "(" sum ")"
  function parse(tokens) {
    var pos = 0;
    function peek() { return tokens[pos] ? tokens[pos].t : null; }
    function missing() {
      return pos >= tokens.length ? "Couldn't read that: something is missing at the end."
        : peek() === ")" ? "Couldn't read that: check the brackets." : "Couldn't read that: two signs in a row?";
    }
    function sum() {
      var v = term();
      while (peek() === "+" || peek() === "-") { var op = tokens[pos++].t, r = term(); v = op === "+" ? v + r : v - r; }
      return v;
    }
    function term() {
      var v = unary();
      for (;;) {
        var op = peek();
        if (op === "*" || op === "/" || op === "%") {
          pos++;
          var r = unary();
          if (op !== "*" && r === 0) fail("Can't divide by zero.");
          v = op === "*" ? v * r : op === "/" ? v / r : v % r;
        } else if (op === "num" || op === "(") {
          if (op === "num" && /^\d|^\./.test(tokens[pos].s) && /^\d|^\./.test(tokens[pos - 1].s || "")) fail("Couldn't read that: two numbers in a row?");
          v = v * unary();                      // 4 KiB, 2(3+1)
        } else return v;
      }
    }
    function unary() {
      if (peek() === "-") { pos++; return -unary(); }
      if (peek() === "+") { pos++; return unary(); }
      return power();
    }
    function power() {
      var b = atom();
      if (peek() === "^") { pos++; return Math.pow(b, unary()); }
      return b;
    }
    function atom() {
      var k = peek();
      if (k === "num") return tokens[pos++].v;
      if (k === "(") {
        pos++;
        var v = sum();
        if (peek() !== ")") fail(pos >= tokens.length ? "Couldn't read that: check the brackets." : missing());
        pos++;
        return v;
      }
      fail(missing());
    }
    if (!tokens.length) fail("Type a sum first, for example 2*32*128.");
    var v = sum();
    if (pos < tokens.length) fail(peek() === ")" ? "Couldn't read that: check the brackets." : missing());
    return v;
  }

  function evaluate(text) {
    var src = String(text || "").trim();
    if (src.length > MAX_LEN) fail("That's too long for the calculator.");
    var v = parse(tokenize(src));
    if (isNaN(v)) fail("That has no answer as a number.");
    if (!isFinite(v)) fail("That number is too big.");
    return v === 0 ? 0 : v;                     // no -0
  }

  // ---------------------------------------------------------------- showing a result
  function group(intStr) { return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
  // the exact number, readable: thousands separators, at most 12 significant digits (so 0.1+0.2 = 0.3)
  function exact(v) {
    var a = Math.abs(v), sign = v < 0 ? "-" : "";
    if (a !== 0 && (a >= 1e21 || a < 1e-6)) return sign + a.toPrecision(12).replace(/\.?0+e/, "e").replace("e+", "e");
    var s = Number.isInteger(a) && a < 1e15 ? String(a) : String(parseFloat(a.toPrecision(12)));
    if (/e/.test(s)) return sign + s.replace("e+", "e");
    var parts = s.split(".");
    return sign + group(parts[0]) + (parts[1] ? "." + parts[1] : "");
  }
  function short(v) {
    var a = Math.abs(v), sign = v < 0 ? "-" : "";
    if (Number.isInteger(a) && a >= 1024 && a < 1e21) {
      for (var i = 0; i < BIN.length; i++) if (a % BIN[i][1] === 0) return sign + group(String(a / BIN[i][1])) + " " + BIN[i][0];
    }
    if (a >= 1e4 && a < 1e21) return "≈ " + sign + a.toExponential(2).replace(/\.?0+e/, "e").replace("e+", "e");
    return "";
  }
  function format(v) {
    var e = exact(v), s = short(v);
    return { exact: e, short: s, text: s ? e + " (" + s + ")" : e };
  }

  // ---------------------------------------------------------------- the panel
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  var MAX_HISTORY = 50;

  function mount(el, history) {
    el.innerHTML =
      '<div class="calc-head"><span class="field-label">Calculator</span>' +
      '<span class="calc-hint">KiB, MiB, GiB count in 1024s; KB, MB, GB in 1000s. ^ is a power, % a remainder.</span></div>' +
      '<ol class="calc-history" aria-label="Your sums, newest last"></ol>' +
      '<div class="calc-line"><input type="text" class="calc-input" autocomplete="off" spellcheck="false" ' +
        'aria-label="Calculator: type a sum and press Enter" placeholder="2*32*128*2, then Enter">' +
        '<button class="btn btn-ghost btn-sm calc-go" type="button">=</button></div>' +
      '<p class="calc-error" role="status" aria-live="polite" hidden></p>';
    var list = el.querySelector(".calc-history"), input = el.querySelector(".calc-input"), errEl = el.querySelector(".calc-error");

    function paint() {
      list.hidden = !history.length;
      list.innerHTML = history.map(function (h, i) {
        return '<li><button type="button" data-calc-use="' + i + '" title="Use this result"><span class="calc-expr">' + esc(h.expr) +
          '</span><span class="calc-eq">=</span><b class="calc-res">' + esc(h.result) + "</b></button></li>";
      }).join("");
      list.scrollTop = list.scrollHeight;
    }
    function showError(msg) { errEl.textContent = msg || ""; errEl.hidden = !msg; }
    function run() {
      var expr = input.value.trim();
      if (!expr) return;
      try {
        var v = evaluate(expr);
        history.push({ expr: expr, result: format(v).text, value: v });
        while (history.length > MAX_HISTORY) history.shift();
        showError("");
        input.value = "";
        paint();
      } catch (e) {
        if (!e.calc) throw e;
        showError(e.message);
      }
    }
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !input.value && errEl.hidden) return;   // nothing to clear: Escape closes the form as usual
      ev.stopPropagation();                     // the page's own shortcuts (the bar's 1 to 9) never see these keys
      if (ev.key === "Enter") { ev.preventDefault(); run(); }   // and the form isn't sent
      else if (ev.key === "Escape") { ev.preventDefault(); input.value = ""; showError(""); }
    });
    input.addEventListener("input", function () { if (!errEl.hidden) showError(""); });
    el.querySelector(".calc-go").addEventListener("click", function () { run(); input.focus(); });
    list.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-calc-use]");
      if (!b) return;
      var h = history[Number(b.dataset.calcUse)];
      if (!h) return;
      input.value = String(parseFloat(h.value.toPrecision(12)));
      input.focus();
    });
    paint();
    return { input: input };
  }

  window.EduCalc = { evaluate: evaluate, format: format, mount: mount, MAX_HISTORY: MAX_HISTORY };
})();
