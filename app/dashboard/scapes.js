/* edu4self soundscapes: music made live with the Web Audio API. No files, no network.
   EduScapes.start(ctx, destination, id) plays one and returns { stop() }. It works the same in a live
   AudioContext and in an OfflineAudioContext (used to render WAVs for listening and tests). */
(function () {
  "use strict";

  var LIST = {
    night: { name: "Night shift", sub: "electric piano, soft bass, brushes" },
    rain: { name: "Rain on the window", sub: "rain on the glass, slow piano" },
    noise: { name: "Brown noise", sub: "a low, steady hush" }
  };

  // ---------------------------------------------------------------- small helpers
  // seeded random, so an offline render is the same every time
  function rng(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function hz(midi) { return 440 * Math.pow(2, (midi - 69) / 12); }

  function noiseBuffer(ctx, seconds, kind, rand) {
    var n = Math.floor(ctx.sampleRate * seconds), b = ctx.createBuffer(1, n, ctx.sampleRate), d = b.getChannelData(0), last = 0;
    for (var i = 0; i < n; i++) {
      var w = rand() * 2 - 1;
      if (kind === "brown") { last = (last + 0.02 * w) / 1.02; d[i] = last * 3.5; } else d[i] = w;
    }
    return b;
  }

  // a room: a short, dark reverb tail made from decaying noise (the tail is smooth once convolved)
  function room(ctx, seconds, rand) {
    var n = Math.floor(ctx.sampleRate * seconds), b = ctx.createBuffer(2, n, ctx.sampleRate);
    for (var c = 0; c < 2; c++) {
      var d = b.getChannelData(c), lp = 0;
      for (var i = 0; i < n; i++) {
        lp += 0.35 * ((rand() * 2 - 1) - lp);              // darker tail: high end rolled off
        d[i] = lp * Math.pow(1 - i / n, 3.2);
      }
    }
    var conv = ctx.createConvolver(); conv.buffer = b;
    return conv;
  }

  // ---------------------------------------------------------------- instruments
  // electric piano: a sine carrier bent by a sine modulator whose depth fades fast, so each note
  // starts with a soft bell and settles into a round tone (the classic FM e-piano recipe)
  function epiano(ctx, out, midi, t, vel, len) {
    var f = hz(midi), car = ctx.createOscillator(), mod = ctx.createOscillator(), depth = ctx.createGain(), amp = ctx.createGain();
    car.frequency.value = f; mod.frequency.value = f; car.type = mod.type = "sine";
    depth.gain.setValueAtTime(f * 1.6 * vel, t);
    depth.gain.exponentialRampToValueAtTime(f * 0.08, t + 0.35);
    amp.gain.setValueAtTime(0.0001, t);
    amp.gain.exponentialRampToValueAtTime(0.11 * vel, t + 0.008);
    amp.gain.exponentialRampToValueAtTime(0.05 * vel, t + 0.4);
    amp.gain.exponentialRampToValueAtTime(0.0001, t + len);
    mod.connect(depth); depth.connect(car.frequency); car.connect(amp); amp.connect(out);
    car.start(t); mod.start(t); car.stop(t + len + 0.05); mod.stop(t + len + 0.05);
  }

  // felt piano: a few harmonics that die away at different speeds, through a gentle low-pass
  function felt(ctx, out, midi, t, vel) {
    var f = hz(midi), tone = ctx.createBiquadFilter();
    tone.type = "lowpass"; tone.frequency.value = Math.min(4000, f * 6); tone.Q.value = 0.4;
    tone.connect(out);
    [[1, 1, 4.5], [2, 0.35, 2.2], [3, 0.12, 1.2], [4.02, 0.05, 0.7]].forEach(function (p) {
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.type = "sine"; o.frequency.value = f * p[0];
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.09 * vel * p[1], t + 0.012);
      g.gain.exponentialRampToValueAtTime(0.0001, t + p[2]);
      o.connect(g); g.connect(tone); o.start(t); o.stop(t + p[2] + 0.05);
    });
  }

  function bass(ctx, out, midi, t, len) {
    var o = ctx.createOscillator(), g = ctx.createGain();
    o.type = "sine"; o.frequency.value = hz(midi);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.16, t + 0.03);
    g.gain.exponentialRampToValueAtTime(0.09, t + 0.5);
    g.gain.exponentialRampToValueAtTime(0.0001, t + len);
    o.connect(g); g.connect(out); o.start(t); o.stop(t + len + 0.05);
  }

  // a soft kick: a sine that drops in pitch
  function kick(ctx, out, t) {
    var o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.setValueAtTime(110, t); o.frequency.exponentialRampToValueAtTime(48, t + 0.12);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.22, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
    o.connect(g); g.connect(out); o.start(t); o.stop(t + 0.4);
  }

  // a brush: a whisper of band-passed noise, kept very quiet
  function brush(ctx, out, buf, t, vel, offset) {
    var s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    s.buffer = buf; f.type = "bandpass"; f.frequency.value = 5500; f.Q.value = 0.9;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.018 * vel, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    s.connect(f); f.connect(g); g.connect(out); s.start(t, offset); s.stop(t + 0.15);
  }

  // a water drop: a short sine that slides up, the way drops sound on glass
  function drop(ctx, out, t, rand) {
    var o = ctx.createOscillator(), g = ctx.createGain(), f = 900 + rand() * 1500;
    o.frequency.setValueAtTime(f, t); o.frequency.exponentialRampToValueAtTime(f * 1.6, t + 0.05);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.025 + rand() * 0.02, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.07);
    o.connect(g); g.connect(out); o.start(t); o.stop(t + 0.1);
  }

  // ---------------------------------------------------------------- the pieces
  // Each returns a list of patterns: { next: time, step(t) -> time of the next event }.

  function night(ctx, dry, wet, rand) {
    var beat = 60 / 72, bar = beat * 4;
    // ii - V - I - vi in C, jazz voicings in the middle of the keyboard
    var CHORDS = [
      { root: 38, notes: [53, 57, 60, 64] },   // Dm9
      { root: 43, notes: [53, 57, 59, 64] },   // G13
      { root: 36, notes: [52, 55, 59, 62] },   // Cmaj9
      { root: 45, notes: [52, 55, 60, 64] }    // Am9
    ];
    var MELODY = [64, 67, 69, 72, 74, 76];
    var hush = noiseBuffer(ctx, 1, "white", rand), n = 0;
    return [
      { next: 0, step: function (t) {          // one chord a bar, rolled a little like a hand would
        var c = CHORDS[n % CHORDS.length];
        c.notes.forEach(function (m, i) { epiano(ctx, i % 2 ? wet : dry, m, t + i * 0.018, 0.75 + rand() * 0.2, bar * 0.95); });
        if (rand() < 0.5) c.notes.slice(1).forEach(function (m, i) { epiano(ctx, wet, m, t + beat * 2.5 + i * 0.015, 0.4, beat * 1.4); });
        bass(ctx, dry, c.root, t, beat * 1.8); bass(ctx, dry, c.root + (rand() < 0.5 ? 7 : 12), t + beat * 2, beat * 1.6);
        n++;
        return t + bar;
      } },
      { next: bar * 4, step: function (t) {    // a few notes on top, now and then
        if (rand() < 0.55) epiano(ctx, wet, MELODY[Math.floor(rand() * MELODY.length)], t, 0.45, beat * 2);
        return t + beat * (rand() < 0.5 ? 1.5 : 2);
      } },
      { next: 0, step: function (t) {          // kick on 1 and 3, brushes with a lazy swing
        kick(ctx, dry, t); kick(ctx, dry, t + beat * 2.5);
        for (var i = 0; i < 4; i++) brush(ctx, dry, hush, t + beat * i + (i % 2 ? beat * 0.12 : 0), i % 2 ? 1 : 0.6, rand() * 0.5);
        return t + bar;
      } }
    ];
  }

  function rain(ctx, dry, wet, rand, keep) {
    // rain in three layers: a steady wash that swells now and then, a low rumble, and close patter
    // made of tiny droplet grains; the piano sits on top
    var white = noiseBuffer(ctx, 4, "white", rand);
    var wash = ctx.createBufferSource(), hp = ctx.createBiquadFilter(), lp = ctx.createBiquadFilter(), wg = ctx.createGain();
    wash.buffer = white; wash.loop = true;
    hp.type = "highpass"; hp.frequency.value = 400; lp.type = "lowpass"; lp.frequency.value = 3200; wg.gain.value = 0.05;
    var gust = ctx.createOscillator(), gd = ctx.createGain();
    gust.frequency.value = 0.07; gd.gain.value = 0.018; gust.connect(gd); gd.connect(wg.gain); gust.start();
    wash.connect(hp); hp.connect(lp); lp.connect(wg); wg.connect(dry); wash.start();
    var rum = ctx.createBufferSource(), rl = ctx.createBiquadFilter(), rg = ctx.createGain();
    rum.buffer = noiseBuffer(ctx, 6, "brown", rand); rum.loop = true;
    rl.type = "lowpass"; rl.frequency.value = 260; rg.gain.value = 0.12;
    rum.connect(rl); rl.connect(rg); rg.connect(dry); rum.start();
    keep.push(wash, gust, rum);
    // slow piano in D major pentatonic, leaning on the low and middle notes
    var SCALE = [50, 54, 57, 59, 62, 64, 66, 69, 71, 74];
    return [
      { next: 0.3, step: function (t) {
        var i = Math.floor(Math.pow(rand(), 1.4) * SCALE.length), v = 0.6 + rand() * 0.35;
        felt(ctx, wet, SCALE[i], t, v);
        if (rand() < 0.3) felt(ctx, wet, SCALE[Math.max(0, i - 2)] - 12, t + 0.02, v * 0.7);   // a low note under it, sometimes
        return t + 1.1 + rand() * 2.2;
      } },
      { next: 0.2, step: function (t) {        // patter: droplets close to the window
        var s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain(), len = 0.006 + rand() * 0.012;
        s.buffer = white; f.type = "bandpass"; f.frequency.value = 1800 + rand() * 5000; f.Q.value = 1.5;
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.02 + rand() * 0.05, t + 0.002);
        g.gain.exponentialRampToValueAtTime(0.0001, t + len);
        s.connect(f); f.connect(g); g.connect(dry); s.start(t, rand() * 3); s.stop(t + len + 0.01);
        return t + 0.012 + rand() * 0.05;
      } },
      { next: 0.5, step: function (t) {        // the odd heavier drop on the glass
        drop(ctx, dry, t, rand);
        return t + 0.4 + rand() * 2.5;
      } }
    ];
  }

  function noise(ctx, dry, wet, rand, keep) {
    var s = ctx.createBufferSource(), lp = ctx.createBiquadFilter(), g = ctx.createGain();
    s.buffer = noiseBuffer(ctx, 4, "brown", rand); s.loop = true;
    lp.type = "lowpass"; lp.frequency.value = 700; g.gain.value = 0.9;
    s.connect(lp); lp.connect(g); g.connect(dry); s.start(); keep.push(s);
    return [];
  }

  var PIECES = { night: night, rain: rain, noise: noise };

  // ---------------------------------------------------------------- playing
  function start(ctx, destination, id, seed) {
    var rand = rng(seed || 7), t0 = ctx.currentTime + 0.05, nodes = [];
    var master = ctx.createGain(), limit = ctx.createDynamicsCompressor();
    limit.threshold.value = -10; limit.knee.value = 8; limit.ratio.value = 6; limit.attack.value = 0.005; limit.release.value = 0.2;
    master.connect(limit); limit.connect(destination);
    var dry = ctx.createGain(), wet = ctx.createGain(), verb = room(ctx, id === "rain" ? 4 : 2.6, rand), send = ctx.createGain();
    dry.connect(master);
    wet.connect(master); wet.connect(send); send.gain.value = id === "rain" ? 0.9 : 0.45;
    send.connect(verb); verb.connect(master);
    nodes.push(master, limit, dry, wet, send, verb);

    var keep = [], patterns = (PIECES[id] || night)(ctx, dry, wet, rand, keep);
    patterns.forEach(function (p) { p.next += t0; });
    function schedule(until) {
      patterns.forEach(function (p) { while (p.next < until) p.next = p.step(p.next); });
    }

    var timer = null;
    if (typeof OfflineAudioContext !== "undefined" && ctx instanceof OfflineAudioContext) {
      schedule(ctx.length / ctx.sampleRate);            // a render: everything up front
    } else {
      schedule(ctx.currentTime + 1);
      timer = setInterval(function () { schedule(ctx.currentTime + 1); }, 250);   // live: a second ahead
    }
    return {
      stop: function () {
        clearInterval(timer);
        master.gain.setTargetAtTime(0, ctx.currentTime, 0.15);
        setTimeout(function () {
          keep.forEach(function (s) { try { s.stop(); } catch (e) {} });
          nodes.forEach(function (n) { try { n.disconnect(); } catch (e) {} });
        }, 800);
      }
    };
  }

  window.EduScapes = { list: LIST, start: start };
})();
