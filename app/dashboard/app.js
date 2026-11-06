/* edu4self dashboard client. Vanilla JS, no dependencies, no build step.
   Reads /api/state, renders it, posts submissions to /api/inbox and settings to /api/config. */
(function () {
  "use strict";

  var POLL_MS = 15000;
  var ONBOARD_KEY = "edu.onboarded.v1";
  var DATA = null;
  var lastStamp = null;
  var submitCtx = null;

  var KIND = {
    lesson:     { label: "Lesson",     open: "Open lesson",     submit: "Submit answers" },
    probe:      { label: "Probe",      open: "Open probe",      submit: "Submit answers" },
    checkpoint: { label: "Checkpoint", open: "Open checkpoint", submit: "Submit answers" },
    reading:    { label: "Reading",    open: "Open reading",    submit: "Mark as done" },
    project:    { label: "Project",    open: "Open project",    submit: "Submit work" },
    mock:       { label: "Mock interview", open: "Start mock",  submit: "Submit notes" }
  };
  var LADDER = ["Not yet", "Heard of it", "Understand it", "Use it on my own", "Public proof"];
  var DAY_GOAL_MIN = 120;    // focused minutes a day, any block type; Settings → Goals
  var WEEK_GOAL_DAYS = 4;    // days with at least one block, Monday to Sunday; Settings → Goals
  var HOURS_PER_STEP = 8;    // rough focused hours per milestone step, for the finish-line date
  var IDLE_DAYS = 3;         // this long without a block and the greeting goes gentle
  var PROOF_KEY = "edu.proofs.seen.v1";

  // ---------------------------------------------------------------- helpers
  function $(sel, el) { return (el || document).querySelector(sel); }
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; }
  }
  function ago(iso) {
    if (!iso) return "never";
    var s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 45) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    var d = Math.round(s / 86400);
    return d === 1 ? "yesterday" : d + " days ago";
  }
  function dayKey(d) {
    var z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
    return z.toISOString().slice(0, 10);
  }
  function greetingWord() {
    var h = new Date().getHours();
    return h < 5 ? "Late night" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  }
  function toast(html, ms) {
    var t = $("#toast");
    t.innerHTML = html;
    t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.hidden = true; }, ms || 5200);
  }
  // The learner's settings (_system/config.json, edited in Settings). The server fills in defaults.
  function cfg() { return (DATA && DATA.config) || {}; }
  function learnerName() { return cfg().name || (DATA && DATA.state && DATA.state.learner) || "there"; }
  function notesInObsidian() { return !!(cfg().obsidian && cfg().obsidian.enabled); }
  function obsidianVault() { return (cfg().obsidian && cfg().obsidian.vault) || (DATA && DATA.server && DATA.server.vault) || ""; }
  function noteHref(path) {
    return notesInObsidian() ? "obsidian://open?vault=" + encodeURIComponent(obsidianVault()) + "&file=" + encodeURIComponent(path)
      : "/vault/" + path.split("/").map(encodeURIComponent).join("/") + ".md";
  }

  // Apply settings that the rest of the code reads as plain variables
  function applyConfig() {
    var c = cfg(), g = c.goals || {}, b = c.blocks || {};
    DAY_GOAL_MIN = g.day_minutes || 120;
    WEEK_GOAL_DAYS = g.week_days || 4;
    if (b.presets && b.presets.length) PRESETS = b.presets.slice();
    if (b.kinds && b.kinds.length) {
      BLOCKS = {};
      b.kinds.forEach(function (k) { BLOCKS[k.id] = { label: k.label, color: k.color, minutes: k.minutes }; });
      if (!BLOCKS[pick.block]) pick.block = b.kinds[0].id;
    }
    if (!pick.touched && PRESETS.indexOf(pick.minutes) < 0) pick.minutes = PRESETS[Math.min(1, PRESETS.length - 1)];
    var tm = THEME ? THEME.meta : null;
    // the bar's names are the learner's (Settings → The bar); other rooms bring their own
    BAR_NAMES = (!tm || tm.id === "bar") && c.bar && c.bar.names && c.bar.names.length ? c.bar.names
      : tm && tm.names && tm.names.length ? tm.names : [[tm ? tm.name : "The bar", ""]];
    Object.keys(VOICES).forEach(function (id) {
      var o = (c.bar && c.bar.voices && c.bar.voices[id]) || {}, t = (tm && tm.voices && tm.voices[id]) || {};
      VOICES[id].name = o.name || t.name || VOICE_DEFAULTS[id].name;
      VOICES[id].c = o.color || t.color || VOICE_DEFAULTS[id].c;
    });
    var port = DATA && DATA.server && DATA.server.port;
    if (port) { var fp = $("#footer-port"); if (fp) fp.textContent = "127.0.0.1:" + port; }
  }

  function kindMeta(k) { return KIND[k] || { label: k, open: "Open", submit: "Submit" }; }
  function openTarget(href) { return /\.(html|md)($|[?#])/.test(href || "") || /^https?:/.test(href || "") ? ' target="_blank" rel="noopener"' : ""; }

  // ---------------------------------------------------------------- data shaping
  function pendingFor(taskId) {
    if (!DATA || !DATA.inbox) return null;
    var list = DATA.inbox.pending.filter(function (e) { return e.task === taskId; });
    return list.length ? list[list.length - 1] : null;
  }

  function actionableTasks() {
    var out = [];
    (DATA.state.topics || []).forEach(function (topic) {
      (topic.queue || []).forEach(function (task, i) {
        out.push({ topic: topic, task: task, index: i });
      });
    });
    return out;
  }

  function heroTask(all) {
    // first task that still needs the learner: todo and not yet submitted
    for (var i = 0; i < all.length; i++) {
      var t = all[i].task;
      if (t.status === "todo" && !pendingFor(t.id)) return all[i];
    }
    // otherwise the first one waiting for grading
    for (var j = 0; j < all.length; j++) {
      if (all[j].task.status === "todo") return all[j];
    }
    return null;
  }


  // ---------------------------------------------------------------- render: shell
  function render() {
    var app = $("#app");
    applyConfig();
    document.body.classList.toggle("v-bar", isBar());
    paintViewButton();
    if (DATA.error) {
      app.innerHTML = '<div class="card error-card"><h2>The dashboard can\'t read its state file</h2>' +
        '<p>' + esc(DATA.error) + '</p><p class="muted">Ask Claude to fix <code>_system/state.json</code> in your vault. Your submissions are safe; they\'re stored separately.</p></div>';
      renderStatus();
      return;
    }
    var st = DATA.state;
    var all = actionableTasks();
    var hero = heroTask(all);
    var topics = st.topics || [];
    var live = topics.filter(function (t) { return !isDormant(t); });
    var away = idleDays();

    if (isBar()) {
      if (!THEME || THEME.meta.id !== wantTheme()) { ensureTheme(); if (!THEME) return; }
      app.innerHTML = renderBar(hero, topics, live);
      markFolds();
      if (topics[0]) document.documentElement.style.setProperty("--topic", topics[0].color);
      mountBlockCard();
      if (away >= IDLE_DAYS && !pick.touched && !active && pick.minutes !== 25) { pick.minutes = 25; paintControls(); }
      paintWater();
      renderStatus();
      musicSync();
      shelfNews();
      return;
    }
    app.innerHTML =
      '<section class="greeting">' +
        '<div>' + (away >= IDLE_DAYS
          ? '<h1>Welcome back, ' + esc(learnerName()) + '. <em>Just 25 minutes today.</em></h1>' +
            '<p>No catching up. One short block, then see how it feels.</p>'
          : '<h1>' + esc(greetingWord()) + ', ' + esc(learnerName()) + '. <em>' + (hero ? "Here's your next move." : "You're all caught up.") + '</em></h1>' +
            '<p>One thing at a time. Do it, submit it, then tell Claude to check your inbox.</p>') + '</div>' +
        renderToday() +
      '</section>' +
      renderFinishLine(topics[0]) +
      '<div class="grid">' +
        '<div class="col">' +
          renderCoach(st.coach) +
          recallCard(false) +
          renderHero(hero) +
          renderQueue(all, hero) +
          shelfCard("Your shelf") +
          topics.map(renderTopic).join("") +
          renderLinked() +
        '</div>' +
        '<div class="col">' +
          '<div id="blk-slot"></div>' +
          live.map(renderMilestones).join("") +
          renderGates(live) +
          live.map(renderEvidence).join("") +
          renderCalibration() +
          live.map(renderSkills).join("") +
        '</div>' +
      '</div>';
    markFolds();
    if (topics[0]) document.documentElement.style.setProperty("--topic", topics[0].color);
    mountBlockCard();
    // coming back after a break: the smallest block is already picked, unless you chose one yourself
    if (away >= IDLE_DAYS && !pick.touched && !active && pick.minutes !== 25) { pick.minutes = 25; paintControls(); }
    renderStatus();
    musicSync();
    shelfNews();
  }

  function renderStatus() {
    var el = $("#status");
    if (!DATA) { el.innerHTML = ""; return; }
    if (DATA.__offline) {
      el.innerHTML = '<span class="pill is-offline"><span class="led"></span>Can\'t reach the dashboard server. Retrying…</span>';
      return;
    }
    var pending = DATA.inbox ? DATA.inbox.pending.length : 0;
    var html = '<span class="pill" title="When Claude last updated your progress"><span class="led"></span>Updated by Claude ' + esc(ago(DATA.state && DATA.state.updated)) + '</span>';
    if (pending) {
      html += '<span class="pill is-wait" title="Submissions Claude hasn\'t graded yet">⏳ ' + pending + ' waiting for Claude</span>';
    }
    el.innerHTML = html;
  }

  // A topic with no proof yet and every skill at zero: show it as one quiet line, not four empty cards
  function isDormant(topic) {
    return !(topic.history || []).some(function (h) { return h.evidence; }) &&
      (topic.regions || []).every(function (r) { return !r.level; });
  }

  function idleDays() {
    var list = allBlocks();
    if (!list.length) return 0;
    var last = Math.max.apply(null, list.map(function (b) { return new Date(b.ts || b.started).getTime(); }));
    return Math.floor((Date.now() - last) / 864e5);
  }

  function weekStart() {
    var d = new Date(); d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - (d.getDay() + 6) % 7);   // Monday
    return d;
  }

  // Effort, not submissions: focused minutes today (any block) and which days this week had a block
  function renderToday() {
    var today = dayKey(new Date()), monday = weekStart(), mins = 0, days = {};
    allBlocks().forEach(function (b) {
      var d = new Date(b.ts || b.started), k = dayKey(d);
      if (k === today) mins += b.minutes;
      if (d >= monday) days[k] = true;
    });
    var pct = Math.min(1, mins / DAY_GOAL_MIN), r = 17, c = 2 * Math.PI * r, dots = "", hit = 0, now = new Date();
    for (var i = 0; i < 7; i++) {
      var d = new Date(monday); d.setDate(monday.getDate() + i);
      var k = dayKey(d);
      if (days[k]) hit++;
      dots += '<i class="' + (days[k] ? "on" : "") + (k === today ? " is-today" : "") + (d > now && k !== today ? " is-future" : "") + '" title="' + k + (days[k] ? ": focused" : "") + '">' + "MTWTFSS"[i] + "</i>";
    }
    var msg = mins >= DAY_GOAL_MIN ? "Goal met · " + hm(mins) : hm(mins) + " of " + DAY_GOAL_MIN + " min";
    var week = hit >= WEEK_GOAL_DAYS ? "Week won · " + hit + " days" : hit + " of " + WEEK_GOAL_DAYS + " days this week";
    return '<div class="today' + (mins >= DAY_GOAL_MIN ? " is-met" : "") + '" id="today" title="Focused minutes today from any block, and the days this week with at least one block">' +
      '<svg width="44" height="44" viewBox="0 0 44 44" aria-hidden="true">' +
        '<circle cx="22" cy="22" r="' + r + '" fill="none" stroke="var(--bg-2)" stroke-width="5"/>' +
        '<circle cx="22" cy="22" r="' + r + '" fill="none" stroke="' + (mins >= DAY_GOAL_MIN ? "var(--green)" : "var(--topic)") + '" stroke-width="5" stroke-linecap="round"' +
        ' stroke-dasharray="' + c + '" stroke-dashoffset="' + (c * (1 - pct)) + '" transform="rotate(-90 22 22)"/>' +
        '<text x="22" y="26" text-anchor="middle" font-size="11" font-weight="700" fill="currentColor">' + mins + "m</text>" +
      '</svg><div><strong>Today</strong><span>' + esc(msg) + '</span>' +
      '<div class="week" aria-label="' + esc(week) + '">' + dots + '</div><span>' + esc(week) + '</span></div></div>';
  }

  function paintToday() {
    var el = $("#today");
    if (el && DATA && !DATA.error) el.outerHTML = renderToday();
    if (DATA && !DATA.error) paintBarBits();
  }

  // Focused hours a week, averaged over the last 4 weeks of blocks
  function paceHoursPerWeek() {
    var cut = Date.now() - 28 * 864e5, mins = 0;
    allBlocks().forEach(function (b) { if (new Date(b.ts || b.started).getTime() >= cut) mins += b.minutes; });
    return mins / 60 / 4;
  }

  function shortDate(d) {
    var o = { month: "short", day: "numeric" };
    if (d.getFullYear() !== new Date().getFullYear()) o.year = "numeric";
    return d.toLocaleDateString([], o);
  }

  // The active milestone as a track, and a date that moves with how much you actually work
  function renderFinishLine(topic) {
    if (!topic) return "";
    var ms = (topic.milestones || []).filter(function (m) { return m.status === "active"; })[0];
    if (!ms || !(ms.steps || []).length) return "";
    var steps = ms.steps, left = steps.filter(function (x) { return !x.done; }).length;
    var perStep = (DATA.state.pace && DATA.state.pace.hours_per_step) || HOURS_PER_STEP;
    var pace = paceHoursPerWeek(), hours = left * perStep;
    var pips = steps.map(function (x, i) {
      var cls = x.done ? "done" : x.current ? "current" : "";
      return '<li class="' + cls + (i === steps.length - 1 ? " is-goal" : "") + '" title="' + esc(x.title) + '"><span></span>' +
        (x.current ? '<em>you are here</em>' : "") + "</li>";
    }).join("");
    var eta;
    if (!left) eta = "<b>" + esc(ms.id) + " done.</b> On to the next one.";
    else if (pace < 0.25) eta = "No focus blocks in the last 4 weeks, so no date yet. One block gives you one.";
    else {
      var at = function (h) { return shortDate(new Date(Date.now() + hours / h * 7 * 864e5)); };
      eta = "At your pace (" + pace.toFixed(1) + " h/week) you get there around <b>" + at(pace) + "</b>. " +
        "Two more hours a week: <b>" + at(pace + 2) + "</b>.";
    }
    return '<section class="finish" style="--topic:' + esc(topic.color) + '">' +
      '<div class="finish-head"><span class="card-title">Finish line · ' + esc(ms.id) + " " + esc(ms.title) + '</span>' +
      '<span class="card-sub">' + (steps.length - left) + " of " + steps.length + " steps · goal: " + esc(ms.goal || "") + '</span></div>' +
      '<ol class="finish-track">' + pips + '</ol>' +
      '<p class="finish-eta">' + eta + ' <small>(about ' + perStep + ' focused hours a step, recalibrated as steps finish)</small></p></section>';
  }

  // One card for every live topic's interview gate, instead of a card each
  function renderGates(topics) {
    topics = topics.filter(function (t) { return t.gate && t.gate.level; });
    if (!topics.length) return "";
    var rows = topics.map(function (t) {
      var g = t.gate || {};
      return '<div class="gate-row"><span class="gate gate-' + esc(g.level) + '">' + esc(g.level || "") + '</span>' +
        '<div><b>' + esc(t.title) + ' · ' + esc(g.label || "") + '</b><p>' + esc(g.why || "") + '</p></div></div>';
    }).join("");
    return '<section class="card"><div class="card-head"><span class="card-title">Readiness</span><button class="info" data-help="gate" aria-label="What is the readiness gate?">?</button></div>' +
      '<div class="gate-rows">' + rows + '</div></section>';
  }

  function renderCoach(coach) {
    if (!coach) return "";
    return '<div class="coach' + (foldOpen.coach ? " is-open" : "") + '" data-fold="coach"><div class="coach-avatar" aria-hidden="true">C</div><div>' +
      '<strong>' + esc(coach.headline) + '</strong><p class="fold fold-2">' + esc(coach.body) + '</p>' +
      '<button class="fold-more" type="button" aria-expanded="false" hidden>more</button>' +
      '<small>Note from Claude · ' + esc(coach.date || "") + '</small></div></div>';
  }

  // ---------------------------------------------------------------- render: hero + queue
  function renderHero(entry) {
    if (!entry) {
      return '<section class="hero hero-empty"><h2>Nothing waiting on you.</h2>' +
        '<p class="hero-why">' + (claudeOK() && pendingCount() ? gradeButton() + " Claude grades what's in your inbox and lines up your next step."
          : 'Tell Claude <strong>"check my inbox"</strong> to get your work graded and your next step lined up.') + "</p></section>";
    }
    var t = entry.task, topic = entry.topic, meta = kindMeta(t.kind);
    var pend = pendingFor(t.id);
    var color = "var(--" + (KIND[t.kind] ? t.kind : "lesson") + ")";
    var html = '<section class="hero" style="--c:' + color + '" aria-labelledby="hero-title">' +
      '<div class="hero-eyebrow"><span class="kicker">Up next</span><span class="dot-sep"></span>' +
        '<span class="chip chip-' + esc(t.kind) + '">' + esc(meta.label) + '</span>' +
        '<span class="topic-name">' + esc(topic.title) + '</span></div>' +
      '<span class="label">' + esc(t.label || "") + '</span>' +
      '<h2 id="hero-title">' + esc(t.title) + '</h2>' +
      '<p class="hero-why">' + esc(t.why || "") + '</p>' +
      '<div class="hero-meta">' + (t.effort ? '<span>◷ ' + esc(t.effort) + '</span>' : "") +
        (t.kind === "probe" ? '<span>◎ Measures what you know. Nothing to study first.</span>' : "") +
        (t.kind === "lesson" ? '<span>✦ Ends with exercises</span>' : "") + '</div>';
    if (t.rules) html += '<div class="hero-rules"><span aria-hidden="true">⚑</span><span><strong>Rules:</strong> ' + esc(t.rules) + '</span></div>';
    if (pend) {
      html += '<div class="hero-submitted"><span class="chip chip-wait">Submitted</span>' +
        '<p>Sent ' + esc(ago(pend.ts)) + "." + (claudeOK() ? "" : ' In Claude Code, say <strong>"check my inbox"</strong> to get it graded.') + "</p>" + gradeButton() +
        '<button class="btn btn-ghost btn-sm" data-withdraw="' + esc(pend.id) + '">Withdraw</button></div>' +
        '<div class="hero-actions">' + openButton(t, "btn btn-ghost") + '</div>';
    } else {
      var running = active && active.task === t.id;
      html += (running ? '<div class="hero-live" data-hero-clock></div>' : "") +
        '<div class="hero-actions">' + openButton(t, "btn btn-topic") +
        (t.submit ? '<button class="btn ' + (t.href ? "btn-ghost" : "btn-topic") + '" data-submit="' + esc(t.id) + '">' + esc(meta.submit) + '</button>' : "") +
        hintsButton(t, "btn btn-ghost") +
        (!active ? '<button class="btn btn-ghost" data-start-task="' + esc(t.id) + '">▶ Start ' + taskMinutes(topic) + ' min on this</button>' : "") +
        '</div>' + stuckNudge(t);
    }
    return html + '</section>';
  }

  // ---------------------------------------------------------------- the recall warm-up ("From memory")
  // A few one-line questions the tutor wrote from passed work (state.json recall), picked by the server
  // (server.py pick_recall). After 3+ days away the same card is the welcome back. Answers go to the
  // inbox as kind "recall"; "Not now" hides it for today in this browser.
  var RECALL_KEY = "edu.recall.hidden.v1";
  function recallToday() {
    var r = DATA && DATA.derived && DATA.derived.recall;
    if (!r || !r.questions || !r.questions.length || r.sent_today || store(RECALL_KEY) === dayKey(new Date())) return null;
    return r;
  }
  function recallCard(bar) {
    var r = recallToday();
    if (!r) return "";
    var n = r.questions.length, list = "<ol>" + r.questions.map(function (q) { return "<li>" + esc(q.q) + "</li>"; }).join("") + "</ol>";
    var head = r.comeback ? "Start with something you already know." : plural(n, "quick question") + " from earlier work.";
    var sub = r.comeback ? "About 5 minutes, from memory. These come from work you already passed, newest first, so it's an easy start."
      : "No notes, about two minutes. Whatever comes to mind counts, and \"I don't remember\" is a fine answer.";
    var buttons = '<div class="recall-actions"><button class="btn btn-topic btn-sm" type="button" data-recall="go">' + (r.comeback ? "Start the warm-up" : "Answer from memory") + "</button>" +
      '<button class="btn btn-ghost btn-sm" type="button" data-recall="later">Not now</button></div>';
    if (bar) return '<div class="bx-job bx-recall' + (r.comeback ? " is-comeback" : "") + '"><div class="bx-k">' + (r.comeback ? "Welcome back" : "From memory") + "</div>" +
      "<h2>" + esc(head) + "</h2><p>" + esc(sub) + "</p>" + list + buttons + "</div>";
    return '<section class="card recall' + (r.comeback ? " is-comeback" : "") + '" aria-labelledby="recall-title"><div class="card-head"><span class="card-title">' +
      (r.comeback ? "Warm-up" : "From memory") + '</span><span class="card-sub">' + (r.comeback ? "about 5 minutes" : "before Up next") + "</span></div>" +
      '<h3 id="recall-title">' + esc(head) + "</h3><p>" + esc(sub) + "</p>" + list + buttons + "</section>";
  }
  function openRecall() {
    var r = recallToday();
    if (!r) return;
    submitCtx = { kind: "recall", topic: "general", task: "recall", title: r.comeback ? "Welcome back: from memory" : "From memory", recall: r.questions.map(function (q) { return q.id; }) };
    renderSubmitForm({ chipClass: "chip-probe", chip: "From memory", title: submitCtx.title,
      intro: (r.comeback ? "An easy start: this is all work you passed. " : "") + "Answer without looking anything up. A few words each is plenty, and \"I don't remember\" is a real answer: it tells Claude what to bring back.",
      fields: r.questions.map(function (q) { return q.q; }), honor: false, button: "Send to Claude", sure: false });
  }
  function recallLater() { store(RECALL_KEY, dayKey(new Date())); render(); }

  // a topic can name the block kind its tasks run under (state.json topics[].block); else the first kind
  function taskBlock(topic) { return topic.block && BLOCKS[topic.block] ? topic.block : Object.keys(BLOCKS)[0]; }
  function taskMinutes(topic) { return BLOCKS[taskBlock(topic)].minutes || 50; }

  function resolveHref(href) {
    // markdown notes open straight in Obsidian; everything else is served by this dashboard
    var m = /^\/vault\/(.+)\.md$/.exec(href || "");
    if (!m || !notesInObsidian()) return href;
    return "obsidian://open?vault=" + encodeURIComponent(obsidianVault()) + "&file=" + encodeURIComponent(decodeURIComponent(m[1]));
  }

  function openButton(t, cls) {
    if (!t.href) return "";
    var href = resolveHref(t.href);
    var label = kindMeta(t.kind).open + (/^obsidian:/.test(href) ? " in Obsidian" : "");
    return '<a class="' + cls + '" href="' + esc(href) + '"' + openTarget(href) + '>' + esc(label) + ' ↗</a>';
  }

  function renderQueue(all, hero) {
    var rest = all.filter(function (e) { return !hero || e.task.id !== hero.task.id; })
                  .filter(function (e) { return e.task.status !== "done"; });
    if (!rest.length) return "";
    var n = 1;
    var open = rest.filter(function (e) { return e.task.status !== "locked"; });
    var locked = rest.filter(function (e) { return e.task.status === "locked"; });
    function row(e) {
      var t = e.task, meta = kindMeta(t.kind), pend = pendingFor(t.id), locked = t.status === "locked";
      n++;
      var right = "";
      if (locked) right = '<span class="chip">🔒 Locked</span>';
      else if (pend) right = '<span class="chip chip-wait">Submitted</span>';
      else right = openButton(t, "btn btn-ghost btn-sm") + (t.submit ? ' <button class="btn btn-soft btn-sm" data-submit="' + esc(t.id) + '">' + esc(meta.submit) + '</button>' : "") +
        (t.exercise ? " " + hintsButton(t, "btn btn-ghost btn-sm") : "");
      return '<div class="q-item' + (locked ? " is-locked" : "") + '" style="--c:var(--' + esc(KIND[t.kind] ? t.kind : "lesson") + ')">' +
        '<div class="q-num">' + n + '</div>' +
        '<div><div class="q-kind"><span class="chip chip-' + esc(t.kind) + '">' + esc(meta.label) + '</span><span class="card-sub">' + esc(t.label || "") + '</span></div>' +
        '<h3>' + esc(t.title) + '</h3><p>' + esc(locked ? (t.unlock || "Locked") : (t.why || "")) + '</p>' + (locked ? "" : stuckNudge(t)) + '</div>' +
        '<div class="q-actions">' + right + '</div></div>';
    }
    var items = open.map(row).join("");
    var folded = locked.length ? '<details class="q-locked"><summary>' + locked.length + " more queued, unlocking as you go</summary>" +
      '<div class="queue">' + locked.map(row).join("") + "</div></details>" : "";
    return '<section class="card"><div class="card-head"><span class="card-title">After that</span>' +
      '<span class="card-sub">' + (open.length ? "Open whenever you like" : "Nothing else open right now") + '</span></div>' +
      (items ? '<div class="queue">' + items + "</div>" : "") + folded + "</section>";
  }

  // ---------------------------------------------------------------- render: topics
  function renderTopic(topic) {
    var d = DATA.derived.topics[topic.id] || { stats: {}, library: { lessons: [], reference: [] } };
    var s = d.stats || {};
    var lib = d.library || { lessons: [], reference: [] };
    function list(items) {
      if (!items.length) return '<p class="card-sub">Nothing yet.</p>';
      return "<ul>" + items.map(function (it) {
        var num = (it.file.match(/^(\d+)/) || ["", "·"])[1].replace(/^0+/, "");
        var title = it.title.replace(/^(Lesson|Ref)\s*\d+\s*[—-]\s*/i, "");
        return '<li><a href="' + esc(it.href) + '" target="_blank" rel="noopener"><b>' + esc(num) + '</b><span>' + esc(title) + '</span></a></li>';
      }).join("") + "</ul>";
    }
    if (isDormant(topic)) {
      return '<section class="card topic-card topic-dormant" style="--topic:' + esc(topic.color) + '">' +
        '<div class="topic-top"><div><span class="card-title">Your topic · not started</span>' +
        '<h3 style="margin-top:10px">' + esc(topic.title) + '</h3><p>' + esc(topic.tagline || "") + '</p></div></div>' +
        '<p class="card-sub" style="margin:10px 0 0">Nothing here yet, and that is fine. Its milestones, proof and skills appear once it starts.</p>' +
        '<div class="topic-links">' +
        noteLink(topic.path + "/MISSION", "Mission") + noteLink(topic.path + "/Dashboard", "Detailed log") + '</div></section>';
    }
    return '<section class="card topic-card" style="--topic:' + esc(topic.color) + '">' +
      '<div class="topic-top"><div><span class="card-title">Your topic · ' + esc(topic.phase || "") + '</span>' +
        '<h3 style="margin-top:10px">' + esc(topic.title) + '</h3><p>' + esc(topic.tagline || "") + '</p></div>' +
        (topic.gate && topic.gate.level ? '<span class="gate gate-' + esc(topic.gate.level) + '" title="Readiness gate">' + esc(topic.gate.level) + '</span>' : "") + '</div>' +
      '<div class="stats">' +
        stat(s.lessons, "lessons") + stat((s.probes_done || 0) + "/" + (s.probes_total || 0), "probes done") +
        stat(s.records, "things proven") + stat(s.glossary, "terms owned") +
      '</div>' +
      '<div class="lib" style="margin-top:18px"><div><h4>Lessons</h4>' + list(lib.lessons) + '</div>' +
        '<div><h4>Cheat sheets</h4>' + list(lib.reference) + '</div></div>' +
      '<div class="topic-links">' +
        noteLink(topic.path + "/MISSION", "Mission") + noteLink(topic.path + "/Dashboard", "Detailed log") + noteLink(topic.path + "/GLOSSARY", "Glossary") +
      '</div></section>';
  }
  function noteLink(path, label) {
    var h = noteHref(path);
    return '<a class="btn btn-ghost btn-sm" href="' + esc(h) + '"' + openTarget(h) + '>' + esc(label) + ' ↗</a>';
  }
  function stat(v, label) { return '<div class="stat"><b>' + esc(v == null ? "–" : v) + '</b><span>' + esc(label) + '</span></div>'; }

  function renderLinked() {
    var links = DATA.derived.linked || [];
    var cards = links.map(function (l) {
      var pct = l.lessons ? Math.round(100 * l.read / l.lessons) : 0;
      return '<a class="linked" href="' + esc(l.url) + '" target="_blank" rel="noopener" style="--c:' + esc(l.color || "var(--reading)") + '">' +
        '<div class="linked-head"><span class="linked-swatch"></span><h4>' + esc(l.title) + '</h4></div>' +
        '<p>' + esc(l.blurb || "") + '</p>' +
        '<div class="bar" title="' + l.read + ' of ' + l.lessons + ' lessons opened"><i style="width:' + pct + '%"></i></div>' +
        '<small>' + l.read + ' of ' + l.lessons + ' lessons opened · ' + l.records + ' learning records</small></a>';
    }).join("");
    return '<section class="card"><div class="card-head"><div><span class="card-title">' + (cards ? "Your other courses" : "Add a topic") + '</span></div>' +
      (cards ? '<span class="card-sub">Linked, read-only</span>' : "") + '</div>' +
      (cards ? '<div class="linked-grid">' + cards + '</div>' : "") +
      '<button class="add-topic" type="button" data-newtopic style="margin-top:12px"><span class="plus">+</span><span>Want to learn something new? <b>Start a new topic</b>: say what and why, Claude sets it up, and it shows up here.</span></button>' +
      '</section>';
  }

  // ---------------------------------------------------------------- render: right column
  function renderMilestones(topic) {
    var ms = topic.milestones || [];
    var active = ms.filter(function (m) { return m.status === "active"; });
    if (!active.length && ms[0]) active = [ms[0]];
    return active.map(function (cur, i) { return milestoneCard(topic, ms, cur, i === active.length - 1); }).join("");
  }

  function milestoneCard(topic, ms, cur, withTrack) {
    var steps = cur.steps || [];
    var done = steps.filter(function (s) { return s.done; }).length;
    var pct = steps.length ? done / steps.length : 0;
    var r = 44, c = 2 * Math.PI * r, gid = "g-" + esc(topic.id) + "-" + esc(cur.id);
    var ring = '<div class="ring"><svg width="104" height="104" viewBox="0 0 104 104" aria-hidden="true">' +
      '<circle cx="52" cy="52" r="' + r + '" fill="none" stroke="var(--bg-2)" stroke-width="10"/>' +
      '<circle cx="52" cy="52" r="' + r + '" fill="none" stroke="url(#' + gid + ')" stroke-width="10" stroke-linecap="round" stroke-dasharray="' + c + '" stroke-dashoffset="' + (c * (1 - pct)) + '"/>' +
      '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="' + esc(topic.color) + '"/><stop offset="1" stop-color="var(--checkpoint)"/></linearGradient></defs>' +
      '</svg><div class="ring-label"><div><b>' + done + '/' + steps.length + '</b><span>steps</span></div></div></div>';
    var stepList = steps.map(function (s) {
      var cls = s.done ? "done" : s.current ? "current" : "";
      return '<li class="' + cls + '"><span class="tick">✓</span><span>' + esc(s.title) + '</span></li>';
    }).join("");
    var track = !withTrack ? "" : '<div class="ms-track">' + ms.map(function (m) {
      return '<div class="ms-row is-' + esc(m.status) + '"><span class="ms-id">' + esc(m.id) + '</span>' +
        '<span>' + esc(m.title) + (m.status === "locked" ? ' <span class="muted">🔒</span>' : "") + '</span><small>' + esc(m.estimate || "") + '</small></div>';
    }).join("") + '</div>';
    return '<section class="card" style="--topic:' + esc(topic.color) + '">' +
      '<div class="card-head"><span class="card-title">Milestone ' + esc(cur.id) + '</span><button class="info" data-help="milestones" aria-label="What are milestones?">?</button></div>' +
      '<div class="ms-current">' + ring + '<div><h3>' + esc(cur.title) + '</h3><p>Goal: ' + esc(cur.goal || "") + '</p><p>Estimate: ' + esc(cur.estimate || "") + '</p></div></div>' +
      '<ul class="steps">' + stepList + '</ul>' + track + '</section>';
  }


  function renderEvidence(topic) {
    var counts = {};
    (topic.history || []).forEach(function (h) { if (h.evidence) counts[h.date] = (counts[h.date] || 0) + 1; });
    var today = new Date(); today.setHours(12, 0, 0, 0);
    var weeks = 18, start = new Date(today);
    start.setDate(start.getDate() - (weeks * 7 - 1) - ((today.getDay() + 6) % 7 - 6));
    var cells = "", total = 0, active = 0, todayK = dayKey(today);
    for (var i = 0; i < weeks * 7; i++) {
      var d = new Date(start); d.setDate(start.getDate() + i);
      var k = dayKey(d), n = counts[k] || 0;
      if (d > today) { cells += '<i style="visibility:hidden"></i>'; continue; }
      total += n; if (n) active++;
      cells += '<i class="' + (n >= 3 ? "l3" : n === 2 ? "l2" : n === 1 ? "l1" : "") + (k === todayK ? " is-today" : "") + '" title="' + k + ": " + n + ' proven"></i>';
    }
    var wins = (topic.history || []).slice(0, 6).map(function (h) {
      return '<li><span class="w-dot' + (h.evidence ? " ev" : "") + '"></span><div><b>' + esc(h.title) + '</b>' +
        '<small>' + esc(h.date) + (h.detail ? " · " + esc(h.detail) : "") + '</small></div></li>';
    }).join("");
    return '<section class="card"><div class="card-head"><span class="card-title">Evidence log</span><button class="info" data-help="evidence" aria-label="What is the evidence log?">?</button></div>' +
      '<div class="heat-wrap"><div class="heat" role="img" aria-label="' + total + ' things proven over ' + active + ' days">' + cells + '</div></div>' +
      '<div class="heat-foot"><span><b>' + total + '</b> things proven, over <b>' + active + '</b> days</span><span>Squares only light up for proof, not for time spent</span></div>' +
      '<ul class="wins">' + wins + '</ul></section>';
  }

  // "How sure are you?" against the grade, once there are a few graded answers (server.py calibration)
  function renderCalibration() {
    var c = DATA.derived && DATA.derived.calibration;
    if (!c || c.rated < 3) return "";
    var s = c.solid, head = s.n ? "You said solid " + plural(s.n, "time") + ", and " + s.passed + " of those passed."
      : "You haven't said solid yet.";
    var rows = ["guessed", "shaky", "solid"].map(function (k) {
      var x = c[k], pct = x.n ? Math.round(100 * x.passed / x.n) : 0;
      return '<div class="cal-row"><b>' + cap(k) + '</b><div class="cal-bar" aria-hidden="true"><i style="width:' + pct + '%"></i></div>' +
        "<span>" + (x.n ? x.passed + " of " + x.n + " passed" : "not used yet") + "</span></div>";
    }).join("");
    return '<section class="card cal"><div class="card-head"><span class="card-title">How sure vs how it went</span></div>' +
      "<p>" + esc(head) + "</p>" + rows +
      '<small class="muted">Out of ' + plural(c.rated, "graded answer") + '. A pass means Claude logged it as proof. If "solid" often doesn\'t pass, slow down before you hand in.</small></section>';
  }

  function renderSkills(topic) {
    var rows = (topic.regions || []).map(function (r) {
      var bars = "";
      for (var i = 1; i <= 4; i++) bars += '<i class="' + (r.level >= i ? "on" : "") + '"></i>';
      return '<div class="skill"><div class="skill-top"><b>' + esc(r.name) + '</b><span>' + esc(LADDER[r.level] || "") + '</span></div>' +
        '<div class="ladder" aria-label="' + esc(LADDER[r.level]) + '">' + bars + '</div><small>' + esc(r.note || "") + '</small></div>';
    }).join("");
    return '<section class="card" style="--topic:' + esc(topic.color) + '"><div class="card-head"><span class="card-title">Skills ladder</span><button class="info" data-help="ladder" aria-label="What is the skills ladder?">?</button></div>' +
      '<div class="skills">' + rows + '</div>' +
      '<div class="legend" style="margin-top:14px"><span>heard of</span><span>understand</span><span>use alone</span><span>public proof</span></div></section>';
  }

  // ---------------------------------------------------------------- dialogs
  function openOverlay(id) { var el = $("#" + id); el.hidden = false; document.body.style.overflow = "hidden"; return el; }
  function closeOverlay(el) { el.hidden = true; if (!document.querySelector(".overlay:not([hidden])")) document.body.style.overflow = ""; }

  function findTask(id) {
    var all = actionableTasks();
    for (var i = 0; i < all.length; i++) if (all[i].task.id === id) return all[i];
    return null;
  }

  function openSubmit(taskId) {
    var entry = findTask(taskId);
    if (!entry) return;
    var t = entry.task, meta = kindMeta(t.kind), sub = t.submit || {};
    submitCtx = { kind: sub.type === "done" ? "done" : "answers", topic: entry.topic.id, task: t.id, title: (t.label ? t.label + " · " : "") + t.title, probe: t.kind === "probe" || t.kind === "checkpoint" };
    renderSubmitForm({
      chipClass: "chip-" + t.kind, chip: meta.label, title: submitCtx.title,
      intro: sub.intro || (sub.type === "done" ? "Mark this as done. Add a note if there's anything Claude should know." : "Type your answers below."),
      rules: t.rules, fields: sub.type === "done" ? [] : (sub.fields || ["Your answer"]), honor: submitCtx.probe, button: meta.submit, sure: true
    });
  }

  function openNote() {
    submitCtx = { kind: "note", topic: "general", task: "note", title: "Note to Claude", probe: false };
    renderSubmitForm({ chipClass: "chip-reading", chip: "Note", title: "Send Claude a note",
      intro: "A question, something that confused you, or a change you want. Claude reads it the next time it grades your inbox.",
      fields: [], honor: false, button: "Send note", noteLabel: "Your note", noteRequired: true });
  }

  function renderSubmitForm(o) {
    var form = $("#submit-form");
    form.reset();
    $("#sub-chip").className = "chip " + o.chipClass;
    $("#sub-chip").textContent = o.chip;
    $("#sub-title").textContent = o.title;
    $("#sub-intro").textContent = o.intro || "";
    var rules = $("#sub-rules");
    rules.hidden = !o.rules;
    rules.innerHTML = o.rules ? "<strong>Rules:</strong> " + esc(o.rules) : "";
    $("#sub-fields").innerHTML = o.fields.map(function (label, i) {
      return '<label class="field"><span class="field-label">' + esc(label) + '</span>' +
        '<textarea name="f' + i + '" data-label="' + esc(label) + '" rows="' + (/why|rewrite|fix|complexity/i.test(label) ? 3 : 2) + '" placeholder="Your answer, or &quot;I don\'t know&quot;"></textarea></label>';
    }).join("");
    var noteLabel = form.querySelector('textarea[name="__note"]').previousElementSibling;
    noteLabel.innerHTML = o.noteLabel ? esc(o.noteLabel) : 'Anything else? <em>optional</em>';
    form.querySelector('textarea[name="__note"]').rows = o.noteRequired ? 6 : 2;
    $("#sub-honor").hidden = !o.honor;
    $("#sub-sure").hidden = !o.sure;
    $("#sub-error").hidden = true;
    $("#sub-send").textContent = o.button || "Submit";
    $("#sub-send").disabled = false;
    openOverlay("submit");
    setTimeout(function () { var f = form.querySelector("textarea"); if (f) f.focus(); }, 60);
  }

  function submitForm(ev) {
    ev.preventDefault();
    if (!submitCtx) return;
    var form = $("#submit-form"), err = $("#sub-error");
    var fields = {};
    form.querySelectorAll("#sub-fields textarea").forEach(function (ta) { fields[ta.dataset.label] = ta.value; });
    var note = form.querySelector('textarea[name="__note"]').value;
    var honor = form.querySelector('input[name="__honor"]').checked;
    var sure = form.querySelector('input[name="__sure"]:checked');

    function fail(msg) { err.textContent = msg; err.hidden = false; }
    if ((submitCtx.kind === "answers" || submitCtx.kind === "recall") && !Object.keys(fields).some(function (k) { return fields[k].trim(); })) return fail("Write at least one answer. \"I don't know\" counts.");
    if (submitCtx.kind === "note" && !note.trim()) return fail("Write your note first.");
    if (submitCtx.kind !== "note" && submitCtx.kind !== "recall" && !sure) return fail("Pick how sure you are: guessed, shaky or solid. Any of them is fine, as long as it's honest.");
    if (submitCtx.probe && !honor) return fail("Tick the box to confirm you did it unaided. If you did get help, don't submit this one. Send Claude a note instead and you'll get a fresh probe.");

    var btn = $("#sub-send");
    btn.disabled = true; btn.textContent = "Saving…";
    fetch("/api/inbox", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: submitCtx.topic, task: submitCtx.task, kind: submitCtx.kind, title: submitCtx.title, fields: fields, note: note, honor: honor, confidence: sure ? sure.value : undefined, recall: submitCtx.recall })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.body.error || "Could not save");
        closeOverlay($("#submit"));
        toast("<span>✓</span><span><b>Saved to your inbox.</b> " + (claudeOK() ? "Press ✦ Grade it now when you're ready." : "Next, in Claude Code say \"check my inbox\".") + "</span>", 7000);
        load();
      })
      .catch(function (e) { btn.disabled = false; btn.textContent = "Try again"; fail("Couldn't save: " + e.message + ". Your text is still here."); });
  }

  function withdraw(id) {
    if (!confirm("Withdraw this submission? You can submit again afterwards.")) return;
    fetch("/api/withdraw", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: id }) })
      .then(function (r) { if (!r.ok) throw new Error(); toast("Submission withdrawn. You can submit again whenever you're ready."); load(); })
      .catch(function () { toast("Couldn't withdraw it. It may already have been graded."); load(); });
  }

  // onboarding
  var obStep = 0;
  function showOnboarding() { obStep = 0; paintOnboarding(); openOverlay("onboarding"); setTimeout(function () { $("#ob-next").focus(); }, 60); }
  function paintOnboarding() {
    document.querySelectorAll(".ob-slide").forEach(function (s) { s.hidden = Number(s.dataset.step) !== obStep; });
    document.querySelectorAll(".ob-dots .dot").forEach(function (d) { d.classList.toggle("is-on", Number(d.dataset.go) === obStep); });
    $("#ob-back").hidden = obStep === 0;
    $("#ob-next").textContent = obStep === 2 ? "Let's go" : "Next";
  }
  function finishOnboarding() { store(ONBOARD_KEY, "1"); closeOverlay($("#onboarding")); askGifts(); }

  // gifts cost the learner's Claude plan, so they start undecided (null) and the page asks once
  function askGifts() {
    if (!DATA || !DATA.config || DATA.config.gifts !== null) return;
    if (document.querySelector(".overlay:not([hidden])")) return;
    try { if (sessionStorage.getItem("edu.giftask.later")) return; sessionStorage.setItem("edu.giftask.later", "1"); } catch (e) {}
    openOverlay("gift-ask");          // once per browser session; closing it without an answer asks again next time
  }
  function answerGifts(yes) {
    fetch("/api/config", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) {
      var c = j.config; c.gifts = yes;
      return postConfig({ config: c });
    }).then(function () {
      closeOverlay($("#gift-ask"));
      if (DATA && DATA.config) DATA.config.gifts = yes;
      toast(yes ? "Gifts are on." : "No gifts. You can turn them on in Settings.");
    }).catch(function (e) { toast("Couldn't save: " + e.message); });
  }

  function openHelp(section) {
    openOverlay("help");
    if (section) {
      var map = { milestones: 3, gate: 4, ladder: 5, evidence: 6 };
      var details = document.querySelectorAll("#help .faq details");
      var target = details[map[section]];
      if (target) { target.open = true; setTimeout(function () { target.scrollIntoView({ block: "center", behavior: "smooth" }); }, 80); }
    }
  }

  // ---------------------------------------------------------------- focus blocks
  // The running block lives in localStorage so it survives reloads; finished blocks are
  // posted to /api/blocks (-> _system/blocks.jsonl). Posts that fail wait in UNSENT_KEY.
  var BLOCK_KEY = "edu.block.v1";
  var UNSENT_KEY = "edu.block.unsent.v1";
  // Block kinds come from Settings (config.json → blocks.kinds); these are the defaults.
  // color is a theme token (lesson, probe, checkpoint, reading, project, mock, coral, amber, green) or #rrggbb.
  var BLOCKS = {
    lessons:  { label: "Lessons",  color: "lesson" },
    practice: { label: "Practice", color: "mock", minutes: 60 },
    reading:  { label: "Reading",  color: "reading" },
    free:     { label: "Free",     color: "probe" },
    play:     { label: "Play",     color: "checkpoint" }
  };
  var FUN_BLOCKS = { free: true, play: true };
  var PRESETS = [25, 50, 90];
  var DIE_TILES = 24;
  var TILE_MIN = 25;   // one tile = 25 focused minutes, so a die = 10 hours
  var NODE_GPUS = 8;   // 8 shipped dies = one node (an 8-GPU server, 80 hours)
  var RACK_NODES = 4;  // 4 nodes = one rack (320 hours)
  var pickedDie = null;
  var BASE_TITLE = document.title;
  var pick = { block: "lessons", minutes: 50 };
  var active = null, endTimer = null, tickTimer = null, audio = null, celebrateNext = null, saving = null;
  var blockEl = document.createElement("section");
  blockEl.className = "card blk-card";
  blockEl.id = "block";

  function readJSON(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } }
  function writeJSON(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  // a kind removed in Settings still has old blocks on the die: they keep a neutral colour
  function blockColor(id) {
    var c = BLOCKS[id] ? BLOCKS[id].color : "probe";
    return /^#/.test(c) ? c : "var(--" + c + ")";
  }
  function blockLabel(id) { return BLOCKS[id] ? BLOCKS[id].label : id; }
  function clock(ms) {
    var s = Math.max(0, Math.ceil(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(sec).padStart(2, "0");
  }
  function hhmm(ms) { return new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }

  // server records plus anything still waiting to be sent, oldest first
  function allBlocks() {
    var list = ((DATA && DATA.blocks) || []).slice();
    var seen = {};
    list.forEach(function (b) { seen[b.started] = true; });
    (readJSON(UNSENT_KEY) || []).forEach(function (b) { if (!seen[b.started]) list.push(b); });
    return list.sort(function (a, b) { return a.started < b.started ? -1 : 1; });
  }

  function mountBlockCard() {
    var slot = $("#blk-slot");
    if (!slot) return;
    var focused = blockEl.contains(document.activeElement) ? document.activeElement : null;
    if (!blockEl.firstChild) paintBlockCard();
    slot.replaceWith(blockEl);
    paintDie();
    if (focused) focused.focus();
  }

  function paintBlockCard() {
    blockEl.innerHTML = '<div class="card-head"><span class="card-title">Focus block</span><span class="card-sub" data-today></span></div>' +
      '<div data-controls></div><div data-die></div>';
    paintControls();
  }

  function paintControls() {
    var el = blockEl.querySelector("[data-controls]");
    if (!el) return;
    if (active) {
      el.innerHTML = '<div class="blk-live" style="--c:' + blockColor(active.block) + '">' +
        '<div class="blk-live-top"><span class="chip" style="--c:' + blockColor(active.block) + '">' + esc(blockLabel(active.block)) + '</span>' +
        '<span class="card-sub">' + active.minutes + ' min · ends ' + esc(hhmm(active.end)) + '</span></div>' +
        '<div class="blk-clock" data-clock role="timer" aria-label="Time remaining"></div>' +
        '<div class="bar"><i data-bar></i></div>' +
        '<div class="blk-water"><span data-water-text>' + esc(waterText()) + '</span>' +
          '<button class="btn btn-soft btn-sm" type="button" data-drink' + ((active.served || 0) > (active.drunk || 0) ? "" : " hidden") + '>Drank it</button></div>' +
        '<button class="btn btn-ghost btn-sm" type="button" data-blk-stop>Stop early</button></div>';
      tick();
      return;
    }
    var custom = PRESETS.indexOf(pick.minutes) < 0;
    el.innerHTML = '<div class="blk-idle">' +
      '<div class="blk-row" role="group" aria-label="Block">' + Object.keys(BLOCKS).map(function (id) {
        return '<button class="blk-opt" type="button" style="--c:' + blockColor(id) + '" data-blk="' + id + '" aria-pressed="' + (pick.block === id) + '">' +
          '<span class="blk-sw"></span>' + esc(BLOCKS[id].label) + '</button>';
      }).join("") + '</div>' +
      '<div class="blk-row" role="group" aria-label="Duration">' + PRESETS.map(function (m) {
        return '<button class="blk-opt" type="button" data-min="' + m + '" aria-pressed="' + (pick.minutes === m) + '">' + m + ' min</button>';
      }).join("") +
        '<label class="blk-opt blk-custom" aria-pressed="' + custom + '"><input type="number" min="1" max="240" inputmode="numeric" placeholder="Custom" aria-label="Custom minutes" data-custom value="' + (custom ? pick.minutes : "") + '"> min</label>' +
      '</div>' +
      '<div class="blk-row" role="group" aria-label="Water rounds"><span class="blk-lab">💧 Water</span>' + [15, 30, 0].map(function (v) {
        return '<button class="blk-opt" type="button" data-water="' + v + '" aria-pressed="' + (waterEvery() === v) + '">' + (v ? "every " + v + " min" : "off") + '</button>';
      }).join("") + '</div>' +
      '<button class="btn btn-topic blk-start" type="button" data-blk-start></button></div>';
    paintPick();
  }

  // update the pressed states in place so focus and typing survive
  function paintPick() {
    blockEl.querySelectorAll("[data-blk]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.blk === pick.block)); });
    blockEl.querySelectorAll("[data-min]").forEach(function (b) { b.setAttribute("aria-pressed", String(Number(b.dataset.min) === pick.minutes)); });
    var c = blockEl.querySelector(".blk-custom");
    if (c) c.setAttribute("aria-pressed", String(PRESETS.indexOf(pick.minutes) < 0));
    var start = blockEl.querySelector("[data-blk-start]");
    if (start) {
      var ok = pick.minutes >= 1 && pick.minutes <= 240;
      start.disabled = !ok;
      start.style.setProperty("--topic", blockColor(pick.block));
      start.textContent = ok ? "Start " + pick.minutes + " min of " + blockLabel(pick.block) : "Pick 1 to 240 minutes";
    }
  }

  // Lay every block's minutes end to end, oldest first, and cut that line into 25-minute tiles.
  // A tile can hold minutes from two blocks; the last tile may be only partly filled.
  function tileModel(list) {
    var tiles = [], cur = null;
    list.forEach(function (b, bi) {
      var left = b.minutes;
      while (left > 0) {
        if (!cur) { cur = { mins: 0, parts: {}, from: [], byBlock: {} }; tiles.push(cur); }
        var take = Math.min(left, TILE_MIN - cur.mins);
        cur.mins += take;
        cur.parts[b.block] = (cur.parts[b.block] || 0) + take;
        cur.byBlock[bi] = (cur.byBlock[bi] || 0) + take;
        if (cur.from.indexOf(bi) < 0) cur.from.push(bi);
        left -= take;
        if (cur.mins >= TILE_MIN) cur = null;
      }
    });
    return tiles;
  }

  function withoutBlock(list, started) { return list.filter(function (b) { return b.started !== started; }); }

  function fullTiles(tiles) { return tiles.filter(function (t) { return t.mins >= TILE_MIN; }).length; }

  function tileCell(t, isNew) {
    if (!t) return "<i></i>";
    var top = Object.keys(t.parts).sort(function (a, b) { return t.parts[b] - t.parts[a]; });
    var title = top.map(function (k) { return blockLabel(k) + " " + t.parts[k] + " min"; }).join(" + ");
    var full = t.mins >= TILE_MIN;
    if (!full) title += " · " + t.mins + " of " + TILE_MIN + " min, in progress";
    return '<i class="' + (full ? "on" : "part") + (isNew ? " is-new" : "") + '" style="--c:' + blockColor(top[0]) +
      (full ? "" : ";--p:" + Math.round(100 * t.mins / TILE_MIN) + "%") + '" title="' + esc(title) + '"></i>';
  }

  // fresh = the start time (ISO) of a block that just finished: mark its tiles, and if it
  // finished a die, show that full die instead of the empty next one
  function dieHTML(list, fresh) {
    var tiles = tileModel(list), full = fullTiles(tiles), newest = -1;
    list.forEach(function (b, i) { if (fresh && b.started === fresh) newest = i; });
    var shipped = Math.floor(full / DIE_TILES);
    var d = shipped;
    if (newest >= 0 && shipped > Math.floor(fullTiles(tileModel(withoutBlock(list, fresh))) / DIE_TILES)) d = shipped - 1;
    var mine = tiles.slice(d * DIE_TILES, d * DIE_TILES + DIE_TILES);
    var cells = "";
    for (var i = 0; i < DIE_TILES; i++) cells += tileCell(mine[i], newest >= 0 && mine[i] && mine[i].from.indexOf(newest) >= 0);
    var etched = Math.min(DIE_TILES, Math.max(0, full - d * DIE_TILES));
    return '<div class="die" role="img" aria-label="Die ' + (d + 1) + ', ' + etched + ' of ' + DIE_TILES + ' tiles etched, one tile per ' + TILE_MIN + ' minutes">' + cells + '</div>' +
      '<div class="die-foot"><span>Die #' + (d + 1) + ' · <b>' + etched + '</b>/' + DIE_TILES + ' tiles</span>' +
      '<span><b>' + shipped + '</b> shipped</span></div>';
  }

  function hm(mins) { return (mins >= 60 ? Math.floor(mins / 60) + "h" + (mins % 60 ? " " : "") : "") + (mins % 60 || mins < 60 ? (mins % 60) + "m" : ""); }

  // One summary per die, shipped or in progress: dates, minutes by block type, and the
  // blocks it was made from. A block that straddles two dies counts toward both.
  function dieSummaries(list) {
    var tiles = tileModel(list), out = [];
    for (var d = 0; d * DIE_TILES < tiles.length; d++) {
      var mine = tiles.slice(d * DIE_TILES, d * DIE_TILES + DIE_TILES), parts = {}, mins = 0, idx = [], tasks = {};
      mine.forEach(function (t) {
        Object.keys(t.parts).forEach(function (k) { parts[k] = (parts[k] || 0) + t.parts[k]; mins += t.parts[k]; });
        Object.keys(t.byBlock).forEach(function (bi) { var tk = list[bi].task; if (tk) tasks[tk] = (tasks[tk] || 0) + t.byBlock[bi]; });
        idx = idx.concat(t.from);
      });
      var full = mins >= DIE_TILES * TILE_MIN;
      var last = list[Math.max.apply(null, idx)];
      out.push({ n: d + 1, full: full, parts: parts, mins: mins, tasks: tasks,
        start: list[Math.min.apply(null, idx)].started, end: full ? (last.ts || last.started) : null });
    }
    return out;
  }

  // Evidence entries (state.json history, evidence: true) dated inside a die's span
  function provedDuring(die) {
    var a = dayKey(new Date(die.start)), b = dayKey(die.end ? new Date(die.end) : new Date()), out = [];
    ((DATA && DATA.state && DATA.state.topics) || []).forEach(function (t) {
      (t.history || []).forEach(function (h) { if (h.evidence && h.date >= a && h.date <= b) out.push(h.title); });
    });
    return out;
  }

  // The die's mix of block types as stacked colour bands, biggest share at the bottom
  function mixFill(parts, pct) {
    var keys = Object.keys(parts).filter(function (k) { return parts[k]; }), total = 0, at = 0, stops = [];
    keys.forEach(function (k) { total += parts[k]; });
    keys.sort(function (a, b) { return parts[b] - parts[a]; }).forEach(function (k) {
      var from = at, to = at + pct * parts[k] / total;
      stops.push(blockColor(k) + " " + from.toFixed(1) + "%", blockColor(k) + " " + to.toFixed(1) + "%");
      at = to;
    });
    if (pct < 100) stops.push("transparent " + at.toFixed(1) + "%", "transparent 100%");
    return "linear-gradient(to top, " + stops.join(", ") + ")";
  }

  function dieDetail(die) {
    var fmt = function (iso) { return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" }); };
    var mix = Object.keys(die.parts).filter(function (k) { return die.parts[k]; })
      .sort(function (a, b) { return die.parts[b] - die.parts[a]; })
      .map(function (k) { return blockLabel(k) + " " + hm(die.parts[k]); }).join(", ");
    var proved = provedDuring(die);
    var spent = Object.keys(die.tasks).sort(function (a, b) { return die.tasks[b] - die.tasks[a]; }).map(function (id) {
      var e = findTask(id);
      return (e ? (e.task.label ? e.task.label + ": " : "") + e.task.title : id) + " " + hm(die.tasks[id]);
    });
    return "<b>Die #" + die.n + "</b> · " + esc(fmt(die.start)) + (die.end ? " – " + esc(fmt(die.end)) : ", in progress") +
      " · " + esc(hm(die.mins)) + (mix ? ": " + esc(mix) : "") +
      (spent.length ? "<br><b>Spent on:</b> " + esc(spent.join(" · ")) : "") +
      "<br><b>Proved " + (die.end ? "during it" : "so far") + ":</b> " + (proved.length ? esc(proved.join(" · ")) : "nothing graded yet");
  }

  function clusterHTML(list) {
    var dies = dieSummaries(list);
    var shipped = dies.filter(function (d) { return d.full; }).length;
    var perRack = NODE_GPUS * RACK_NODES;
    var rack = Math.floor(Math.max(0, dies.length - 1) / perRack);   // the rack the newest die sits in
    var nodes = "";
    for (var n = 0; n < RACK_NODES; n++) {
      var slots = "", filled = 0;
      for (var g = 0; g < NODE_GPUS; g++) {
        var die = dies[rack * perRack + n * NODE_GPUS + g];
        if (!die) { slots += '<i class="gpu"></i>'; continue; }
        if (die.full) filled++;
        var pct = die.full ? 100 : Math.round(100 * die.mins / (DIE_TILES * TILE_MIN));
        slots += '<button type="button" class="gpu ' + (die.full ? "on" : "wip") + (pickedDie === die.n ? " is-picked" : "") +
          '" data-gpu="' + die.n + '" style="background-image:' + mixFill(die.parts, pct) + '" aria-label="Die ' + die.n +
          (die.full ? ", shipped" : ", " + pct + "% done") + '"></button>';
      }
      nodes += '<div class="node' + (filled === NODE_GPUS ? " is-online" : "") + '"><span>node ' + (n + 1) + '</span><div class="gpus">' + slots + '</div><span>' + filled + "/" + NODE_GPUS + "</span></div>";
    }
    var picked = dies[(pickedDie || dies.length) - 1];
    return '<div class="cluster"><div class="cluster-head"><span class="card-title">Your cluster</span>' +
      '<span class="card-sub">Rack #' + (rack + 1) + (rack ? " · " + rack + " full rack" + (rack > 1 ? "s" : "") + " before it" : "") + '</span></div>' +
      '<div class="rack">' + nodes + '</div>' +
      '<p class="cluster-key">1 tile = ' + TILE_MIN + ' min · 1 die = ' + (DIE_TILES * TILE_MIN / 60) + ' h · ' + NODE_GPUS + ' dies = a node · ' + RACK_NODES + ' nodes = a rack · ' + shipped + ' shipped</p>' +
      (picked ? '<p class="cluster-detail" aria-live="polite">' + dieDetail(picked) + '</p>' : "") + '</div>';
  }

  function paintDie() {
    var el = blockEl.querySelector("[data-die]");
    if (!el) return;
    var list = allBlocks(), today = dayKey(new Date());
    var todays = list.filter(function (b) { return dayKey(new Date(b.ts || b.started)) === today; });
    var mins = todays.reduce(function (a, b) { return a + b.minutes; }, 0);
    blockEl.querySelector("[data-today]").textContent = todays.length ? "Today: " + todays.length + " · " + (mins >= 60 ? Math.floor(mins / 60) + "h " : "") + (mins % 60) + "m" : "One tile per " + TILE_MIN + " focused minutes";
    el.innerHTML = '<div class="die-wrap">' + dieHTML(list, false) +
      '<div class="die-legend">' + Object.keys(BLOCKS).map(function (id) {
        return '<span><i style="--c:' + blockColor(id) + '"></i>' + esc(BLOCKS[id].label) + '</span>';
      }).join("") + '</div>' + (list.length ? clusterHTML(list) : "") + '</div>';
    paintBarBits();
  }

  function tick() {
    if (!active) return;
    var left = active.end - Date.now();
    if (left <= 0) return finishBlock();
    var label = blockLabel(active.block), t = clock(left);
    var c = blockEl.querySelector("[data-clock]");
    if (c) c.textContent = t;
    var bar = blockEl.querySelector("[data-bar]");
    if (bar) bar.style.width = (100 * (1 - left / (active.end - active.start))).toFixed(2) + "%";
    var pill = $("#blk-pill");
    pill.hidden = false;
    pill.style.setProperty("--c", blockColor(active.block));
    pill.innerHTML = '<span class="blk-sw"></span>' + esc(label) + ' <b>' + t + '</b>';
    document.title = t + " · " + label + " · edu4self";
    var hc = $("[data-hero-clock]");
    if (hc) hc.textContent = "◷ " + t + " left on this · ends " + hhmm(active.end);
    document.body.style.setProperty("--blk", blockColor(active.block));
    waterCheck();
    paintWater();
    barTick();
  }

  function arm() {
    clearTimeout(endTimer); clearInterval(tickTimer);
    if (!active) return;
    // one exact timeout for the end, plus a display tick; background tabs throttle the tick, not the timeout
    endTimer = setTimeout(finishBlock, Math.max(0, active.end - Date.now()));
    tickTimer = setInterval(tick, 500);
    document.body.classList.add("blk-on");
  }

  function idle() {
    clearTimeout(endTimer); clearInterval(tickTimer);
    active = null;
    $("#blk-pill").hidden = true;
    document.title = BASE_TITLE;
    document.body.classList.remove("blk-on");
    paintControls();
    barTick();
  }

  // tell the server a block is running (or not), so a reminder never lands in the middle of one
  function presence(until) {
    fetch("/api/presence", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ block_until: until ? new Date(until).toISOString() : null }) }).then(function (r) { return r.text(); }).catch(function () {});
  }

  function mailReady() { return !!(DATA && DATA.reminders && DATA.reminders.mail_ready); }
  // a failed mail shows on the dashboard until dismissed, so the learner can check why
  var MAILERR_KEY = "edu.mailerr.seen";
  function paintMailAlert() {
    var e = (DATA && DATA.reminders && DATA.reminders.errors) || [];
    var last = e.length ? e[e.length - 1] : "";
    var box = $("#mail-alert");
    if (!box) return;
    if (!last || store(MAILERR_KEY) === last) { box.hidden = true; return; }
    var m = /^(\S+) mail failed: ([\s\S]*)$/.exec(last);
    var when = m ? new Date(m[1]) : null;
    $("#mail-alert-why").textContent = (when && !isNaN(when) ? when.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) + ": " : "") +
      (m ? m[2] : last) + " Run ./edu4self mail test in a terminal to try again.";
    box.hidden = false;
  }
  function dismissMailAlert() {
    var e = (DATA && DATA.reminders && DATA.reminders.errors) || [];
    if (e.length) store(MAILERR_KEY, e[e.length - 1]);
    $("#mail-alert").hidden = true;
  }

  function mailErrors() {
    var e = (DATA && DATA.reminders && DATA.reminders.errors) || [];
    return e.length ? '<p class="set-warn">' + esc(e[e.length - 1]) + "</p>" : "";
  }

  function startBlock(task) {
    var m = pick.minutes;
    if (!(m >= 1 && m <= 240)) return;
    unlockAudio();
    try { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); } catch (e) {}
    var now = Date.now();
    active = { block: pick.block, minutes: m, start: now, end: now + m * 60000, water: waterEvery(), served: 0, drunk: 0 };
    if (task) active.task = task;
    writeJSON(BLOCK_KEY, active);
    presence(active.end);
    arm();
    paintControls();
    if (isBar()) barSay("you", "start " + m + " minutes of " + esc(blockLabel(active.block)) + "." +
      (active.water ? ' <span class="bx-chk">water every ' + active.water + " min</span>" : ""));
  }

  function stopBlock() {
    if (!confirm("Stop this block? It won't count toward your die.")) return;
    writeJSON(BLOCK_KEY, null);
    presence(null);
    idle();
  }

  function finishBlock() {
    var a = active;
    if (!a) return;
    var stored = readJSON(BLOCK_KEY);
    idle();
    if (!stored || stored.start !== a.start) return; // another tab already claimed it
    writeJSON(BLOCK_KEY, null);
    presence(null);
    var list = readJSON(UNSENT_KEY) || [];
    var rec = { block: a.block, minutes: a.minutes, started: new Date(a.start).toISOString(), ts: new Date(a.end).toISOString(), task: a.task };
    if (a.water) { rec.water_served = a.served || 0; rec.water_drunk = Math.min(a.drunk || 0, rec.water_served); }
    list.push(rec);
    writeJSON(UNSENT_KEY, list);
    paintDie();
    paintToday();
    if (a.task || isBar()) render();   // the hero card drops its live clock; the bar redraws its room
    saving = flushUnsent();
    chime();
    if (!document.hasFocus()) notify(a);
    celebrateNext = a;
    if (!document.hidden) showCelebration();
  }

  function flushUnsent() {
    var list = readJSON(UNSENT_KEY) || [];
    if (flushUnsent.busy || !list.length) return Promise.resolve();
    flushUnsent.busy = true;
    var sent = 0;
    var chain = list.reduce(function (p, b) {
      return p.then(function () {
        return fetch("/api/blocks", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ block: b.block, minutes: b.minutes, started: b.started, task: b.task || undefined,
            water_served: b.water_served, water_drunk: b.water_drunk }) })
          .then(function (r) {
            // 4xx means the server will never take it, so drop it rather than retry forever
            if (!r.ok && r.status >= 500) throw new Error("server");
            writeJSON(UNSENT_KEY, (readJSON(UNSENT_KEY) || []).filter(function (x) { return x.started !== b.started; }));
            sent++;
          });
      });
    }, Promise.resolve());
    return chain.catch(function () {}).then(function () {
      var left = readJSON(UNSENT_KEY);
      if (left && !left.length) writeJSON(UNSENT_KEY, null);
      flushUnsent.busy = false;
      if (sent) return load();
    });
  }

  function resumeBlock() {
    active = readJSON(BLOCK_KEY);
    if (!active) return;
    if (!active.block || !(active.end > active.start)) { writeJSON(BLOCK_KEY, null); active = null; return; }
    if (active.water == null) { active.water = waterEvery(); active.served = 0; active.drunk = 0; }   // started before water rounds existed
    if (active.end <= Date.now()) return finishBlock();
    presence(active.end);   // the server may have restarted since the block began
    arm();
    paintControls();
    if (isBar() && DATA && !DATA.error) render();   // the room was drawn before the block came back (sign, clock strip)
  }

  // another tab started, stopped or finished a block
  window.addEventListener("storage", function (ev) {
    if (ev.key !== BLOCK_KEY) return;
    var next = readJSON(BLOCK_KEY);
    if (next) { active = next; arm(); paintControls(); } else if (active) idle();
    paintDie();
  });

  // ------------------------------------------------ reward: sound, notification, burst
  function unlockAudio() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
    } catch (e) { audio = null; }
  }

  function chime() {
    duckMusic(3500);
    unlockAudio();
    if (!audio) return;
    var master = audio.createGain(), t0 = audio.currentTime + 0.05;
    master.gain.value = 0.55;
    master.connect(audio.destination);
    function bell(freq, t, dur, vol) {
      var g = audio.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(vol, t + 0.012);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      g.connect(master);
      [[1, 1], [2.01, 0.22], [3.02, 0.08]].forEach(function (p) { // fundamental plus soft overtones, bell-like
        var o = audio.createOscillator(), og = audio.createGain();
        o.frequency.value = freq * p[0];
        og.gain.value = p[1];
        o.connect(og); og.connect(g);
        o.start(t); o.stop(t + dur + 0.05);
      });
    }
    var C = [523.25, 659.25, 783.99, 1046.5];
    C.forEach(function (f, i) { bell(f, t0 + i * 0.11, 0.9, 0.3); });               // rising arpeggio
    C.concat([1318.5]).forEach(function (f) { bell(f, t0 + 0.5, 2.8, 0.13); });       // then the chord rings out
    C.forEach(function (f, i) { bell(f * 2, t0 + 0.5 + i * 0.07, 1.2, 0.05); });     // sparkle on top
  }

  function notify(a) {
    try {
      if (!("Notification" in window) || Notification.permission !== "granted") return;
      var n = new Notification("Block done: " + a.minutes + " min of " + blockLabel(a.block), {
        body: "Your die just grew. Come back to the dashboard to see it.", tag: "edu-block", requireInteraction: true
      });
      n.onclick = function () { window.focus(); n.close(); };
    } catch (e) {}
  }

  function showCelebration() {
    var a = celebrateNext;
    celebrateNext = null;
    (saving || Promise.resolve()).then(function () {
      var list = allBlocks(), label = blockLabel(a.block);
      var key = new Date(a.start).toISOString();   // same key finishBlock stored the block under
      var before = fullTiles(tileModel(withoutBlock(list, key))), tiles = tileModel(list), after = fullTiles(tiles);
      var etched = after - before, shippedNow = Math.floor(after / DIE_TILES) > Math.floor(before / DIE_TILES);
      var last = tiles[tiles.length - 1], carry = last && last.mins < TILE_MIN ? last.mins : 0;
      $("#blk-done-chip").className = "chip";
      $("#blk-done-chip").style.setProperty("--c", blockColor(a.block));
      $("#blk-done-chip").textContent = label + " · " + a.minutes + " min";
      var dieNo = Math.floor(after / DIE_TILES), gpu = (dieNo - 1) % NODE_GPUS + 1, node = Math.floor((dieNo - 1) / NODE_GPUS) % RACK_NODES + 1;
      var nodeDone = shippedNow && gpu === NODE_GPUS;
      $("#blk-done-title").textContent = nodeDone ? "Node " + node + " online." : shippedNow ? "Die #" + dieNo + " shipped."
        : etched > 1 ? etched + " tiles etched." : etched === 1 ? "Tile etched." : "Progress etched.";
      $("#blk-done-body").textContent = (shippedNow
        ? (nodeDone ? NODE_GPUS + " GPUs, " + (NODE_GPUS * DIE_TILES * TILE_MIN / 60) + " hours of real work. A whole server, built one block at a time."
                    : DIE_TILES + " tiles, " + (DIE_TILES * TILE_MIN / 60) + " hours of real work, burned into silicon. It's GPU " + gpu + " of " + NODE_GPUS + " in node " + node + ".")
        : "That's " + (after % DIE_TILES) + " of " + DIE_TILES + " on this die.") +
        (carry ? " The next tile is " + carry + " of " + TILE_MIN + " minutes in." : "");
      $("#blk-done-die").innerHTML = dieHTML(list, key);
      openOverlay("blk-done");
      setTimeout(function () { $("#blk-done .btn").focus(); }, 60);
      burst(a.block);
    });
  }

  // New evidence (state.json history, evidence: true) gets its own moment, once per browser
  function checkProofs() {
    if (!DATA || DATA.error || celebrateNext || !$("#blk-done").hidden) return;
    var all = [];
    (DATA.state.topics || []).forEach(function (t) {
      (t.history || []).forEach(function (h) { if (h.evidence) all.push({ topic: t, h: h, key: t.id + "|" + h.date + "|" + h.title }); });
    });
    var seen = readJSON(PROOF_KEY);
    if (!seen) { writeJSON(PROOF_KEY, all.map(function (x) { return x.key; })); return; }   // first visit: old proof isn't news
    var fresh = all.filter(function (x) { return seen.indexOf(x.key) < 0; });
    if (!fresh.length) return;
    writeJSON(PROOF_KEY, seen.concat(fresh.map(function (x) { return x.key; })));
    var first = fresh[0];
    $("#blk-done-chip").className = "chip";
    $("#blk-done-chip").style.setProperty("--c", "var(--green)");
    $("#blk-done-chip").textContent = first.topic.title + " · " + first.h.date;
    $("#blk-done-title").textContent = fresh.length > 1 ? "Proved, " + fresh.length + " times." : "Proved.";
    $("#blk-done-body").textContent = first.h.title + (first.h.detail ? ". " + first.h.detail : "");
    $("#blk-done-die").innerHTML = '<ul class="proof-list">' + fresh.slice(1).map(function (x) { return "<li>" + esc(x.h.title) + "</li>"; }).join("") + "</ul>" +
      '<p class="proof-foot">This is the part that counts: not time spent, but something you can now do. It is on your evidence log for good.</p>';
    openOverlay("blk-done");
    setTimeout(function () { $("#blk-done .btn").focus(); }, 60);
    chime();
    burst("--green");
  }

  function burst(block) {
    var cv = $("#blk-burst");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !cv.getContext) return;
    var dpr = window.devicePixelRatio || 1, W = window.innerWidth, H = window.innerHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    var ctx = cv.getContext("2d");
    ctx.scale(dpr, dpr);
    var css = getComputedStyle(document.documentElement);
    var bc = BLOCKS[block] ? BLOCKS[block].color : null;
    var main = bc && /^#/.test(bc) ? bc : css.getPropertyValue(bc ? "--" + bc : block).trim();
    var colors = [main, main, main, css.getPropertyValue("--coral").trim(), css.getPropertyValue("--amber").trim(), "#ffffff"];
    var parts = [];
    for (var i = 0; i < 140; i++) {
      var ang = Math.random() * Math.PI * 2, sp = 4 + Math.random() * 9;
      parts.push({ x: W / 2, y: H / 2 - 40, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp - 4, s: 4 + Math.random() * 6,
        r: Math.random() * 6, vr: (Math.random() - .5) * .3, c: colors[i % colors.length] });
    }
    var t0 = performance.now();
    (function frame(now) {
      var t = (now - t0) / 1000;
      ctx.clearRect(0, 0, W, H);
      if (t > 2.6 || $("#blk-done").hidden) return;
      ctx.globalAlpha = Math.min(1, 2.6 - t);
      parts.forEach(function (p) {
        p.vy += 0.28; p.vx *= 0.985; p.vy *= 0.985; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c;
        ctx.fillRect(-p.s / 2, -p.s / 2, p.s, p.s); // little square tiles, like the die
        ctx.restore();
      });
      requestAnimationFrame(frame);
    })(t0);
  }

  blockEl.addEventListener("click", function (ev) {
    var el = ev.target.closest("[data-blk],[data-min],[data-blk-start],[data-blk-stop],[data-gpu],[data-water],.blk-custom");
    if (!el) return;
    if (el.dataset.gpu) { pickedDie = Number(el.dataset.gpu); paintDie(); return; }
    if (el.dataset.water) {
      store(WATER_KEY, el.dataset.water);
      blockEl.querySelectorAll("[data-water]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === el)); });
      return;
    }
    pick.touched = true;
    if (el.dataset.blk) {
      pick.block = el.dataset.blk;
      var preset = BLOCKS[pick.block].minutes;
      if (preset) { pick.minutes = preset; blockEl.querySelector("[data-custom]").value = PRESETS.indexOf(preset) < 0 ? preset : ""; }
      paintPick();
    }
    else if (el.dataset.min) { pick.minutes = Number(el.dataset.min); blockEl.querySelector("[data-custom]").value = ""; paintPick(); }
    else if (el.hasAttribute("data-blk-start")) startBlock();
    else if (el.hasAttribute("data-blk-stop")) stopBlock();
    else if (el.classList.contains("blk-custom")) {
      var inp = el.querySelector("input");
      if (inp.value) { pick.minutes = Number(inp.value); paintPick(); }
    }
  });
  blockEl.addEventListener("input", function (ev) {
    if (!ev.target.hasAttribute("data-custom")) return;
    pick.touched = true;
    var v = ev.target.value;
    pick.minutes = v === "" ? 50 : Math.round(Number(v));
    paintPick();
  });
  blockEl.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && ev.target.hasAttribute("data-custom")) startBlock();
  });
  // browsers only allow sound after a click on the page; after a reload, any click re-arms the chime
  document.addEventListener("pointerdown", function () { if (active) unlockAudio(); });
  $("#blk-pill").addEventListener("click", function (ev) {
    ev.preventDefault();
    if (isBar() && barRoom() === "back") { store(ROOM_KEY, "front"); render(); }
    blockEl.scrollIntoView({ behavior: "smooth", block: "center" });
  });


  // ---------------------------------------------------------------- water rounds
  // While a block runs, a glass arrives every N minutes (15, 30 or off, picked before the start).
  // The count lives on the running block, so it survives reloads and is saved with the block.
  var WATER_KEY = "edu.water.v1";
  var WATER_LINES = [
    "Drink it. Your neurons are mostly water. Probably.",
    "Even an H100 needs coolant. So do you.",
    "One sip. Then straight back to it.",
    "Thirsty brains guess more and remember less. Water is cheaper than a retry."
  ];
  // this browser's last pick, else the default from Settings
  function waterEvery() {
    var v = store(WATER_KEY);
    if (v == null) v = String((cfg().water && cfg().water.every != null) ? cfg().water.every : 15);
    return v === "0" ? 0 : v === "30" ? 30 : 15;
  }

  function clink() {
    duckMusic(1500);
    unlockAudio();
    if (!audio) return;
    [1568, 2093].forEach(function (f, n) {   // two soft sine pings, like a glass set down
      var o = audio.createOscillator(), g = audio.createGain(), t = audio.currentTime + 0.03 + n * 0.09;
      o.type = "sine"; o.frequency.value = f; o.connect(g); g.connect(audio.destination);
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.22, t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
      o.start(t); o.stop(t + 0.75);
    });
  }

  // Glass k arrives at k * interval minutes, never at or after the block's end
  function waterCheck() {
    if (!active || !active.water) return;
    var step = active.water * 60000;
    var due = Math.min(Math.floor((Date.now() - active.start) / step), Math.floor((active.end - active.start - 1) / step));
    if (due <= (active.served || 0)) return;
    var stored = readJSON(BLOCK_KEY);
    if (stored && stored.start === active.start && (stored.served || 0) >= due) { active = stored; return paintWater(); }  // another tab served it
    active.served = due;
    writeJSON(BLOCK_KEY, active);
    serveWater();
  }

  function serveWater() {
    var mins = Math.round((Date.now() - active.start) / 60000);
    clink();
    try {
      if (!document.hasFocus() && "Notification" in window && Notification.permission === "granted") {
        var n = new Notification("💧 Water. " + mins + " minutes in.", { body: "A glass just landed on the bar. Take a sip; the timer keeps running.", tag: "edu-water" });
        n.onclick = function () { window.focus(); n.close(); };
      }
    } catch (e) {}
    paintWater();
    if (isBar()) {
      barSay("bartender", "slides a glass of water down the bar. <span class=\"bx-chk\">" + mins + " min in · click the glass once you've drunk it</span>", true);
      setTimeout(function () { barSay("physical", esc(WATER_LINES[((active && active.served) || 1) % WATER_LINES.length])); }, 900);
    } else {
      toast('<span>💧</span><span><b>Water.</b> ' + mins + ' minutes in. Take a sip, then back to it. <button class="btn btn-soft btn-sm" type="button" data-drink>Drank it</button></span>', 12000);
    }
  }

  function drinkWater() {
    if (!active || (active.served || 0) <= (active.drunk || 0)) return;
    active.drunk = (active.drunk || 0) + 1;
    writeJSON(BLOCK_KEY, active);
    $("#toast").hidden = true;
    paintWater();
    if (isBar()) barSay("you", ["drink it. Cold.", "drink it. Better.", "drink it, and get back to it."][(active.drunk - 1) % 3]);
  }

  function waterText() {
    if (!active) return "";
    if (!active.water) return "💧 Water rounds are off for this block.";
    var served = active.served || 0, drunk = active.drunk || 0, nextAt = active.start + (served + 1) * active.water * 60000;
    return "💧 " + (served > drunk ? "A glass is waiting. " : "") +
      (nextAt < active.end ? "Next glass in " + clock(nextAt - Date.now()) : "No more glasses this block") +
      (served ? " · " + drunk + " of " + served + " drunk" : "");
  }

  function paintWater() {
    var owed = active && (active.served || 0) > (active.drunk || 0);
    document.querySelectorAll("[data-water-text]").forEach(function (el) { el.textContent = waterText(); });
    blockEl.querySelectorAll("[data-drink]").forEach(function (b) { b.hidden = !owed; });
    var g = $(".bx-glass");
    if (g) {
      g.classList.toggle("full", !!owed);
      if (owed && Date.now() - glassServedAt < 1500 && !g.classList.contains("serve")) g.classList.add("serve");
    }
    var bar = $("[data-bx-wbar]");
    if (bar && active && active.water) bar.style.width = (100 * ((Date.now() - active.start) % (active.water * 60000)) / (active.water * 60000)).toFixed(1) + "%";
  }

  // ---------------------------------------------------------------- rooms (themes)
  // The room view is drawn from a theme: app/dashboard/themes/<id>/ or <vault>/themes/<id>/. The server
  // checks and cleans it (app/themes.py); here its layout gets its slots filled, its CSS is added, and
  // its palette, fonts and words are applied. A theme that fails its check falls back to the bar.
  var THEME = null, THEME_WANT = null, THEME_ERR = null;
  var FONT = { sans: "var(--sans)", serif: '"Bar Baskerville", Georgia, serif', mono: '"Bar Plex", ui-monospace, Menlo, monospace',
    head: '"Bar Oswald", "Avenir Next Condensed", sans-serif', neon: '"Bar Neon", "Bar Oswald", sans-serif' };
  var PALETTE_VARS = { bg: "--bg", bg2: "--bg-2", surface: "--surface", surface2: "--surface-2", ink: "--ink", ink2: "--ink-2",
    muted: "--muted", line: "--line", line2: "--line-2", accent: "--bar-amber", accent2: "--bar-cream", accent_ink: "--accent-ink" };
  function wantTheme() { return THEME_WANT || cfg().theme || "bar"; }
  function W(k) { return (THEME && THEME.meta.words[k]) || k; }
  function LINE(k, text) { return (THEME && THEME.meta.lines && THEME.meta.lines[k]) || text; }
  var themeLoading = null;
  function fetchTheme(id) {
    return fetch("/api/theme?id=" + encodeURIComponent(id), { cache: "no-store" }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) { var e = new Error(j.error || "theme failed"); e.errors = j.errors || []; throw e; } return j; });
    });
  }
  function ensureTheme() {
    var id = wantTheme();
    if (themeLoading === id) return;
    themeLoading = id;
    fetchTheme(id).catch(function (e) {
      THEME_ERR = { id: id, errors: e.errors && e.errors.length ? e.errors : [e.message] };
      return id === "bar" ? null : fetchTheme("bar");
    }).then(function (t) {
      themeLoading = null;
      if (!t) return;
      if (t.meta.id === id) THEME_ERR = null;
      applyTheme(t);
      if (t.meta.id !== id) THEME_WANT = t.meta.id;   // fell back: stop asking for the broken one
      if (DATA) render();
    });
  }
  function applyTheme(t) {
    THEME = t;
    var css = $("#theme-css"), vars = $("#theme-vars");
    if (!css) { css = document.createElement("style"); css.id = "theme-css"; document.head.appendChild(css); }
    if (!vars) { vars = document.createElement("style"); vars.id = "theme-vars"; document.head.appendChild(vars); }
    css.textContent = t.css;
    var m = t.meta, p = m.palette || {}, f = m.fonts || {}, decl = [];
    Object.keys(p).forEach(function (k) { if (PALETTE_VARS[k]) decl.push(PALETTE_VARS[k] + ":" + p[k]); });
    if (f.head) decl.push("--bx-head:" + FONT[f.head]);
    if (f.body) decl.push("--serif:" + FONT[f.body]);
    if (f.sign) decl.push("--bx-sign:" + FONT[f.sign]);
    decl.push("color-scheme:" + (m.dark === false ? "light" : "dark"));
    // the bar's kind colours are bright for a dark room; a light room gets the classic view's deeper ones
    if (m.dark === false) decl.push("--lesson:#5b5bd6;--probe:#b0650a;--checkpoint:#d6336c;--reading:#0e7f6c;--project:#8e4ec6;--mock:#0b6fb8");
    if (m.backdrop) decl.push("background:" + m.backdrop);
    vars.textContent = "body.v-bar{" + decl.join(";") + "}";
    document.body.dataset.theme = m.id;
    applyConfig();
  }

  // ---------------------------------------------------------------- bar view
  // A second way to draw the same data: a room where your skills talk. Classic stays as it was.
  var VIEW_KEY = "edu.view.v1", ROOM_KEY = "edu.bar.room.v1", NAME_KEY = "edu.bar.name.v1";
  var BAR_NAMES = [   // Settings → The bar → Names
    ["Cache Miss", "nobody remembers your name"],
    ["The Last Token", "last call, every step"],
    ["Bad Tokens", "loud, wrong, and proud of it"],
    ["Exploding Gradients", "no ceiling, no mercy"],
    ["Dead Neurons", "switched off since forever"]
  ];
  // The ids are part of the state.json contract (coach.voices); names and colours can be changed in Settings.
  var VOICE_DEFAULTS = {
    bartender:    { name: "The bartender", c: "#ffe9cf" },
    logic:        { name: "Logic",         c: "#85b8ff" },
    volition:     { name: "Willpower",     c: "#cfa6ff" },
    gpu:          { name: "GPU whisperer", c: "#ff9090" },
    encyclopedia: { name: "The archivist", c: "#f5d06f" },
    physical:     { name: "The body",      c: "#ffa36b" },
    nostalgia:    { name: "Nostalgia",     c: "#8fe0cf" },
    critic:       { name: "The critic",    c: "#ff8fbf" },
    regular:      { name: "The regular",   c: "#c8b6ff" },
    jukebox:      { name: "The jukebox",   c: "#7fe3ff" },
    you:          { name: "You",           c: "#9fe0a4" }
  };
  var VOICES = {};
  Object.keys(VOICE_DEFAULTS).forEach(function (k) { VOICES[k] = { name: VOICE_DEFAULTS[k].name, c: VOICE_DEFAULTS[k].c }; });
  var NUM_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "twenty-one", "twenty-two", "twenty-three", "twenty-four"];
  var barSeen = {}, barExtra = [], glassServedAt = 0, barXid = 0;

  // this browser's choice, else the default view from Settings
  function isBar() { var v = store(VIEW_KEY); return v ? v !== "classic" : cfg().view !== "classic"; }
  function barRoom() { return store(ROOM_KEY) === "back" ? "back" : "front"; }
  function barName() { return BAR_NAMES[(Number(store(NAME_KEY)) || 0) % BAR_NAMES.length]; }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function tonight() {
    var today = dayKey(new Date()), monday = weekStart(), mins = 0, days = {}, glasses = 0;
    allBlocks().forEach(function (b) {
      var d = new Date(b.ts || b.started), k = dayKey(d);
      if (k === today) { mins += b.minutes; glasses += b.water_drunk || 0; }
      if (d >= monday) days[k] = true;
    });
    if (active) glasses += active.drunk || 0;
    return { mins: mins, days: days, hit: Object.keys(days).length, glasses: glasses, monday: monday, today: today };
  }

  function dieNow() {
    var full = fullTiles(tileModel(allBlocks())), shipped = Math.floor(full / DIE_TILES);
    return { n: shipped + 1, etched: full - shipped * DIE_TILES, shipped: shipped };
  }

  function tonightHTML() {
    var t = tonight(), pips = "";
    for (var i = 0; i < DAY_GOAL_MIN / 20; i++) pips += '<i class="' + (t.mins >= (i + 1) * 20 ? "on" : t.mins > i * 20 ? "half" : "") + '"></i>';
    return '<div class="bx-k">' + esc(W("tonight")) + '</div><div class="bx-pips h">' + pips + '</div>' +
      '<div class="bx-mono">' + t.mins + " of " + DAY_GOAL_MIN + " min" + (t.mins >= DAY_GOAL_MIN ? " ✓" : "") + "</div>";
  }
  function weekHTML() {
    var t = tonight(), week = "";
    for (var j = 0; j < 7; j++) {
      var d = new Date(t.monday); d.setDate(t.monday.getDate() + j);
      var k = dayKey(d);
      week += '<i class="' + (t.days[k] ? "on" : "") + (k === t.today ? " is-today" : "") + '" title="' + k + '">' + "MTWTFSS"[j] + "</i>";
    }
    return '<div class="bx-k">' + esc(W("week")) + '</div><div class="bx-pips m">' + week + '</div>' +
      '<div class="bx-mono">' + t.hit + " of " + WEEK_GOAL_DAYS + " " + esc(W("nights")) + (t.hit >= WEEK_GOAL_DAYS ? " · week won" : "") + "</div>";
  }

  function cabinetHTML() {
    var d = dieNow();
    return '<div class="bx-k">' + esc(W("die_case")) + " · " + esc(W("die")) + " #" + d.n + '</div>' +
      '<div class="bx-cab-row"><b class="bx-num">' + d.etched + "<small> / " + DIE_TILES + "</small></b>" + dieHTML(allBlocks(), false) + "</div>" +
      '<div class="bx-mono">' + d.etched + " of " + DIE_TILES + " · a slot per " + TILE_MIN + " min · " + d.shipped + " " + esc(W(d.shipped === 1 ? "die" : "dies")) + " " + esc(W("shipped")) + "</div>";
  }

  function glassHTML() {
    var owed = active && (active.served || 0) > (active.drunk || 0);
    return '<button class="bx-glass' + (owed ? " full" : "") + '" type="button" data-drink aria-label="' + (owed ? "A " + esc(W("glass")) + " of water. Click once you've drunk it." : "An empty " + esc(W("glass"))) + '"></button>';
  }

  // A past proof, a different one each day, from more than three days ago
  function pastProof() {
    var cut = dayKey(new Date(Date.now() - 3 * 864e5)), all = [];
    (DATA.state.topics || []).forEach(function (t) { (t.history || []).forEach(function (h) { if (h.evidence && h.date <= cut) all.push(h); }); });
    if (!all.length) return "";
    var day = Math.floor(Date.now() / 864e5), h = all[day % all.length];
    var tail = ["You've done harder things than tonight.", "Same brain. More practice since.", "That was proof, not luck."][day % 3];
    return shortDate(new Date(h.date + "T12:00:00")) + ": " + h.title + ". " + tail;
  }

  // What your blocks say about tonight: per-day minutes, streak, record, last stop, time on the hero task
  function blockStats(hero) {
    var byDay = {}, today = dayKey(new Date()), total = 0, types = {}, heroMins = 0, lastEnd = 0, first = null;
    allBlocks().forEach(function (b) {
      var end = new Date(b.ts || b.started), k = dayKey(end);
      byDay[k] = (byDay[k] || 0) + b.minutes;
      total += b.minutes;
      if (k === today) types[b.block] = (types[b.block] || 0) + b.minutes;
      if (hero && b.task === hero.task.id) heroMins += b.minutes;
      lastEnd = Math.max(lastEnd, end.getTime());
      if (!first || b.started < first) first = b.started;
    });
    var streak = 0, d = new Date();
    if (!byDay[today]) d.setDate(d.getDate() - 1);
    while (byDay[dayKey(d)]) { streak++; d.setDate(d.getDate() - 1); }
    var best = 0;
    Object.keys(byDay).forEach(function (k) { if (k !== today) best = Math.max(best, byDay[k]); });
    return { todayMins: byDay[today] || 0, best: best, streak: streak, total: total, types: types, heroMins: heroMins, lastEnd: lastEnd, first: first };
  }

  function daysSince(dateStr) { return Math.floor((Date.now() - new Date(dateStr + (dateStr.length === 10 ? "T12:00:00" : "")).getTime()) / 864e5); }

  // Lines that only make sense right now. Each is [priority, voice, text, id]; the top few are shown.
  function occasionLines(hero, S, t, d) {
    var O = [], now = new Date(), hr = now.getHours(), wd = now.getDay(), md = String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0");
    function add(p, v, text, id) { O.push([p, v, text, id]); }
    // a trophy won today: the host says so, in the room's words
    var ksl = (THEME && THEME.meta.keepsakes && THEME.meta.keepsakes.lines) || {}, todayKey = dayKey(now);
    (ksData().items || []).forEach(function (it) {
      if (it.backfill || dayKey(new Date(it.ts)) !== todayKey) return;
      if (ksl[it.kind]) add(it.kind === "day" ? 84 : 94, "bartender", ksl[it.kind], "ks-" + it.id);
      if (/^gifts\//.test(it.gift || "") && ksl.gift) add(95, "bartender", ksl.gift, "ksg-" + it.id);
    });
    if (active) {
      var el = (Date.now() - active.start) / 60000, left = (active.end - Date.now()) / 60000;
      if (el < 3) add(90, "volition", "Clock's running. The first five minutes are the hardest, and you're in them.", "a-start");
      else if (left < 5) add(92, "volition", "Under five minutes left. Don't touch your phone now. You've come this far.", "a-end");
      else if (el / active.minutes >= 0.45 && el / active.minutes < 0.6) add(88, "logic", "Halfway. About " + Math.round(left) + " minutes to go.", "a-half");
      if (active.block === "play") add(80, "regular", LINE("play", "A play block. The regular at the end of the bar raises his glass. Fun is on the schedule too."), "a-play");
      if (active.block === "practice") add(80, "encyclopedia", "Practice hour. Brute force first, then make it good. Nobody gets it clean on the first try.", "a-practice");
      if (Math.floor((S.total + active.minutes) / (DIE_TILES * TILE_MIN)) > Math.floor(S.total / (DIE_TILES * TILE_MIN)))
        add(86, "gpu", "Finish this block and die #" + d.n + " ships. Don't stop early.", "a-ship");
      var owedFor = active.water && (active.served || 0) > (active.drunk || 0) ? el - (active.served || 0) * active.water : 0;
      if (owedFor > 5) add(91, "physical", "There's still a " + W("glass") + " on " + W("counter") + ". It's getting warm.", "a-warm");
    } else if (S.lastEnd && Date.now() - S.lastEnd < 20 * 60000) {
      add(65, "gpu", "You stopped " + Math.max(1, Math.round((Date.now() - S.lastEnd) / 60000)) + " minutes ago. The die is still warm. Another 25?", "warm-die");
    }
    if (S.best && S.todayMins > S.best) add(85, "volition", "New record: " + hm(S.todayMins) + " in one day. The old best was " + hm(S.best) + ".", "record");
    var dates = {
      "10-31": ["regular", LINE("halloween", "Halloween. Someone came dressed as a KV cache. Twice the size anyone expected.")],
      "12-31": ["bartender", LINE("nye", "Last night of the year. Close the die, not just the year.")],
      "01-01": ["bartender", LINE("newyear", "New year. Same bar. The die doesn't reset.")],
      "02-14": ["regular", LINE("valentine", "Valentine's Day. The regular says attention is all you need. He's been single since 2017.")]
    };
    if (dates[md]) add(80, dates[md][0], dates[md][1], "date");
    else if (now.getDate() === 1) add(60, "encyclopedia", "First of the month. Whatever last month was, this one has a blank page.", "month");
    actionableTasks().forEach(function (e) {
      var p = pendingFor(e.task.id);
      var days = p ? Math.floor((Date.now() - new Date(p.ts).getTime()) / 864e5) : 0;
      if (days >= 1) add(75, "bartender", (e.task.label || e.task.title) + " has been on " + W("counter") + " for " + plural(days, "day") + (claudeOK() ? ". Grade it. I'm starting to take it personally." : '. Say "check my inbox". I\'m starting to take it personally.'), "pend-" + e.task.id);
    });
    if (S.streak >= 7) add(72, "volition", S.streak + " days in a row. A full week without missing. That's not motivation anymore, that's a habit.", "streak");
    else if (S.streak >= 2) add(70, "volition", S.streak + " days in a row with a block. Don't look down.", "streak");
    if (t.glasses >= 4) add(60, "physical", t.glasses + " " + W("glasses") + " tonight. You're better cooled than most GPUs in prod.", "glasses");
    if (S.todayMins >= 240) add(55, "physical", hm(S.todayMins) + " today. Stand up, roll your shoulders, look at something farther away than the screen.", "heavy");
    if (hr >= 20 && S.todayMins && Object.keys(S.types).every(function (k) { return FUN_BLOCKS[k]; }))
      add(52, "critic", "Today was all " + Object.keys(S.types).map(blockLabel).join(" and ") + ". Fair. One lesson block would make the die a little prouder.", "only-fun");
    var tod = hr >= 5 && hr < 9 ? ["volition", "Before nine and already here. The day hasn't had a chance to get in the way."]
      : hr < 12 && hr >= 9 ? ["logic", "Morning brain. Best hours of the day for new material, worst hours for scrolling."]
      : hr >= 12 && hr < 14 ? ["physical", "Lunch hour. Eat something that isn't caffeine."]
      : hr >= 14 && hr < 17 ? ["physical", "Afternoon slump hours. Twenty-five minutes of focus beats them better than coffee does."]
      : hr >= 17 && hr < 21 ? ["regular", LINE("evening", "Evening. The bar fills up around now. Nobody else here brought homework.")]
      : hr >= 21 ? ["volition", "The good hours. Everyone else is scrolling."]
      : hr < 2 ? ["physical", "Past midnight. The die doesn't care what time it is. Your memory does: sleep is when it saves."]
      : ["critic", "It's " + hhmm(Date.now()) + ". One block and bed, or just bed. Not scrolling."];
    add(50, tod[0], tod[1], "tod");
    if (wd === 1 && t.hit <= 1) add(45, "encyclopedia", "Monday. The week is a blank die. Etch the first tile.", "monday");
    if (wd === 5 && hr >= 18) add(46, "regular", LINE("friday", "Friday night, and you're at a bar studying. The regulars respect it. Quietly."), "friday");
    if ((wd === 6 || wd === 0) && hr < 18) add(44, "regular", "Weekend. Nobody is grading speed today.", "weekend");
    if (wd === 0 && hr >= 12 && t.hit < WEEK_GOAL_DAYS) add(73, "volition", "Sunday. " + t.hit + " of " + WEEK_GOAL_DAYS + " nights. The week closes at midnight.", "sunday");
    var proofs = [];
    (DATA.state.topics || []).forEach(function (tp) { (tp.history || []).forEach(function (h) { if (h.evidence) proofs.push(h.date); }); });
    proofs.sort();
    var lastProof = proofs.length ? daysSince(proofs[proofs.length - 1]) : null;
    if (lastProof !== null && lastProof <= 1) add(40, "nostalgia", "Proof landed " + (lastProof ? "yesterday" : "today") + ". Ride it.", "proof-new");
    else if (lastProof !== null && lastProof > 14) add(35, "critic", lastProof + " days since the last proof. The next submit fixes that.", "proof-old");
    var graded = DATA.state.updated ? daysSince(DATA.state.updated.slice(0, 10)) : 0;
    if (graded > 7) add(30, "bartender", LINE("silent", "I haven't graded anything in {days} days. Not mad. Just polishing glasses.").replace("{days}", graded), "silent");
    if (hero && S.heroMins >= 100) add(42, "logic", "You've put " + hm(S.heroMins) + " into " + (hero.task.label || hero.task.title) + " so far. It's going in, even when it doesn't feel like it.", "hero-time");
    if (hero && hero.task.kind === "probe") add(41, "logic", 'It\'s a probe: it measures, it doesn\'t judge. "I don\'t know" is a real answer.', "probe");
    if (music && !music.paused && music.currentTime > 3600) add(25, "jukebox", (musicTitle() || "This track") + ", " + Math.floor(music.currentTime / 3600) + " h " + Math.floor(music.currentTime % 3600 / 60) + " min in. You've been in it longer than some people stay at jobs.", "music");
    else if (music && music.paused && musicPrefs().on === false) add(24, "jukebox", LINE("music_quiet", "The jukebox is quiet. Press play, or enjoy the silence like a monk."), "music");
    else if (!musicPlayable() && hr >= 18) add(23, "jukebox", LINE("music_none", "No tape in the jukebox.") + " Settings → Music has a soundscape, radio, or your own file.", "music");
    if (S.total >= 600) add(20, "encyclopedia", hm(S.total) + " of focus logged since " + shortDate(new Date(S.first)) + ".", "lifetime");
    return O.sort(function (a, b) { return b[0] - a[0]; });
  }

  // Every line comes from real data or from Claude's notes. [voice, html, small print, id]
  function barLines(hero) {
    var st = DATA.state, L = [], t = tonight(), d = dieNow(), away = idleDays(), hr = new Date().getHours(), coach = st.coach, S = blockStats(hero);
    if (coach) L.push(["bartender", '<b>"' + esc(coach.headline) + '"</b>', coach.date, "coach", esc(coach.body || "")]);
    ((coach && coach.voices) || []).forEach(function (v, i) { if (VOICES[v.voice]) L.push([v.voice, esc(v.text), "from Claude", "claude-" + i]); });

    // No lines that only restate what the room already shows: tonight's minutes and the week's nights
    // (the tonight and week slots), the next task (the job card, which also says when it's submitted),
    // the die's count (the die slot), and the finish line and the other open tasks (the finish slot and
    // the replies). Coming back after a gap is advice, not a number, so it stays.
    if (away >= IDLE_DAYS) L.push(["volition", esc("You've been away " + away + " days. No catching up. One 25-minute block, then see how it feels."), null, "vol"]);

    var shown = {};
    occasionLines(hero, S, t, d).forEach(function (o) {
      if (Object.keys(shown).length >= 3 || shown[o[3]]) return;
      shown[o[3]] = true;
      L.push([o[1], esc(o[2]), null, "o-" + o[3]]);
    });

    if (active && active.water) L.push(["physical", '<span data-water-text>' + esc(waterText()) + "</span>", null, "water"]);
    else if (t.glasses && t.glasses < 4) L.push(["physical", t.glasses + " " + W(t.glasses === 1 ? "glass" : "glasses") + " of water tonight. Your neurons noticed.", null, "water"]);

    var past = pastProof();
    if (past) L.push(["nostalgia", esc(past), null, "nostalgia"]);
    var pool = (cfg().bar && cfg().bar.gags === false ? [] : (THEME && THEME.meta.gags) || []).concat(((cfg().bar && cfg().bar.lines) || []).map(function (l) { return [l.voice, l.text]; }));
    if (pool.length) {
      var fi = Math.floor(Date.now() / (40 * 60000)) % pool.length;
      if (VOICES[pool[fi][0]]) L.push([pool[fi][0], esc(pool[fi][1]), null, "flavor-" + fi + "-" + pool.length]);
    }
    // Each character speaks once: the first line wins, so Claude's note and voices beat the room's own chatter.
    // Lines from what you just did (barExtra: a block started, water served) are short-lived and stay.
    var spoke = {};
    L = L.filter(function (l) { if (spoke[l[0]]) return false; spoke[l[0]] = true; return true; });
    return L.concat(barExtra);
  }

  // Transient lines (water, drinks, starts). Kept in memory, last four only.
  function barSay(voice, html, keep) {
    barExtra.push([voice, html, null, "x" + (++barXid)]);
    if (barExtra.length > 4) barExtra.shift();
    if (voice === "bartender" && keep) glassServedAt = Date.now();
    if (isBar() && DATA && !DATA.error && barRoom() === "front") render();
  }

  function barJob(hero) {
    if (!hero) return '<div class="bx-job is-empty"><div class="bx-k">' + esc(W("job")) + '</div><h2>Nothing waiting on you.</h2><p>' +
      (claudeOK() ? (pendingCount() ? gradeButton() : '<button class="btn btn-topic btn-sm" type="button" data-newtopic>+ Start a new topic</button>')
        : 'Tell Claude <b>"check my inbox"</b> to get your work graded and the next step lined up.') + "</p></div>";
    var t = hero.task, meta = kindMeta(t.kind), pend = pendingFor(t.id);
    return '<div class="bx-job" style="--c:var(--' + (KIND[t.kind] ? t.kind : "lesson") + ')">' +
      '<div class="bx-k">' + esc(W("job")) + " · " + esc(meta.label) + " · " + esc(hero.topic.title) + "</div>" +
      "<h2>" + (t.label ? '<span class="bx-label">' + esc(t.label) + "</span>" : "") + esc(t.title) + "</h2>" +
      (t.why ? "<p>" + esc(t.why) + "</p>" : "") +
      '<div class="bx-meta">' + (t.effort ? "<span>◷ " + esc(t.effort) + "</span>" : "") +
        (t.kind === "probe" ? "<span>◎ Measures what you know. Nothing to study first.</span>" : "") +
        (t.kind === "lesson" ? "<span>✦ Ends with exercises</span>" : "") + "</div>" +
      (t.rules ? '<div class="bx-rules">⚑ <b>Rules:</b> ' + esc(t.rules) + "</div>" : "") +
      (pend ? '<div class="bx-sent">Submitted ' + esc(ago(pend.ts)) + "." + (claudeOK() ? " " + gradeButton() : ' In Claude Code, say <b>"check my inbox"</b> to get it graded.') + "</div>" : stuckNudge(t, true)) +
      "</div>";
  }

  function barReplies(hero) {
    var R = [], n = 0;
    function act(html) { n++; R.push('<li><b class="bx-n">' + n + ".</b>" + html.replace(/^<(a|button) /, '<$1 data-n="' + n + '" ') + "</li>"); }
    function quiet(html) { R.push('<li class="is-quiet"><b class="bx-n">–</b><span>' + html + "</span></li>"); }
    function chk(s) { return ' <span class="bx-chk">' + s + "</span>"; }
    if (hero) {
      var t = hero.task, meta = kindMeta(t.kind), pend = pendingFor(t.id);
      if (t.href) { var href = resolveHref(t.href); act('<a class="bx-r" href="' + esc(href) + '"' + openTarget(href) + ">[" + esc(meta.open) + (/^obsidian:/.test(href) ? " in Obsidian" : "") + ".] ↗</a>"); }
      if (pend) act('<button class="bx-r" type="button" data-withdraw="' + esc(pend.id) + '">[Withdraw the submission.]' + chk("only before Claude grades it") + "</button>");
      else {
        if (t.submit) act('<button class="bx-r" type="button" data-submit="' + esc(t.id) + '">[' + esc(meta.submit) + ".]</button>");
        if (t.exercise) act('<button class="bx-r" type="button" data-hints="' + esc(t.id) + '">[Ask for a hint.]' + chk("each one is noted for Claude") + "</button>");
        if (!active) act('<button class="bx-r" type="button" data-start-task="' + esc(t.id) + '">[Start ' + taskMinutes(hero.topic) + " min on this.]" + chk(esc(BLOCKS[taskBlock(hero.topic)].label) + " block") + "</button>");
        else if (active.task === t.id) quiet("The clock is running on this one.");
      }
    }
    actionableTasks().forEach(function (e) {
      var x = e.task;
      if (x.status !== "todo" || (hero && x.id === hero.task.id)) return;
      var m = kindMeta(x.kind), name = x.label || x.title;
      if (pendingFor(x.id)) return quiet(esc(name) + chk("submitted, waiting for Claude"));
      if (x.href) { var h2 = resolveHref(x.href); act('<a class="bx-r" href="' + esc(h2) + '"' + openTarget(h2) + ">[" + esc(name) + ": " + esc(x.title) + ".] ↗</a>"); }
      if (x.submit) act('<button class="bx-r" type="button" data-submit="' + esc(x.id) + '">[' + esc(m.submit) + ": " + esc(name) + ".]</button>");
    });
    if (claudeOK()) act('<button class="bx-r" type="button" data-claude-open>"' + esc(W("note")) + '"' + chk("talk to Claude") + "</button>");
    else act('<button class="bx-r" type="button" data-note>"' + esc(W("note")) + '"' + chk("it goes to Claude") + "</button>");
    act('<button class="bx-r" type="button" data-help="all">"' + esc(W("how")) + '"</button>');
    act('<button class="bx-r" type="button" data-room="back">"' + esc(W("back_q")) + '"' + chk("milestones, proof, skills, library, your cluster") + "</button>");
    return R.join("");
  }

  // Each line folds to one line (the host's note: its headline and two lines of the rest) so the job
  // stays near the top. A folded line opens in place on a click, a tap or Enter; markFolds() decides
  // which ones are actually cut off, after the room is drawn.
  function barLines2HTML(hero) {
    var k = 0;
    return barLines(hero).map(function (l) {
      var v = VOICES[l[0]], key = l[3] || l[0] + "|" + l[1], fresh = !barSeen[key];
      barSeen[key] = true;
      var chk = l[2] ? ' <span class="bx-chk">' + esc(l[2]) + "</span>" : "", who = '<span class="bx-who">' + esc(v.name) + "</span>";
      var inner = l[4] != null ? who + l[1] + '<span class="fold fold-2">' + l[4] + chk + '</span><button class="fold-more" type="button" aria-expanded="false" hidden>more</button>'
        : '<span class="fold">' + who + l[1] + chk + "</span>";
      return '<p class="bx-line' + (fresh ? " is-new" : "") + (foldOpen[key] ? " is-open" : "") + '" data-fold="' + esc(key) + '" style="--vc:' + v.c + (fresh ? ";--i:" + (k++) : "") + '" data-ini="' + v.name.replace(/^The /, "").charAt(0).toUpperCase() + '">' +
        inner + "</p>";
    }).join("");
  }

  var foldOpen = {};
  function markFolds() {
    document.querySelectorAll("[data-fold]").forEach(function (box) {
      var f = box.querySelector(".fold"), more = box.querySelector(".fold-more");
      if (!f) return;
      var open = box.classList.contains("is-open"), cut = open || f.scrollHeight > f.clientHeight + 1;
      box.toggleAttribute("data-clip", cut);
      if (more) { more.hidden = !cut; more.textContent = open ? "less" : "more"; more.setAttribute("aria-expanded", String(open)); return; }
      if (cut) { box.tabIndex = 0; box.setAttribute("role", "button"); box.setAttribute("aria-expanded", String(open)); }
      else { box.removeAttribute("tabindex"); box.removeAttribute("role"); box.removeAttribute("aria-expanded"); }
    });
  }
  function toggleFold(box) {
    var open = box.classList.toggle("is-open"), more = box.querySelector(".fold-more");
    foldOpen[box.dataset.fold] = open;
    if (more) { more.textContent = open ? "less" : "more"; more.setAttribute("aria-expanded", String(open)); }
    else box.setAttribute("aria-expanded", String(open));
  }
  document.addEventListener("click", function (ev) {
    var box = ev.target.closest("[data-fold][data-clip]");
    if (!box || (ev.target.closest("a, button, input") && !ev.target.closest(".fold-more")) || String(getSelection()).length) return;
    toggleFold(box);
  });
  document.addEventListener("keydown", function (ev) {
    if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches && ev.target.matches('[data-fold][data-clip][role="button"]')) { ev.preventDefault(); toggleFold(ev.target); }
  });
  var foldTimer;
  window.addEventListener("resize", function () { clearTimeout(foldTimer); foldTimer = setTimeout(markFolds, 150); });
  if (document.fonts) document.fonts.addEventListener("loadingdone", function () { markFolds(); });   // a room's fonts move the line breaks

  // ---------------------------------------------------------------- the shelf (trophies)
  // The server awards trophies (app/keepsakes.py) and keeps each one's drawing from the room it was won
  // in, so a shelf can hold bottle caps from the bar next to books from the library. Day trophies stack
  // into real piles of ten; weeks and dice stand in a row, each with a printable card and maybe a gift.
  var KS_SEEN = "edu.keepsakes.seen.v1", KS_PILE = 10;
  function ksData() { return (DATA && DATA.keepsakes) || { items: [], art: {} }; }
  function ksLook(kind) { return (THEME && THEME.meta.keepsakes && THEME.meta.keepsakes[kind]) || { name: kind, plural: kind + "s" }; }
  function ksBox(art) {
    var m = /viewbox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(art || "");
    return m && +m[1] > 0 ? { w: +m[1], h: +m[2] } : { w: 1, h: 1 };
  }
  function ksSeen() { try { return JSON.parse(store(KS_SEEN) || "null"); } catch (e) { return null; } }
  function ksWhen(it) {
    var d = new Date(it.date + "T12:00:00");
    return it.kind === "day" ? d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }) + (it.minutes ? " · " + it.minutes + " min" : "")
      : it.kind === "week" ? "week of " + d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "#" + it.n + " · " + d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }
  // one pile of trophies: up to ten copies of the same drawing, placed by the room's stack style. Days
  // and dice both pile up; a die in the pile is also the link to its printable card.
  function ksPile(group, art, isNew) {
    var stack = group[0].stack, box = ksBox(art), n = group.length;
    if (stack === "pile" && box.h > box.w * 1.1) stack = "row";   // a tall thing can't pile straight up; it stands
    var W = stack === "fan" ? 34 : stack === "heap" ? 26 : stack === "row" ? Math.min(40, 50 * box.w / box.h) : 40, h = W * box.h / box.w, items = "", wide = W, tall = h;
    group.forEach(function (it, i) {
      var x, y, r;
      if (stack === "fan") { x = i * 5; y = i * 3; r = -12 + (i * 7) % 24; }
      else if (stack === "row") { x = i * (W + 3); y = 0; r = ((i * 53) % 5 - 2) * 0.7; }
      else if (stack === "heap") {   // rows of 4, 3, 2, 1, each row resting in the dips of the one below
        var row = i < 4 ? 0 : i < 7 ? 1 : i < 9 ? 2 : 3, col = i - [0, 4, 7, 9][row];
        x = row * W * 0.42 + col * W * 0.84; y = row * h * 0.62; r = (i * 47) % 50 - 25;
      } else { x = ((i * 37) % 5) - 2; y = i * h * 0.86; r = ((i * 53) % 5 - 2) * 0.9; }
      wide = Math.max(wide, x + W); tall = Math.max(tall, y + h);
      items += '<button type="button" data-ks="' + esc(it.id) + '" class="ks-i' + (isNew[it.id] ? " is-new" : "") + '" style="left:' + x.toFixed(1) + "px;bottom:" + y.toFixed(1) + "px;width:" + W + "px;transform:rotate(" + r.toFixed(1) + 'deg)" title="' +
        esc(cap(it.name) + " · " + ksWhen(it)) + '" aria-label="' + esc(cap(it.name) + ", " + ksWhen(it)) + '">' + art + "</button>";
    });
    return '<div class="ks-pile ks-' + esc(stack) + '" style="width:' + Math.ceil(wide + 4) + "px;height:" + Math.ceil(tall + 6) + 'px" role="group" aria-label="' +
      esc(n + " " + (n === 1 ? group[0].name : group[0].plural)) + '">' + items + "</div>";
  }
  function ksStanding(it, art, isNew) {
    var W = it.kind === "die" ? 34 : 46;
    return '<div class="ks-one' + (isNew[it.id] ? " is-new" : "") + '"><button type="button" data-ks="' + esc(it.id) + '" class="ks-art" style="width:' + W + 'px" title="' +
      esc(cap(it.name) + " · " + ksWhen(it)) + '" aria-label="' + esc(cap(it.name) + ", " + ksWhen(it)) + '">' + art + "</button>" +
      (/^gifts\//.test(it.gift || "") ? '<a class="ks-gift" href="/vault/' + esc(it.gift) + '" target="_blank" rel="noopener">a gift</a>' : "") + "</div>";
  }
  // what a trophy stands for. The same words as the away mail (app/reminders.py TROPHY_MEANS).
  var KS_MEANS = {
    day: function () { return "days you reached your daily goal of " + DAY_GOAL_MIN + " minutes"; },
    week: function () { return "weeks you studied on " + WEEK_GOAL_DAYS + " days or more"; },
    die: function () { return "one for every 10 focused hours"; },
  };
  function ksLong(iso) { return new Date(iso + "T12:00:00").toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }); }
  function ksFacts(it) {
    if (it.kind === "day") return "On " + ksLong(it.date) + " you studied " + (it.minutes ? it.minutes + " focused minutes" : "past your goal") + ". The goal is " + DAY_GOAL_MIN + ".";
    if (it.kind === "week") return "In the week of " + ksLong(it.date) + " you studied on " + (it.days || WEEK_GOAL_DAYS) + " days. The goal is " + WEEK_GOAL_DAYS + ".";
    return "Your die number " + it.n + ": focused hours " + (it.n - 1) * 10 + " to " + it.n * 10 + ", finished on " + ksLong(it.date) + ".";
  }
  function ksStamp(it) {
    var word = it.stamp || (THEME && it.theme === THEME.meta.id && ksLook(it.kind).stamp) || "earned";
    var d = new Date(((it.ts || "").slice(0, 10) || it.date) + "T12:00:00");     // the day it was won
    return word + " " + d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  }
  function openTrophy(id) {
    var K = ksData(), it = (K.items || []).filter(function (x) { return x.id === id; })[0];
    if (!it) return;
    var box = $("#ks-detail");
    box.querySelector(".ks-d-art").innerHTML = K.art[it.art] || "";      // drawings are cleaned by the server (shelf_for_page)
    box.querySelector(".ks-stamp").textContent = ksStamp(it);
    $("#ks-d-title").textContent = cap(it.name);
    box.querySelector(".ks-d-means").textContent = "A " + it.name + " stands for " + (it.kind === "die" ? "10 focused hours" : KS_MEANS[it.kind]().replace(/^days/, "a day").replace(/^weeks/, "a week")) + ".";
    box.querySelector(".ks-d-facts").textContent = ksFacts(it);
    var links = it.kind !== "day" ? '<a class="btn" href="/card?id=' + encodeURIComponent(it.id) + '" target="_blank" rel="noopener">Print the card</a>' : "";
    if (/^gifts\//.test(it.gift || "")) links += '<a class="btn" href="/vault/' + esc(it.gift) + '" target="_blank" rel="noopener">Open the gift</a>';
    box.querySelector(".ks-d-links").innerHTML = links;
    // piles overlap, so a click can only reach the top one: step through every trophy of this kind instead
    var same = (K.items || []).filter(function (x) { return x.kind === it.kind; }).sort(function (a, b) { return (a.ts || "") < (b.ts || "") ? -1 : 1; });
    var i = same.indexOf(it), nav = function (j, label, sym) {
      return same[j] ? '<button class="icon-btn" type="button" data-ks="' + esc(same[j].id) + '" aria-label="' + label + '">' + sym + "</button>" : '<span class="icon-btn" aria-hidden="true"></span>';
    };
    box.querySelector(".ks-d-nav").innerHTML = same.length > 1 ? nav(i - 1, "Earlier", "‹") + "<span>" + (i + 1) + " of " + same.length + "</span>" + nav(i + 1, "Later", "›") : "";
    if ($("#ks-detail").hidden) openOverlay("ks-detail");
  }

  function shelfHTML() {
    var K = ksData(), items = K.items || [], seen = ksSeen() || {}, isNew = {};
    items.forEach(function (it) { if (!it.backfill && !seen[it.id]) isNew[it.id] = true; });
    if (!items.length) {
      var day = ksLook("day");
      return '<div class="ks-shelf is-empty"><p class="ks-sum">An empty shelf. Reach today\'s goal (' + DAY_GOAL_MIN + " min) and the first " + esc(day.name) + " goes here.</p></div>";
    }
    var groups = [], byArt = {}, counts = {}, order = [];
    items.forEach(function (it) {
      var key = it.kind + ":" + it.name;
      if (!counts[key]) { counts[key] = { n: 0, it: it }; order.push(key); }
      counts[key].n++;
      if (it.kind === "week") return;
      var g = byArt[it.art];
      if (!g || g.length >= KS_PILE) { g = byArt[it.art] = []; groups.push({ kind: it.kind, art: it.art, list: g }); }
      g.push(it);
    });
    var piles = function (kind) { return groups.filter(function (g) { return g.kind === kind; }).map(function (g) { return ksPile(g.list, K.art[g.art] || "", isNew); }).join(""); };
    // the newest die's gift sits beside the pile; every gift is also linked from its own card
    var dieGift = items.filter(function (it) { return it.kind === "die" && /^gifts\//.test(it.gift || ""); }).pop();
    var dice = piles("die") + (dieGift ? '<div class="ks-one"><a class="ks-gift" href="/vault/' + esc(dieGift.gift) + '" target="_blank" rel="noopener">a gift</a></div>' : "");
    var standing = function (kind) { return items.filter(function (it) { return it.kind === kind; }).map(function (it) { return ksStanding(it, K.art[it.art] || "", isNew); }).join(""); };
    var sum = ["day", "week", "die"].map(function (kind) {
      var mine = order.filter(function (k) { return counts[k].it.kind === kind; });
      if (!mine.length) return "";
      return '<span class="ks-sum-line">' + esc(mine.map(function (k) { var c = counts[k]; return c.n + " " + (c.n === 1 ? c.it.name : c.it.plural); }).join(", ")) +
        ": " + esc(KS_MEANS[kind]()) + "</span>";
    }).join("") + '<span class="ks-sum-hint">Click one to see the day you earned it.</span>';
    // three shelves, like a bookcase: the piles of days, then the weeks, then the piles of dice. Each object
    // brings its own stretch of plank, so a shelf that wraps on a narrow screen still has wood under every row.
    var shelves = [piles("day"), standing("week"), dice].filter(Boolean).map(function (row) { return '<div class="ks-row">' + row + "</div>"; }).join("");
    return '<div class="ks-shelf">' + shelves + '<p class="ks-sum">' + sum + "</p></div>";
  }
  // after a paint: say hello to anything new, then remember it. The first visit ever only remembers.
  function shelfNews() {
    var K = ksData(), seen = ksSeen(), first = !seen, news = [];
    seen = seen || {};
    (K.items || []).forEach(function (it) {
      if (!seen[it.id]) { if (!first && !it.backfill) news.push(it); seen[it.id] = 1; }
      var gk = "gift:" + it.id;
      if (/^gifts\//.test(it.gift || "") && !seen[gk]) { if (!first) news.push({ gift: it }); seen[gk] = 1; }
    });
    store(KS_SEEN, JSON.stringify(seen));
    var last = news[news.length - 1];
    if (!last) return;
    var lines = (THEME && THEME.meta.keepsakes && THEME.meta.keepsakes.lines) || {};
    if (last.gift) {
      toast('<span>🎁</span><span><b>' + esc(lines.gift || "Someone left you something on the shelf.") + '</b> <a href="/vault/' + esc(last.gift.gift) + '" target="_blank" rel="noopener">Open it</a></span>', 12000);
    } else {
      toast('<span>🏆</span><span><b>' + esc(lines[last.kind] || "A " + last.name + " for your shelf.") + "</b>" +
        (last.kind !== "day" ? ' <a href="/card?id=' + encodeURIComponent(last.id) + '" target="_blank" rel="noopener">Print the card</a>' : "") + "</span>", 9000);
    }
  }
  function shelfCard(title) {
    return '<section class="card ks-card"><div class="card-head"><h2 class="card-title">' + esc(title) + "</h2></div>" + shelfHTML() + "</section>";
  }

  function renderBar(hero, topics, live) {
    var nm = barName(), room = barRoom();
    var tabs = '<div class="bx-tabs" role="group" aria-label="Rooms">' +
      '<button type="button" data-room="front" aria-pressed="' + (room === "front") + '">' + esc(W("front_icon")) + " " + esc(W("front")) + "</button>" +
      '<button type="button" data-room="back" aria-pressed="' + (room === "back") + '">' + esc(W("back_icon")) + " " + esc(W("back")) + "</button></div>";
    var neon = '<button class="bx-neon" type="button" data-barname title="Click for another name">' + esc(nm[0]) + (nm[1] ? "<small>" + esc(nm[1]) + "</small>" : "") + "</button>";
    if (room === "back") {
      var list = allBlocks();
      return '<div class="room t-' + esc(THEME.meta.id) + ' is-back"><div class="bx-backroom">' + '<div class="bx-backhead">' + neon + tabs + "</div>" +
        '<div class="bx-back">' + shelfCard("The shelf") +
          (list.length ? '<section class="card bx-cluster">' + clusterHTML(list) + "</section>" : "") +
          live.map(renderMilestones).join("") + renderGates(live) +
          live.map(renderEvidence).join("") + renderCalibration() + live.map(renderSkills).join("") +
          topics.map(renderTopic).join("") + renderLinked() +
        '</div></div></div>';
    }
    var locked = actionableTasks().filter(function (e) { return e.task.status === "locked"; });
    var fill = {
      name: neon, rooms: tabs,
      tonight: tonightHTML(), week: weekHTML(), die: cabinetHTML(),
      sign: esc(W(active ? "sign_busy" : "sign_open")),
      clock: esc(active ? clock(active.end - Date.now()) : hhmm(Date.now())),
      water: glassHTML(),
      finish: renderFinishLine(topics[0]),
      doors: locked.length ? '<div class="bx-doors"><div class="bx-k">' + esc(W("doors")) + " · " + locked.length + "</div><ul>" +
        locked.map(function (e) { return "<li><b>" + esc(e.task.label ? e.task.label + ": " : "") + esc(e.task.title) + '</b><span class="bx-chk">' + esc(e.task.unlock || "Locked") + "</span></li>"; }).join("") +
        "</ul></div>" : "",
      timer: active ? '<div class="bx-clock" id="bx-clock" style="--c:' + blockColor(active.block) + '"><b data-bx-time>' + esc(clock(active.end - Date.now())) + "</b>" +
        '<div><div class="bx-mono">' + esc(blockLabel(active.block)) + (active.task && findTask(active.task) ? " · " + esc(findTask(active.task).task.label || findTask(active.task).task.title) : "") + " · ends " + esc(hhmm(active.end)) + "</div>" +
        (active.water ? '<div class="bx-wbar"><i data-bx-wbar></i></div>' : "") + '<div class="bx-mono" data-water-text>' + esc(waterText()) + "</div></div></div>" : "",
      voices: barLines2HTML(hero), job: recallCard(true) + barJob(hero), replies: barReplies(hero),
      keys: "Press <kbd>1</kbd>–<kbd>9</kbd> to reply.",
      block: '<div id="blk-slot"></div>', music: '<div id="bx-music-slot"></div>', shelf: shelfHTML()
    };
    var tpl = document.createElement("template");
    tpl.innerHTML = THEME.layout;   // cleaned by the server: no scripts, handlers, links or ids
    tpl.content.querySelectorAll("[data-slot]").forEach(function (el) { el.innerHTML = fill[el.dataset.slot] || ""; });
    var box = document.createElement("div");
    box.appendChild(tpl.content);
    return '<div class="room t-' + esc(THEME.meta.id) + '">' + box.innerHTML + "</div>";
  }

  // cheap refresh of the parts that change between polls, without redrawing the room
  function paintBarBits() {
    if (!isBar() || !THEME) return;
    var parts = { tonight: tonightHTML, week: weekHTML, die: cabinetHTML };
    Object.keys(parts).forEach(function (k) { var el = $('.room [data-slot="' + k + '"]'); if (el) el.innerHTML = parts[k](); });
  }

  function barTick() {
    if (!isBar()) return;
    var wc = $('.room [data-slot="clock"]');
    if (!active) { if (wc) wc.textContent = hhmm(Date.now()); return; }
    var t = clock(active.end - Date.now());
    if (wc) wc.textContent = t;
    var bt = $("[data-bx-time]"); if (bt) bt.textContent = t;
  }

  function paintViewButton() {
    var b = $("#btn-view");
    if (b) b.innerHTML = isBar() ? '☰ <span class="hide-sm">Classic view</span>' : esc(THEME ? W("front_icon") : "🍸") + ' <span class="hide-sm">' + esc(THEME ? W("view") : "Room view") + "</span>";
  }

  document.addEventListener("keydown", function (ev) {
    if (!isBar() || barRoom() !== "front" || ev.metaKey || ev.ctrlKey || ev.altKey || !/^[1-9]$/.test(ev.key)) return;
    if (document.querySelector(".overlay:not([hidden])")) return;
    if (/^(input|textarea|select)$/i.test(ev.target.tagName || "")) return;
    var r = $('.bx-replies [data-n="' + ev.key + '"]');
    if (r) { ev.preventDefault(); r.click(); }
  });


  // ---------------------------------------------------------------- jukebox music (bar view only)
  // Three sources (Settings → Music): a soundscape made live in the browser (the default, offline),
  // a radio station, or one track of your own on loop (stored in _system/music/). A track picks up
  // where you left off (saved every few seconds), and the scrubber, ±1 min and "random spot" choose
  // where it plays. Only one tab plays at a time.
  var MUSIC_KEY = "edu.music.v1", MUSIC_OWNER_KEY = "edu.music.owner.v1";
  var SCAPES = window.EduScapes.list;   // scapes.js
  // stations that publish their stream addresses for other players, checked to play in a browser
  var STATIONS = [
    { name: "Radio Paradise · Mellow", url: "https://stream.radioparadise.com/mellow-128", note: "mellow rock, folk and electronica, no ads" },
    { name: "Radio Paradise · Serenity", url: "https://stream.radioparadise.com/serenity", note: "ambient and slow" },
    { name: "Radio Paradise · Main mix", url: "https://stream.radioparadise.com/aac-128", note: "eclectic, picked by people" },
    { name: "Radio Paradise · Global", url: "https://stream.radioparadise.com/global-128", note: "music from everywhere" }
  ];
  function musicConf() { return cfg().music || {}; }
  function musicSrc() { var m = musicConf(); return m.source || (m.file ? "file" : "scape"); }
  function musicFile() { return musicConf().file || ""; }
  function musicStream() { return musicConf().stream || {}; }
  function musicScape() { return SCAPES[musicConf().scape] ? musicConf().scape : "night"; }
  // what is loaded; a different one resets the player. A file keeps its bare name, so positions saved
  // before sources existed still match.
  function musicKey() {
    var s = musicSrc();
    return s === "file" ? musicFile() : s === "radio" ? "radio:" + (musicStream().url || "") : "scape:" + musicScape();
  }
  function musicPlayable() { var s = musicSrc(); return s === "scape" || (s === "radio" ? !!musicStream().url : !!musicFile()); }
  function streamHost() { try { return new URL(musicStream().url).host; } catch (e) { return ""; } }
  function musicTitle() {
    var s = musicSrc();
    if (s === "scape") return SCAPES[musicScape()].name;
    if (s === "radio") return musicStream().name || streamHost() || "Radio";
    return musicConf().title || musicFile().replace(/\.[^.]+$/, "");
  }
  function musicSub() {
    var s = musicSrc();
    if (s === "scape") return SCAPES[musicScape()].sub + " · offline";
    if (s === "radio") return "live radio · " + streamHost();
    return (musicConf().subtitle ? musicConf().subtitle + " · " : "") + "on loop";
  }
  var TAB_ID = Math.random().toString(36).slice(2);
  var music = null, musicReady = false, musicWaiting = false, musicErr = false, musicSaveT = 0, musicDrag = false, musicDuck = 0, musicQueued = null;
  var musicEl = document.createElement("div");
  musicEl.className = "bx-music";

  // position, volume and on/off for this browser; the position belongs to one file and resets for a new one
  function musicPrefs() {
    var m = readJSON(MUSIC_KEY) || {}, same = m.file === musicKey();
    return { file: musicKey(), t: same ? m.t || 0 : 0, vol: m.vol == null ? 0.5 : m.vol,
      on: m.on == null ? musicConf().autoplay !== false : m.on !== false };
  }
  function saveMusic(extra) {
    var m = musicPrefs();
    if (music && music.dataset.file !== m.file) return;   // a stale player for a track that was replaced
    if (music && musicReady && !music.seeking) m.t = music.currentTime;
    if (music && !musicDuck) m.vol = music.volume;
    for (var k in extra || {}) m[k] = extra[k];
    writeJSON(MUSIC_KEY, m);
  }
  function longClock(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    var h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
  }

  function ensureMusic() {
    if (music) return music;
    if (musicSrc() === "scape") {
      music = makeScape(musicScape());
      music.volume = musicPrefs().vol;
      musicReady = true;
      music.addEventListener("play", function () { store(MUSIC_OWNER_KEY, TAB_ID + ":" + Date.now()); paintMusic(); });
      music.addEventListener("pause", function () { saveMusic(); releaseMusic(); paintMusic(); });
      music.dataset.file = musicKey();
      return music;
    }
    music = new Audio();
    music.preload = "metadata";
    music.loop = true;
    music.volume = musicPrefs().vol;
    music.addEventListener("loadedmetadata", function () {
      if (this !== music) return;
        // a player that was swapped out
      var t = musicPrefs().t;
      if (musicSrc() === "file" && t > 0 && t < music.duration) music.currentTime = t;   // resume where you left off
      musicReady = true;
      if (musicQueued) { var q = musicQueued; musicQueued = null; musicJump(q); }
      paintMusic();
    });
    music.addEventListener("timeupdate", function () {
      if (this !== music) return;
      if (Date.now() - musicSaveT > 3000 && !music.paused) { musicSaveT = Date.now(); saveMusic(); store(MUSIC_OWNER_KEY, TAB_ID + ":" + Date.now()); }
      paintMusicTime();
    });
    music.addEventListener("play", function () {
      if (this !== music) return;
      store(MUSIC_OWNER_KEY, TAB_ID + ":" + Date.now()); paintMusic(); });
    music.addEventListener("pause", function () {
      if (this !== music) return;
      saveMusic(); releaseMusic(); paintMusic(); });
    music.addEventListener("error", function () {
      if (this !== music) return;
      musicErr = true; musicWaiting = false; paintMusic(); });
    music.addEventListener("playing", function () {
      if (this !== music) return;
      musicErr = false; paintMusic(); });
    if (musicSrc() === "radio") { music.loop = false; music.preload = "none"; music.src = musicStream().url; }
    else music.src = "/music?f=" + encodeURIComponent(musicFile());
    music.dataset.file = musicKey();
    return music;
  }

  function musicStart() {
    var a = ensureMusic(), pr = a.play();
    musicErr = false;
    if (pr && pr.then) pr.then(function () { musicWaiting = false; paintMusic(); }, function () { musicWaiting = true; paintMusic(); });
  }

  // drop the "this tab is playing" marker when this tab stops, so a reload or another tab can take over
  function releaseMusic() {
    var o = store(MUSIC_OWNER_KEY) || "";
    if (o.indexOf(TAB_ID + ":") === 0) { try { localStorage.removeItem(MUSIC_OWNER_KEY); } catch (e) {} }
  }

  function musicJump(what) {
    var a = ensureMusic();
    if (!musicReady || !isFinite(a.duration)) { musicQueued = what; return; }   // after the track's length is known
    if (what === "back") a.currentTime = Math.max(0, a.currentTime - 60);
    if (what === "fwd") a.currentTime = Math.min(a.duration - 1, a.currentTime + 60);
    if (what === "rand") a.currentTime = Math.floor(Math.random() * (a.duration - 60));
    saveMusic();
    paintMusicTime();
  }

  // another tab is playing if it said so in the last 10 seconds
  function otherTabPlaying() {
    var o = store(MUSIC_OWNER_KEY) || "", i = o.lastIndexOf(":");
    return o && o.slice(0, i) !== TAB_ID && Date.now() - Number(o.slice(i + 1)) < 10000;
  }

  // called after every render: play in the bar if you want it on, stop in classic
  function musicSync() {
    if (!isBar()) { if (music && !music.paused) music.pause(); return; }
    if (music && music.dataset.file !== musicKey()) {   // the source changed in Settings
      music.pause(); music.removeAttribute("src"); music.load(); music = null; musicReady = false; musicQueued = null; musicErr = false;
      musicEl.innerHTML = "";
    }
    var slot = $("#bx-music-slot");
    // the shell is drawn for one file (or for none); redraw it when that changes
    if (!musicEl.firstChild || musicEl.dataset.file !== musicKey()) paintMusicShell();
    if (slot) slot.replaceWith(musicEl);
    paintMusic();
    if (!musicPlayable()) return;
    if (musicPrefs().on && (!music || music.paused) && !musicWaiting && !otherTabPlaying()) musicStart();
  }

  // music dips under the chime and the water clink, then comes back
  function duckMusic(ms) {
    if (!music || music.paused) return;
    if (!musicDuck) music.volume = musicPrefs().vol * 0.25;
    clearTimeout(musicDuck);
    musicDuck = setTimeout(function () { musicDuck = 0; if (music) music.volume = musicPrefs().vol; }, ms);
  }

  function paintMusicShell() {
    musicEl.dataset.file = musicKey();
    if (!musicPlayable()) {
      musicEl.innerHTML = '<div class="bx-mu-empty"><b>No tape loaded.</b><span>The jukebox plays one track of your own on loop, and remembers where it stopped.</span>' +
        '<button class="bx-mu-add" type="button" data-settings="music">Add music in Settings</button></div>';
      return;
    }
    musicEl.innerHTML =
      '<div class="bx-mu-head"><button class="bx-mu-play" type="button" data-mu="toggle" aria-label="Play or pause the music"></button>' +
        '<div class="bx-mu-title"><b>' + esc(musicTitle()) + '</b><small data-mu-state></small></div>' +
        '<span class="bx-eq" aria-hidden="true"><i></i><i></i><i></i><i></i></span></div>' +
      (musicSrc() === "file" ?
        '<input class="bx-mu-seek" type="range" min="0" max="1" step="1" value="0" data-mu-seek aria-label="Where in the track to play">' +
        '<div class="bx-mu-row"><span class="bx-mu-time" data-mu-time>–</span>' +
          '<button type="button" data-mu="back" title="Back one minute">−1m</button><button type="button" data-mu="fwd" title="Forward one minute">+1m</button>' +
          '<button type="button" data-mu="rand" title="Jump to a random spot">⤨ random</button></div>'
      : musicSrc() === "scape" ?
        '<div class="bx-mu-row bx-mu-scapes">' + Object.keys(SCAPES).map(function (id) {
          return '<button type="button" data-scape="' + id + '" aria-pressed="' + (id === musicScape()) + '">' + esc(SCAPES[id].name) + "</button>";
        }).join("") + "</div>"
      : "") +
      '<button class="bx-mu-change" type="button" data-settings="music">' + (musicSrc() === "file" ? "change music" : musicSrc() === "radio" ? "change station" : "radio or your own music") + "</button>" +
      '<label class="bx-mu-vol"><span>vol</span><input type="range" min="0" max="1" step="0.05" data-mu-vol aria-label="Music volume"></label>' +
      '<p class="bx-mu-hint" data-mu-hint hidden>Click anywhere to start the music. Browsers need one click first.</p>';
  }

  function paintMusicTime() {
    if (!music) return;
    var seek = musicEl.querySelector("[data-mu-seek]"), d = music.duration;
    if (seek && isFinite(d)) { seek.max = Math.floor(d); if (!musicDrag) seek.value = Math.floor(music.currentTime); }
    var tm = musicEl.querySelector("[data-mu-time]");
    if (tm) tm.textContent = longClock(musicDrag && seek ? Number(seek.value) : music.currentTime) + " / " + (isFinite(d) ? longClock(d) : "–");
  }

  function paintMusic() {
    document.body.classList.toggle("music-on", !!(music && !music.paused));
    if (!musicEl.firstChild || !musicPlayable()) return;
    var playing = music && !music.paused;
    document.body.classList.toggle("music-on", !!playing);
    musicEl.classList.toggle("is-playing", !!playing);
    var b = musicEl.querySelector("[data-mu=toggle]");
    b.textContent = playing ? "❚❚" : "▶";
    var src = musicSrc();
    musicEl.querySelector("[data-mu-state]").textContent = musicErr ? (src === "radio" ? "the station isn't answering" : "this track won't play")
      : playing ? musicSub() : musicWaiting ? "waiting for a click" : otherTabPlaying() ? "playing in another tab"
      : src === "file" ? "paused · resumes where you left off" : src === "radio" ? "paused · live, joins wherever it is" : "paused · press play";
    musicEl.querySelector("[data-mu-hint]").hidden = !musicWaiting;
    var vol = musicEl.querySelector("[data-mu-vol]");
    if (document.activeElement !== vol) vol.value = musicPrefs().vol;
    var tm = musicEl.querySelector("[data-mu-time]");
    if (!music && tm) { var t = musicPrefs().t; tm.textContent = t ? "resumes at " + longClock(t) : "–"; }
    paintMusicTime();
  }

  musicEl.addEventListener("click", function (ev) {
    var sc = ev.target.closest("[data-scape]");
    if (sc) return switchScape(sc.dataset.scape);
    var b = ev.target.closest("[data-mu]");
    if (!b) return;
    var a = ensureMusic(), what = b.dataset.mu;
    if (what === "toggle") {
      if (a.paused) { saveMusic({ on: true }); musicWaiting = false; musicStart(); }
      else { a.pause(); saveMusic({ on: false }); }
      return;
    }
    musicJump(what);
  });
  musicEl.addEventListener("input", function (ev) {
    if (ev.target.hasAttribute("data-mu-vol")) {
      var v = Number(ev.target.value);
      if (music && !musicDuck) music.volume = v;
      saveMusic({ vol: v });
    } else if (ev.target.hasAttribute("data-mu-seek")) { musicDrag = true; paintMusicTime(); }
  });
  musicEl.addEventListener("change", function (ev) {
    if (!ev.target.hasAttribute("data-mu-seek")) return;
    musicDrag = false;
    var a = ensureMusic();
    if (musicReady) { a.currentTime = Number(ev.target.value); saveMusic(); } else saveMusic({ t: Number(ev.target.value) });
    paintMusicTime();
  });
  // the first click or key press anywhere lets the music start (browser autoplay rule)
  ["pointerdown", "keydown"].forEach(function (type) {
    document.addEventListener(type, function (ev) {
      if (!musicWaiting || !isBar() || !musicPlayable() || musicEl.contains(ev.target)) return;
      musicWaiting = false;
      if (musicPrefs().on) musicStart();
    }, true);
  });
  window.addEventListener("storage", function (ev) {
    if (ev.key === MUSIC_OWNER_KEY && music && !music.paused && otherTabPlaying()) music.pause();
  });
  window.addEventListener("pagehide", function () { if (music) saveMusic(); releaseMusic(); });


  // ---------------------------------------------------------------- Claude, in the page
  // The server runs Claude Code in the vault (see /api/claude). Grading, chatting and starting a topic
  // all happen here; the drawer shows what Claude is doing while it works. Without Claude Code
  // installed, the page keeps its old instructions for doing it in a terminal.
  var CL = { available: false, busy: false, conversation: false, next: 0, events: [], timer: 0, gen: 0 };
  function claudeOK() { return CL.available; }
  function pendingCount() { return (DATA && DATA.inbox && DATA.inbox.pending || []).filter(function (e) { return e.kind !== "note"; }).length; }
  function gradeButton(label) {
    return claudeOK() ? '<button class="btn btn-topic btn-sm" type="button" data-claude="grade"' + (CL.busy ? " disabled" : "") + ">" + (label || "✦ Grade it now") + "</button>" : "";
  }
  // A poll that left before a send or reset answers about the old world: CL.gen drops those answers.
  function claudePoll() {
    var gen = CL.gen;
    return fetch("/api/claude?since=" + CL.next, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) {
      if (gen !== CL.gen) return;
      var wasAvail = CL.available, wasBusy = CL.busy;
      if (j.next < CL.next) { CL.events = []; CL.next = 0; return claudePoll(); }   // the server started over
      CL.available = j.available; CL.busy = j.busy; CL.conversation = j.conversation;
      var fresh = j.events.filter(function (e) { return e.n >= CL.next; });
      if (fresh.length) { CL.events = CL.events.concat(fresh); }
      CL.next = Math.max(CL.next, j.next);
      paintClaude();
      if (wasBusy && !j.busy) {
        var last = CL.events[CL.events.length - 1] || {};
        toast(last.kind === "check" && /OK/.test(last.text) ? "<span>✦</span><span><b>Claude is done.</b></span>" : "<span>!</span><span><b>Claude finished with a problem.</b> Open ✦ Claude to see it.</span>", 5000);
        load();
      }
      if (wasAvail !== j.available || wasBusy !== j.busy) { if (DATA) render(); }
      clearTimeout(CL.timer);
      if (j.busy) CL.timer = setTimeout(claudePoll, 700);
    }).catch(function () {});
  }
  function claudeSend(kind, text) {
    openClaude();
    var st = $("#cl-status");
    CL.gen++;
    return fetch("/api/claude", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: kind, text: text || "" }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "couldn't start"); }); })
      .then(function () { CL.gen++; CL.busy = true; paintClaude(); if (DATA) render(); return claudePoll(); })
      .catch(function (e) { st.textContent = e.message; st.classList.add("is-err"); });
  }
  function openClaude() {
    openOverlay("claude");
    paintClaude();
    var inp = $("#cl-input"); if (!CL.busy) inp.focus();
    claudePoll();
  }
  // ---- hints: one at a time, and each one opened is noted in the exercise's work record (server.py open_hint)
  function hintsButton(t, cls) {
    return t.exercise ? '<button class="' + cls + '" type="button" data-hints="' + esc(t.id) + '">Hints</button>' : "";
  }
  // stuck: the last few checker runs all failed (server.py stuck_tasks). A gentle offer, nothing written.
  function stuckNudge(t, bar) {
    var st = DATA && DATA.derived && DATA.derived.stuck && DATA.derived.stuck[t.id];
    if (!st || pendingFor(t.id)) return "";
    var h = st.next_hint, say = plural(st.fails, "run") + " in a row haven't passed yet. Getting stuck here is normal.";
    var act = h ? '<button class="btn btn-soft btn-sm" type="button" data-stuck-hint="' + esc(t.id) + '" data-n="' + h.n + '">Open the next hint: ' + esc(h.title) + "</button>"
      : '<button class="btn btn-ghost btn-sm" type="button" data-note>Tell Claude where it breaks</button>';
    return '<div class="stuck' + (bar ? " bx-stuck" : "") + '" role="status"><span>' + esc(say) + (h ? "" : " You've opened every hint already.") + "</span>" + act + "</div>";
  }
  function stuckHint(id, n) {      // the learner asked for it with the button, so it opens and is noted like any hint
    fetch("/api/hints", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task: id, n: n }) })
      .then(function () { openHints(id); load(); }).catch(function () { openHints(id); });
  }
  // the attempts so far, from the work record: each run (passed or not, and how long after the one before) and each hint
  function sinceText(sec) {
    if (sec == null) return "";
    return sec < 10 ? "right after" : sec < 60 ? sec + " s later" : sec < 3600 ? Math.round(sec / 60) + " min later" : sec < 86400 ? Math.round(sec / 3600) + " h later" : Math.round(sec / 86400) + " days later";
  }
  function paintAttempts(a) {
    var box = $("#hints-attempts");
    if (!a || !a.events.length) { box.innerHTML = '<p class="set-hint">No checker runs yet. Each time you run the checker it shows up here.</p>'; return; }
    var run = 0;
    box.innerHTML = '<ol class="att">' + a.events.map(function (e) {
      var when = new Date(e.ts).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
      if (e.kind === "hint") return '<li class="att-hint"><b>Hint ' + esc(e.n) + " opened</b><span>" + esc(e.title) + "</span><small>" + esc(when) + "</small></li>";
      run++;
      return '<li class="att-run ' + (e.passed ? "is-pass" : "is-fail") + '"><b>Run ' + run + ": " + (e.passed ? "passed" : "didn't pass") + "</b><span>" +
        esc(e.since == null ? "first run" : sinceText(e.since)) + "</span><small>" + esc(when) + "</small></li>";
    }).join("") + "</ol>";
  }
  function hintText(t) {
    return esc(t).replace(/`([^`]+)`/g, "<code>$1</code>").split("\n").map(function (l) {
      return /^\s*-\s+/.test(l) ? "<li>" + l.replace(/^\s*-\s+/, "") + "</li>" : l.trim() ? "<p>" + l.trim() + "</p>" : "";
    }).join("").replace(/(<li>[\s\S]*?<\/li>)(?!<li>)/g, "<ul>$1</ul>").replace(/<\/ul><ul>/g, "");
  }
  var hintsTask = null;
  function paintHints(list) {
    $("#hints-list").innerHTML = list.map(function (h) {
      var when = h.opened ? new Date(h.opened).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
      return '<div class="hint' + (h.opened ? " is-open" : "") + '"><div class="hint-head"><b>' + esc(h.title) + "</b>" +
        (h.opened ? '<small>opened ' + esc(new Date(h.opened).toLocaleDateString([], { day: "numeric", month: "short" })) + " " + esc(when) + "</small>"
          : '<button class="btn btn-soft btn-sm" type="button" data-hint-n="' + h.n + '">Open this hint</button>') + "</div>" +
        (h.opened ? '<div class="hint-body">' + hintText(h.body || "") + "</div>" : "") + "</div>";
    }).join("") || '<p class="set-hint">No hints for this one.</p>';
  }
  function openHints(id) {
    var e = findTask(id);
    hintsTask = id;
    $("#hints-title").textContent = "Hints: " + (e ? (e.task.label ? e.task.label + ": " : "") + e.task.title : id);
    $("#hints-list").innerHTML = '<p class="set-hint">Loading…</p>';
    openOverlay("hints");
    fetch("/api/attempts?task=" + encodeURIComponent(id), { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (j) { paintAttempts(j.error ? null : j); }).catch(function () { paintAttempts(null); });
    fetch("/api/hints?task=" + encodeURIComponent(id), { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (j) { if (j.error) throw new Error(j.error); paintHints(j.hints); })
      .catch(function (err) { $("#hints-list").innerHTML = '<p class="form-error">' + esc(err.message) + "</p>"; });
  }
  function revealHint(n) {
    fetch("/api/hints", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task: hintsTask, n: n }) })
      .then(function (r) { return r.json(); }).then(function (j) { if (j.error) throw new Error(j.error); openHints(hintsTask); })
      .catch(function (err) { $("#hints-list").insertAdjacentHTML("afterbegin", '<p class="form-error">' + esc(err.message) + "</p>"); });
  }

  // ---- the work record in Settings: what's kept, and deleting it after saying what that costs
  function kb(b) { return b < 1024 ? b + " bytes" : b < 1048576 ? Math.round(b / 1024) + " KB" : (b / 1048576).toFixed(1) + " MB"; }
  function paintTraceSettings(confirming) {
    var box = $("#set-trace");
    if (!box) return;
    fetch("/api/traces", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (s) {
      var none = !s.runs && !s.hints;
      box.innerHTML = '<p class="set-hint">' + (none ? "Nothing saved yet." :
        "Saved now: " + s.runs + " checker run" + (s.runs === 1 ? "" : "s") + " and " + s.hints + " hint" + (s.hints === 1 ? "" : "s") +
        " opened, across " + s.exercises + " exercise" + (s.exercises === 1 ? "" : "s") + " (" + kb(s.bytes) + ").") + "</p>" +
        (none ? "" : confirming
          ? '<div class="set-warn"><p><b>Delete your whole work record?</b> Grades you already got stay. But Claude can no longer look back at how you worked through those exercises: ' +
            "where you got stuck, what you tried, which hints you opened. Anything not graded yet gets graded from your answers alone, and spotting patterns in your mistakes starts over. This can't be undone.</p>" +
            '<button class="btn btn-sm" type="button" id="set-trace-yes">Yes, delete it</button> <button class="btn btn-ghost btn-sm" type="button" id="set-trace-no">Keep it</button></div>'
          : '<button class="btn btn-ghost btn-sm" type="button" id="set-trace-del">Delete my work record…</button>');
    }).catch(function () { box.innerHTML = ""; });
  }
  function deleteTraces() {
    fetch("/api/traces/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) })
      .then(function (r) { return r.json(); }).then(function (j) {
        paintTraceSettings(false);
        toast("<span>🗑</span><span><b>Deleted " + j.deleted + " saved file" + (j.deleted === 1 ? "" : "s") + ".</b> New checker runs start a fresh record.</span>", 6000);
      });
  }

  // replies are plain text with a little markdown: paragraphs, **bold**, `code`, and - lists
  function clText(t) {
    return esc(t).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>")
      .split(/\n{2,}/).map(function (p) { return "<p>" + p.replace(/\n/g, "<br>") + "</p>"; }).join("");
  }
  function paintClaude() {
    var log = $("#cl-log");
    if (!log) return;
    var html = "", tools = [];
    function flush() { if (tools.length) { html += '<div class="cl-tools">' + tools.map(function (t) { return "<span>" + esc(t) + "</span>"; }).join("") + "</div>"; tools = []; } }
    CL.events.forEach(function (e) {
      if (e.kind === "tool") return tools.push(e.text);
      flush();
      if (e.kind === "you") html += '<div class="cl-msg cl-you">' + clText(e.text) + "</div>";
      else if (e.kind === "text") html += '<div class="cl-msg cl-claude">' + clText(e.text) + "</div>";
      else html += '<div class="cl-note cl-' + e.kind + '">' + esc(e.text) + "</div>";
    });
    flush();
    if (!CL.events.length) html = '<div class="cl-empty">' + (claudeOK()
      ? "Nothing here yet. Try “what should I work on tonight?”, or press <b>Grade my inbox</b>."
      : "Claude Code isn't installed on this computer, or isn't on the PATH, so the page can't run it. Install it from <a href=\"https://claude.com/claude-code\" target=\"_blank\" rel=\"noopener\">claude.com/claude-code</a>, sign in once in a terminal, then restart the dashboard.") + "</div>";
    if (CL.busy) html += '<div class="cl-working"><span class="cl-dots" aria-hidden="true"><i></i><i></i><i></i></span> Claude is working…</div>';
    var stick = log.scrollHeight - log.scrollTop - log.clientHeight < 60;
    log.innerHTML = html;
    if (stick) log.scrollTop = log.scrollHeight;
    $("#cl-send").disabled = CL.busy || !claudeOK();
    $("#cl-grade").disabled = CL.busy || !claudeOK();
    $("#cl-input").disabled = !claudeOK();
    $("#cl-stop").hidden = !CL.busy;
    $("#cl-new").disabled = CL.busy || !CL.events.length;
    var st = $("#cl-status"); if (!st.classList.contains("is-err")) st.textContent = "";
    // the top bar: the Claude button, and a grade button while something waits
    $("#btn-claude").hidden = !claudeOK();
    $("#btn-claude").classList.toggle("is-busy", CL.busy);
    $("#btn-note").hidden = claudeOK();
    var g = $("#btn-grade"), n = pendingCount();
    g.hidden = !claudeOK() || (!n && !CL.busy);
    g.disabled = CL.busy;
    g.innerHTML = CL.busy ? "✦ Claude is working…" : "✦ Grade " + n + " <span class=\"hide-sm\">waiting</span>";
  }

  function openNewTopic() {
    var body = $("#nt-body");
    body.innerHTML = claudeOK()
      ? '<p class="nt-intro">Say it in your own words. Claude asks a few questions in the chat, then sets up the first lessons, and the topic appears on this page.</p>' +
        '<label class="nt-field"><span>What, and why?</span><textarea id="nt-what" rows="3" maxlength="2000" placeholder="Spanish, for a move to Madrid next spring" required></textarea></label>' +
        '<label class="nt-field"><span>Anything Claude should know? <small>optional</small></span><textarea id="nt-more" rows="2" maxlength="2000" placeholder="how much time you have, what you know already, a deadline"></textarea></label>' +
        '<p class="form-error" id="nt-error" hidden></p>' +
        '<div class="sub-buttons"><button class="btn btn-ghost" type="button" data-close>Cancel</button><button class="btn btn-primary" type="submit">Start with Claude</button></div>'
      : '<p class="nt-intro">Starting a topic needs Claude Code on this computer. Install it from <a href="https://claude.com/claude-code" target="_blank" rel="noopener">claude.com/claude-code</a> and sign in once; then this button does it all here. Until then, in a terminal:</p>' +
        "<pre><code>cd " + esc((DATA && DATA.server && DATA.server.vault) || "your-vault") + " && claude\n&gt; /teach what you want to learn</code></pre>" +
        '<div class="sub-buttons"><button class="btn btn-primary" type="button" data-close>OK</button></div>';
    openOverlay("newtopic");
    var w = $("#nt-what"); if (w) w.focus();
  }
  $("#nt-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var what = ($("#nt-what") || {}).value || "", more = ($("#nt-more") || {}).value || "";
    if (!what.trim()) { var e = $("#nt-error"); e.textContent = "Say what you want to learn first."; e.hidden = false; return; }
    closeOverlay($("#newtopic"));
    claudeSend("topic", what.trim() + (more.trim() ? "\nMore about me: " + more.trim() : ""));
  });
  $("#cl-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var inp = $("#cl-input"), text = inp.value.trim();
    if (!text || CL.busy) return;
    inp.value = ""; $("#cl-status").classList.remove("is-err");
    claudeSend("chat", text);
  });
  $("#cl-input").addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); $("#cl-form").requestSubmit(); }
  });
  $("#cl-grade").addEventListener("click", function () { $("#cl-status").classList.remove("is-err"); claudeSend("grade"); });
  $("#cl-stop").addEventListener("click", function () { fetch("/api/claude/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(claudePoll); });
  $("#cl-new").addEventListener("click", function () {
    // forget locally first, so a reply landing late can't wipe a message sent right after
    CL.gen++; CL.events = []; CL.next = 0; paintClaude(); $("#cl-input").focus();
    fetch("/api/claude/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  });
  $("#btn-claude").addEventListener("click", openClaude);
  $("#btn-grade").addEventListener("click", function () { claudeSend("grade"); });
  $("#btn-topic").addEventListener("click", openNewTopic);

  // a soundscape chip in the jukebox: saved like any setting, keeps playing if it was
  function switchScape(id) {
    if (!DATA || !DATA.config || id === musicScape()) return;
    var was = music && !music.paused, c = JSON.parse(JSON.stringify(DATA.config));
    c.music.source = "scape"; c.music.scape = id;
    postConfig({ config: c }).then(function (j) {
      DATA.config = j.config; applyConfig();
      if (was) { var pr = musicPrefs(); pr.on = true; writeJSON(MUSIC_KEY, pr); }   // musicPrefs is already keyed to the new scape
      musicSync();
    }).catch(function (e) { toast(esc(e.message)); });
  }

  // ---------------------------------------------------------------- soundscapes
  // The music is made in scapes.js; this wraps it in something that acts enough like an <audio>
  // element (play, pause, paused, volume, events) for the jukebox to treat it as one.
  function makeScape(id) {
    var ev = document.createElement("span"), ctx = null, out = null, piece = null, vol = 0.5;
    var p = { paused: true, currentTime: 0, duration: NaN, seeking: false, dataset: {},
      addEventListener: ev.addEventListener.bind(ev), removeAttribute: function () {},
      load: function () { stop(); if (ctx) { ctx.close(); ctx = null; } } };
    Object.defineProperty(p, "volume", { get: function () { return vol; }, set: function (v) {
      vol = v; if (out) out.gain.setTargetAtTime(v, ctx.currentTime, 0.08);
    } });
    p.play = function () {
      if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
      // Chrome leaves a context made before the first click suspended; give up quickly, and the
      // jukebox's "waiting for a click" path calls play() again inside the click
      var tries = 0;
      return ctx.resume().then(function () {
        return new Promise(function (ok, no) {
          (function wait() { if (ctx.state === "running") ok(); else if (++tries > 6) no(new Error("NotAllowedError")); else setTimeout(wait, 50); })();
        });
      }).then(function () {
        if (!p.paused) return;
        out = ctx.createGain(); out.gain.value = 0; out.connect(ctx.destination);
        out.gain.setTargetAtTime(vol, ctx.currentTime, 0.6);   // fade in
        piece = window.EduScapes.start(ctx, out, id, Date.now() % 100000);
        p.paused = false; ev.dispatchEvent(new Event("play"));
      });
    };
    function stop() { if (piece) { piece.stop(); piece = null; } out = null; }
    p.pause = function () { if (p.paused) return; stop(); p.paused = true; ev.dispatchEvent(new Event("pause")); };
    return p;
  }

  // ---------------------------------------------------------------- settings
  // A form over _system/config.json. Nothing here needs a terminal or Claude.
  var COLOR_CHOICES = ["lesson", "probe", "checkpoint", "reading", "project", "mock", "coral", "amber", "green"];
  var setDraft = null;

  function openSettings(section) {
    Promise.all([
      fetch("/api/config", { cache: "no-store" }).then(function (r) { return r.json(); }),
      fetch("/api/themes", { cache: "no-store" }).then(function (r) { return r.json(); }).catch(function () { return { themes: [] }; })
    ]).then(function (both) {
      var j = both[0];
      setDraft = JSON.parse(JSON.stringify(j.config));
      setDraft.__defaults = j.defaults;
      setRooms = both[1].themes || [];
      paintSettings(j.error);
      openOverlay("settings");
      // focus now, not on a timer: a delayed focus steals the caret from whatever you started typing in
      var target = section && document.getElementById("set-" + section);
      if (target) target.scrollIntoView({ block: "start" });
      else $("#set-name").focus();
    }).catch(function () { toast("Couldn't load your settings. Is the server running?"); });
  }

  function fieldRow(label, input, hint) {
    return '<label class="set-field"><span class="field-label">' + label + "</span>" + input + (hint ? '<small class="set-hint">' + hint + "</small>" : "") + "</label>";
  }
  function colorSelect(val, attr) {
    var custom = /^#/.test(val);
    return '<span class="set-color"><select ' + attr + ' data-color-select aria-label="Colour">' + COLOR_CHOICES.map(function (c) {
      return '<option value="' + c + '"' + (c === val ? " selected" : "") + ">" + c + "</option>";
    }).join("") + '<option value="custom"' + (custom ? " selected" : "") + ">custom…</option></select>" +
      '<input type="color" ' + attr + ' data-color-hex value="' + (custom ? val : "#888888") + '"' + (custom ? "" : " hidden") + ' aria-label="Custom colour"></span>';
  }

  var setRooms = [];
  function roomPicks(c) {
    return setRooms.map(function (t) {
      var bad = t.errors && t.errors.length;
      return '<label class="set-pick' + (bad ? " set-bad" : "") + '"><input type="radio" name="set-theme" value="' + esc(t.id) + '"' +
        (c.theme === t.id ? " checked" : "") + (bad ? " disabled" : "") + "><b>" + esc((t.icon ? t.icon + " " : "") + t.name) + "</b><small>" +
        (bad ? "Can't open: " + esc(t.errors[0]) + (t.errors.length > 1 ? " (+" + (t.errors.length - 1) + " more, run <code>edu4self check</code>)" : "")
             : esc(t.about || "") + (t.builtin ? "" : " <i>yours</i>")) + "</small></label>";
    }).join("");
  }

  function paintSettings(err) {
    var c = setDraft, D = c.__defaults, voices = Object.keys(VOICE_DEFAULTS).filter(function (v) { return v !== "you"; });
    var kinds = c.blocks.kinds.map(function (k, i) {
      return '<div class="set-kind" data-kind="' + i + '"><span class="set-sw" style="--c:' + (/^#/.test(k.color) ? k.color : "var(--" + k.color + ")") + '"></span>' +
        '<input type="text" maxlength="24" value="' + esc(k.label) + '" data-k="label" aria-label="Block name">' +
        '<input type="number" min="1" max="240" value="' + (k.minutes || "") + '" placeholder="min" data-k="minutes" aria-label="Default minutes" title="Minutes this kind starts with (blank = whatever duration is picked)">' +
        colorSelect(k.color, 'data-k="color"') +
        '<button class="icon-btn" type="button" data-kind-del aria-label="Remove ' + esc(k.label) + '"' + (c.blocks.kinds.length < 2 ? " disabled" : "") + ">✕</button></div>";
    }).join("");
    var presets = [0, 1, 2, 3].map(function (i) {
      return '<input type="number" min="1" max="240" data-preset="' + i + '" value="' + (c.blocks.presets[i] || "") + '" aria-label="Duration ' + (i + 1) + '" placeholder="–">';
    }).join("");
    var voiceRows = voices.map(function (v) {
      var o = c.bar.voices[v] || {};
      return '<div class="set-voice"><span class="set-sw" style="--c:' + esc(o.color || VOICE_DEFAULTS[v].c) + '"></span>' +
        '<input type="text" maxlength="30" data-voice="' + v + '" value="' + esc(o.name || "") + '" placeholder="' + esc(VOICE_DEFAULTS[v].name) + '" aria-label="Name for ' + esc(VOICE_DEFAULTS[v].name) + '">' +
        '<input type="color" data-voice-color="' + v + '" value="' + esc(o.color || VOICE_DEFAULTS[v].c) + '" aria-label="Colour for ' + esc(VOICE_DEFAULTS[v].name) + '"><code>' + v + "</code></div>";
    }).join("");
    var m = c.music, src = m.source || (m.file ? "file" : "scape"), scape = SCAPES[m.scape] ? m.scape : "night";
    m.stream = m.stream || { url: "", name: "" };
    var station = m.stream.url ? STATIONS.map(function (st) { return st.url; }).indexOf(m.stream.url) : -1;
    if (station < 0 && m.stream.url) station = "other";
    $("#set-body").innerHTML =
      (err ? '<p class="set-warn">' + esc(err) + ". Saving here writes a fresh, valid file.</p>" : "") +
      '<h3 id="set-you">You</h3>' +
      fieldRow("Your name", '<input type="text" id="set-name" maxlength="60" value="' + esc(c.name) + '" placeholder="' + esc((DATA && DATA.state && DATA.state.learner) || "there") + '">', "How the dashboard greets you.") +
      '<div class="set-field"><span class="field-label">Default look</span><div class="set-seg" role="radiogroup">' +
        ["bar", "classic"].map(function (v) { return '<label><input type="radio" name="set-view" value="' + v + '"' + (c.view === v ? " checked" : "") + "> " + (v === "bar" ? "✦ Your room" : "☰ Classic") + "</label>"; }).join("") +
      '</div><small class="set-hint">The button at the top still switches; each browser remembers its last choice.</small></div>' +

      '<h3 id="set-room">Room</h3>' +
      '<p class="set-hint">Where you study. Each room has its own layout, colours, voices and jokes; your goals, blocks and lessons stay the same. ' +
        'To make your own, ask Claude for one (it follows <code>docs/THEMES.md</code>).</p>' +
      '<div class="set-rooms" role="radiogroup" aria-label="Room">' + roomPicks(c) + "</div>" +
      '<label class="set-check"><input type="checkbox" id="set-theme-lessons"' + (c.theme_lessons !== false ? " checked" : "") + "> Lessons wear the room's look (off: the plain default lesson pages)</label>" +

      '<h3 id="set-goals">Goals</h3>' +
      '<div class="set-two">' +
        fieldRow("Focused minutes a day", '<input type="number" id="set-day" min="10" max="960" value="' + c.goals.day_minutes + '">') +
        fieldRow("Days a week", '<input type="number" id="set-week" min="1" max="7" value="' + c.goals.week_days + '">') +
      "</div>" +

      '<label class="set-check"><input type="checkbox" id="set-gifts"' + (c.gifts === true ? " checked" : "") + "> Gifts: when you win a week or finish a die, Claude makes you something from what you proved (one short run on your Claude account)</label>" +

      '<h3 id="set-reminders">Reminders</h3>' +
      '<p class="set-hint">If you\'ve been away, a short mail after 3, 7, 15 and 30 days, then once a month: what you\'ve done so far, and one small thing to do today. ' +
        "Every Sunday evening, a recap of your week (it's also saved in <code>recaps/</code>).</p>" +
      '<label class="set-check"><input type="checkbox" id="set-rem-mail"' + (!c.reminders || c.reminders.mail !== false ? " checked" : "") + (mailReady() ? "" : " disabled") + "> Mail me when I've been away" +
        (mailReady() ? "" : ' <small class="set-hint">not set up: run <code>./edu4self mail setup</code> in a terminal</small>') + "</label>" +
      mailErrors() +

      '<h3 id="set-record">Your work record</h3>' +
      '<p class="set-hint">Every time you run an exercise\'s checker, its output and a copy of your code are saved in the exercise folder (<code>trace/</code>), ' +
        "and so is every hint you open here. When you hand the exercise in, Claude reads them in order to see where you really got stuck, not just the final answer, " +
        "and plans what comes next from that. It all stays on your computer, and other AI tools never see it.</p>" +
      '<div id="set-trace"></div>' +

      '<h3 id="set-blocks">Focus blocks</h3>' +
      '<div class="set-field"><span class="field-label">Durations to pick from (minutes)</span><div class="set-presets">' + presets + "</div></div>" +
      '<div class="set-field"><span class="field-label">Kinds of block</span><div class="set-kinds">' + kinds + "</div>" +
        '<button class="btn btn-ghost btn-sm" type="button" id="set-kind-add"' + (c.blocks.kinds.length >= 8 ? " disabled" : "") + ">+ Add a kind</button>" +
        '<small class="set-hint">Name, starting minutes (optional) and colour. Old blocks of a removed kind stay on your die in grey.</small></div>' +

      '<h3 id="set-water">Water</h3>' +
      '<div class="set-seg" role="radiogroup">' + [15, 30, 0].map(function (v) {
        return '<label><input type="radio" name="set-water" value="' + v + '"' + (c.water.every === v ? " checked" : "") + "> " + (v ? "every " + v + " min" : "off") + "</label>";
      }).join("") + "</div>" +

      '<h3 id="set-music">Music</h3>' +
      '<p class="set-hint">What the jukebox in the bar plays.</p>' +
      '<div class="set-src" role="radiogroup" aria-label="Music source">' +
        [["scape", "Soundscape", "Made live in your browser. Offline, nothing to download."],
         ["radio", "Radio", "A live station from the internet."],
         ["file", "Your own track", "An audio file you own, on loop."]].map(function (o) {
          return '<label class="set-src-opt"><input type="radio" name="set-mu-src" value="' + o[0] + '"' + (src === o[0] ? " checked" : "") + '>' +
            "<b>" + o[1] + "</b><small>" + o[2] + "</small></label>";
        }).join("") + "</div>" +
      '<div class="set-mu-pane" data-pane="scape"' + (src === "scape" ? "" : " hidden") + ">" +
        Object.keys(SCAPES).map(function (id) {
          return '<label class="set-pick"><input type="radio" name="set-mu-scape" value="' + id + '"' + (scape === id ? " checked" : "") + "><b>" + esc(SCAPES[id].name) + "</b><small>" + esc(SCAPES[id].sub) + "</small></label>";
        }).join("") +
      "</div>" +
      '<div class="set-mu-pane" data-pane="radio"' + (src === "radio" ? "" : " hidden") + ">" +
        STATIONS.map(function (st, i) {
          return '<label class="set-pick"><input type="radio" name="set-mu-station" value="' + i + '"' + (station === i ? " checked" : "") + "><b>" + esc(st.name) + "</b><small>" + esc(st.note) + "</small></label>";
        }).join("") +
        '<label class="set-pick"><input type="radio" name="set-mu-station" value="other"' + (station === "other" ? " checked" : "") + "><b>Another station</b><small>paste its stream address</small></label>" +
        '<div class="set-two">' +
          fieldRow("Stream address", '<input type="url" id="set-mu-url" maxlength="500" placeholder="https://…" value="' + esc(station === "other" ? m.stream.url : "") + '">') +
          fieldRow("Name", '<input type="text" id="set-mu-sname" maxlength="60" value="' + esc(station === "other" ? m.stream.name : "") + '">') +
        "</div>" +
        '<small class="set-hint">Radio is the one thing here that uses the internet: while it plays, this page connects to the station. ' +
          'Radio Paradise is listener-supported and ad-free; if it keeps you company, <a href="https://radioparadise.com" target="_blank" rel="noopener">radioparadise.com</a> takes donations.</small>' +
      "</div>" +
      '<div class="set-mu-pane" data-pane="file"' + (src === "file" ? "" : " hidden") + ">" +
      (m.file ? '<div class="set-track"><b>' + esc(m.title || m.file) + '</b><code>' + esc(m.file) + '</code><button class="btn btn-ghost btn-sm" type="button" id="set-mu-del">Remove</button></div>'
              : '<p class="set-hint">No track yet. Pick a file and it starts playing in the bar, on loop, remembering where it stopped.</p>') +
      '<label class="set-upload"><input type="file" id="set-mu-file" accept="audio/*,.m4a,.mp3,.ogg,.opus,.wav,.flac,.aac,.webm"><span class="btn btn-soft btn-sm">' + (m.file ? "Replace the track…" : "Choose an audio file…") + "</span>" +
        '<span class="set-prog" id="set-mu-prog" hidden><i></i></span></label>' +
      '<small class="set-hint">Any audio file you own, up to 1 GB. It is copied into <code>_system/music/</code> and never leaves this computer.</small>' +
      '<div class="set-two">' +
        fieldRow("Title", '<input type="text" id="set-mu-title" maxlength="80" value="' + esc(m.title) + '">') +
        fieldRow("Subtitle", '<input type="text" id="set-mu-sub" maxlength="80" value="' + esc(m.subtitle) + '" placeholder="artist, album, mood">') +
      "</div>" +
      "</div>" +
      '<label class="set-check"><input type="checkbox" id="set-mu-auto"' + (m.autoplay ? " checked" : "") + "> Start playing when the bar opens (browsers still need one click first)</label>" +

      '<h3 id="set-bar">Sign, jokes and voices</h3>' +
      fieldRow("Names on the neon sign", '<textarea id="set-names" rows="5">' + esc(c.bar.names.map(function (n) { return n[0] + (n[1] ? " | " + n[1] : ""); }).join("\n")) + "</textarea>",
        "One per line: <code>Name | tagline</code>. Click the sign in the bar to cycle through them. Other rooms bring their own names.") +
      '<label class="set-check"><input type="checkbox" id="set-gags"' + (c.bar.gags ? " checked" : "") + "> Room jokes (a new one every 40 minutes)</label>" +
      fieldRow("Your own lines", '<textarea id="set-lines" rows="4" placeholder="regular: The coffee machine has been broken since the last exam.">' + esc(c.bar.lines.map(function (l) { return l.voice + ": " + l.text; }).join("\n")) + "</textarea>",
        "One per line, <code>voice: text</code>. They rotate in with the jokes. Voices: " + voices.map(function (v) { return "<code>" + v + "</code>"; }).join(" ") + ".") +
      '<div class="set-field"><span class="field-label">Voices</span><div class="set-voices">' + voiceRows + '</div><small class="set-hint">Rename any voice or change its colour. Leave a name blank for the default.</small></div>' +

      '<h3 id="set-notes">Notes</h3>' +
      '<label class="set-check"><input type="checkbox" id="set-obs"' + (c.obsidian.enabled ? " checked" : "") + "> Open notes (.md files) in Obsidian</label>" +
      fieldRow("Obsidian vault name", '<input type="text" id="set-obs-vault" maxlength="120" value="' + esc(c.obsidian.vault) + '" placeholder="' + esc((DATA && DATA.server && DATA.server.vault) || "") + '">', "Off: notes open as plain text in the browser.");
    $("#set-error").hidden = true;
    paintTraceSettings(false);
  }

  // read the form back into the draft
  function readSettings() {
    var c = setDraft;
    c.name = $("#set-name").value;
    var view = document.querySelector('input[name="set-view"]:checked'); if (view) c.view = view.value;
    var room = document.querySelector('input[name="set-theme"]:checked'); if (room) c.theme = room.value;
    c.theme_lessons = $("#set-theme-lessons").checked;
    c.gifts = $("#set-gifts").checked;
    c.reminders = { mail: $("#set-rem-mail").checked };
    c.goals.day_minutes = Math.round(Number($("#set-day").value));
    c.goals.week_days = Math.round(Number($("#set-week").value));
    c.blocks.presets = [].map.call(document.querySelectorAll("[data-preset]"), function (i) { return Math.round(Number(i.value)); }).filter(function (v) { return v > 0; });
    document.querySelectorAll(".set-kind").forEach(function (row) {
      var k = c.blocks.kinds[Number(row.dataset.kind)];
      k.label = row.querySelector('[data-k="label"]').value;
      var mins = row.querySelector('[data-k="minutes"]').value;
      if (mins) k.minutes = Math.round(Number(mins)); else delete k.minutes;
      var sel = row.querySelector("[data-color-select]").value;
      k.color = sel === "custom" ? row.querySelector("[data-color-hex]").value : sel;
    });
    var water = document.querySelector('input[name="set-water"]:checked'); if (water) c.water.every = Number(water.value);
    var msrc = document.querySelector('input[name="set-mu-src"]:checked'); if (msrc) c.music.source = msrc.value;
    var msc = document.querySelector('input[name="set-mu-scape"]:checked'); if (msc) c.music.scape = msc.value;
    var mst = document.querySelector('input[name="set-mu-station"]:checked');
    if (mst && mst.value === "other") c.music.stream = { url: $("#set-mu-url").value.trim(), name: $("#set-mu-sname").value.trim() };
    else if (mst) c.music.stream = { url: STATIONS[Number(mst.value)].url, name: STATIONS[Number(mst.value)].name };
    c.music.title = $("#set-mu-title").value;
    c.music.subtitle = $("#set-mu-sub").value;
    c.music.autoplay = $("#set-mu-auto").checked;
    c.bar.names = $("#set-names").value.split("\n").map(function (l) { return l.trim(); }).filter(Boolean).map(function (l) {
      var i = l.indexOf("|"); return i < 0 ? [l, ""] : [l.slice(0, i).trim(), l.slice(i + 1).trim()];
    });
    c.bar.gags = $("#set-gags").checked;
    c.bar.lines = $("#set-lines").value.split("\n").map(function (l) { return l.trim(); }).filter(Boolean).map(function (l) {
      var m = /^([a-z]+)\s*:\s*(.+)$/.exec(l);
      return m ? { voice: m[1], text: m[2] } : { voice: "regular", text: l };
    });
    var vo = {};
    document.querySelectorAll("[data-voice]").forEach(function (inp) {
      var v = inp.dataset.voice, col = document.querySelector('[data-voice-color="' + v + '"]').value, e = {};
      if (inp.value.trim()) e.name = inp.value.trim();
      if (col.toLowerCase() !== VOICE_DEFAULTS[v].c.toLowerCase()) e.color = col;
      if (e.name || e.color) vo[v] = e;
    });
    c.bar.voices = vo;
    c.obsidian.enabled = $("#set-obs").checked;
    c.obsidian.vault = $("#set-obs-vault").value;
    var out = JSON.parse(JSON.stringify(c)); delete out.__defaults;
    return out;
  }

  function postConfig(body) {
    return fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "could not save"); return j; }); });
  }

  function setError(msg) { var e = $("#set-error"); e.textContent = msg; e.hidden = false; e.scrollIntoView({ block: "nearest" }); }

  function slug(label, taken) {
    var base = (label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "kind").replace(/^[^a-z]+/, "") || "kind";
    base = base.slice(0, 20); var id = base, n = 2;
    while (taken[id]) id = base + "-" + n++;
    return id;
  }

  $("#set-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var c = readSettings(), taken = {};
    c.blocks.kinds.forEach(function (k) { if (k.id) taken[k.id] = true; });
    c.blocks.kinds.forEach(function (k) { if (!k.id) { k.id = slug(k.label, taken); taken[k.id] = true; } });
    var btn = $("#set-save"); btn.disabled = true; btn.textContent = "Saving…";
    postConfig({ config: c }).then(function () {
      closeOverlay($("#settings"));
      toast("<span>✓</span><span><b>Settings saved.</b></span>", 3500);
      return load();
    }).catch(function (e) { setError("Not saved: " + e.message + "."); })
      .then(function () { btn.disabled = false; btn.textContent = "Save"; });
  });
  $("#set-reset").addEventListener("click", function () {
    if (!confirm("Reset every setting to its default? Your music file stays.")) return;
    postConfig({ reset: true }).then(function () {
      try { localStorage.removeItem(VIEW_KEY); localStorage.removeItem(WATER_KEY); localStorage.removeItem(NAME_KEY); } catch (e) {}
      closeOverlay($("#settings")); toast("Settings are back to the defaults."); return load();
    }).catch(function (e) { setError(e.message); });
  });
  $("#set-body").addEventListener("click", function (ev) {
    if (ev.target.id === "set-kind-add") {
      readSettings();
      setDraft.blocks.kinds.push({ id: "", label: "New kind", color: COLOR_CHOICES[setDraft.blocks.kinds.length % COLOR_CHOICES.length] });
      paintSettings(); var rows = document.querySelectorAll(".set-kind"); rows[rows.length - 1].querySelector("input").select();
    } else if (ev.target.hasAttribute("data-kind-del")) {
      readSettings();
      setDraft.blocks.kinds.splice(Number(ev.target.closest(".set-kind").dataset.kind), 1);
      paintSettings();
    } else if (ev.target.id === "set-trace-del" || ev.target.id === "set-trace-no") {
      paintTraceSettings(ev.target.id === "set-trace-del");
    } else if (ev.target.id === "set-trace-yes") {
      deleteTraces();
    } else if (ev.target.id === "set-mu-del") {
      if (!confirm("Remove the track from the jukebox and delete its file from _system/music/?")) return;
      postConfig({ config: DATA.config, remove_music: true }).then(function (j) {
        setDraft.music = j.config.music; readSettings(); paintSettings(); load();
      }).catch(function (e) { setError(e.message); });
    }
  });
  $("#set-body").addEventListener("change", function (ev) {
    var t = ev.target;
    if (t.hasAttribute("data-color-select")) {
      var hex = t.parentNode.querySelector("[data-color-hex]"); hex.hidden = t.value !== "custom";
      t.closest(".set-kind").querySelector(".set-sw").style.setProperty("--c", t.value === "custom" ? hex.value : "var(--" + t.value + ")");
    } else if (t.hasAttribute("data-color-hex")) {
      t.closest(".set-kind").querySelector(".set-sw").style.setProperty("--c", t.value);
    } else if (t.hasAttribute("data-voice-color")) {
      t.parentNode.querySelector(".set-sw").style.setProperty("--c", t.value);
    } else if (t.name === "set-mu-src") {
      document.querySelectorAll(".set-mu-pane").forEach(function (p) { p.hidden = p.dataset.pane !== t.value; });
    } else if (t.id === "set-mu-url" && t.value.trim()) {
      var o = document.querySelector('input[name="set-mu-station"][value="other"]'); if (o) o.checked = true;
    } else if (t.id === "set-mu-file" && t.files[0]) uploadMusic(t.files[0]);
  });

  // straight to disk, with a progress bar; saved as soon as it lands
  function uploadMusic(file) {
    var prog = $("#set-mu-prog"), bar = prog.querySelector("i"), x = new XMLHttpRequest();
    if (file.size > 1024 * 1024 * 1024) return setError("That file is over 1 GB.");
    prog.hidden = false; bar.style.width = "0%";
    x.open("POST", "/api/music");
    x.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    x.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    x.upload.onprogress = function (e) { if (e.lengthComputable) bar.style.width = (100 * e.loaded / e.total).toFixed(1) + "%"; };
    x.onload = function () {
      var j = {}; try { j = JSON.parse(x.responseText); } catch (e) {}
      if (x.status >= 300) { prog.hidden = true; return setError("Upload failed: " + (j.error || x.status)); }
      readSettings();
      setDraft.music = j.config.music;
      paintSettings();
      toast("<span>♪</span><span><b>" + esc(j.config.music.title || j.config.music.file) + "</b> is in the jukebox.</span>", 4000);
      load();
    };
    x.onerror = function () { prog.hidden = true; setError("Upload failed. Is the server running?"); };
    x.send(file);
  }

  // ---------------------------------------------------------------- loading
  function load() {
    return fetch("/api/state", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (json) {
        var stamp = json.state ? json.state.updated : json.error;
        var changed = lastStamp && stamp !== lastStamp;
        DATA = json;
        lastStamp = stamp;
        render();
        paintClaude();
        paintMailAlert();
        if (changed) toast("<span>✦</span><span><b>Claude updated your dashboard.</b> Take a look at what's next.</span>", 6000);
        if (readJSON(UNSENT_KEY)) flushUnsent();
        checkProofs();
      })
      .catch(function () {
        if (DATA) { DATA.__offline = true; renderStatus(); }
        else {
          $("#app").innerHTML = '<div class="card error-card"><h2>Can\'t reach the dashboard server</h2>' +
            '<p>If you installed it as a service it starts on its own when you log in. To start or restart it, run this in a terminal, from the edu4self folder:</p>' +
            '<pre><code>./edu4self restart</code></pre>' +
            '<p class="muted">This page will keep retrying.</p></div>';
        }
      });
  }

  // ---------------------------------------------------------------- events
  document.addEventListener("click", function (ev) {
    var el = ev.target.closest("[data-submit],[data-withdraw],[data-close],[data-help],[data-go],[data-start-task],[data-note],[data-room],[data-barname],[data-drink],[data-gpu],[data-settings],[data-claude],[data-claude-open],[data-newtopic],[data-ks],[data-hints],[data-hint-n],[data-recall],[data-stuck-hint]");
    if (!el) return;
    if (el.dataset.stuckHint) return stuckHint(el.dataset.stuckHint, Number(el.dataset.n));
    if (el.dataset.recall) return el.dataset.recall === "go" ? openRecall() : recallLater();
    if (el.dataset.claude) return claudeSend(el.dataset.claude);
    if (el.hasAttribute("data-claude-open")) return openClaude();
    if (el.hasAttribute("data-newtopic")) return openNewTopic();
    if (el.dataset.ks) return openTrophy(el.dataset.ks);
    if (el.dataset.hints) return openHints(el.dataset.hints);
    if (el.dataset.hintN) return revealHint(Number(el.dataset.hintN));
    if (el.dataset.settings != null) return openSettings(el.dataset.settings);
    if (el.hasAttribute("data-drink")) return drinkWater();
    if (el.hasAttribute("data-note")) return openNote();
    if (el.dataset.room) { store(ROOM_KEY, el.dataset.room); render(); return window.scrollTo(0, 0); }
    if (el.hasAttribute("data-barname")) { store(NAME_KEY, String(((Number(store(NAME_KEY)) || 0) + 1) % BAR_NAMES.length)); return render(); }
    if (el.dataset.gpu) { if (!blockEl.contains(el)) { pickedDie = Number(el.dataset.gpu); render(); } return; }
    if (el.dataset.startTask) {
      var entry = findTask(el.dataset.startTask);
      if (!entry || active) return;
      pick.block = taskBlock(entry.topic);
      pick.minutes = taskMinutes(entry.topic);
      pick.touched = true;
      paintControls();
      startBlock(entry.task.id);
      return render();
    }
    if (el.dataset.submit) return openSubmit(el.dataset.submit);
    if (el.dataset.withdraw) return withdraw(el.dataset.withdraw);
    if (el.hasAttribute("data-close")) return closeOverlay(el.closest(".overlay"));
    if (el.dataset.help) return openHelp(el.dataset.help);
    if (el.dataset.go) { obStep = Number(el.dataset.go); paintOnboarding(); }
  });
  document.querySelectorAll(".overlay").forEach(function (o) {
    o.addEventListener("mousedown", function (ev) { if (ev.target === o && o.id !== "onboarding") closeOverlay(o); });
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    var open = document.querySelectorAll(".overlay:not([hidden])");
    if (!open.length) return;
    var top = open[open.length - 1];
    if (top.id === "onboarding") finishOnboarding(); else closeOverlay(top);
  });
  $("#submit-form").addEventListener("submit", submitForm);
  $("#btn-help").addEventListener("click", function () { openHelp(); });
  $("#footer-help").addEventListener("click", function (ev) { ev.preventDefault(); openHelp(); });
  $("#btn-note").addEventListener("click", openNote);
  $("#btn-settings").addEventListener("click", function () { openSettings(); });
  $("#btn-view").addEventListener("click", function () {
    store(VIEW_KEY, isBar() ? "classic" : "bar");
    if (DATA) render(); else { document.body.classList.toggle("v-bar", isBar()); paintViewButton(); }
    window.scrollTo(0, 0);
  });
  document.body.classList.toggle("v-bar", isBar());
  paintViewButton();
  $("#ob-next").addEventListener("click", function () { if (obStep < 2) { obStep++; paintOnboarding(); } else finishOnboarding(); });
  $("#ob-back").addEventListener("click", function () { if (obStep > 0) { obStep--; paintOnboarding(); } });
  $("#replay-onboarding").addEventListener("click", function () { closeOverlay($("#help")); showOnboarding(); });
  $("#gift-yes").addEventListener("click", function () { answerGifts(true); });
  $("#mail-alert-ok").addEventListener("click", dismissMailAlert);
  $("#mail-alert-open").addEventListener("click", function () { dismissMailAlert(); openSettings("reminders"); });
  $("#gift-no").addEventListener("click", function () { answerGifts(false); });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) return;
    load();
    if (celebrateNext) showCelebration();
  });

  // deep links: #submit=<task-id>, #hints=<task-id>, #note, #help, #settings, #settings=<section>, #claude, #newtopic
  function followHash() {
    var h = location.hash.slice(1);
    if (!h || !DATA || DATA.error) return;
    if (h.indexOf("submit=") === 0) openSubmit(decodeURIComponent(h.slice(7)));
    else if (h.indexOf("hints=") === 0) openHints(decodeURIComponent(h.slice(6)));
    else if (h === "note") openNote();
    else if (h === "claude") openClaude();
    else if (h === "newtopic") openNewTopic();
    else if (h === "help") openHelp();
    else if (h === "settings" || h.indexOf("settings=") === 0) openSettings(h.slice(9));
    history.replaceState(null, "", location.pathname + location.search);
  }
  window.addEventListener("hashchange", followHash);

  Promise.all([claudePoll(), load()]).then(function () {
    if (claudeOK()) render();
    resumeBlock();
    if (location.hash) return followHash();
    if (!store(ONBOARD_KEY) && !/[?&]noonboard/.test(location.search)) showOnboarding(); else askGifts();
  });
  setInterval(function () { if (!document.hidden) load(); }, POLL_MS);
})();
