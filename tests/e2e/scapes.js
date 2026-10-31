// Renders each soundscape to a WAV and measures it:  node scapes.js [out-dir] [seconds]
// Uses the real scapes.js in Chrome's OfflineAudioContext, so what you hear is what the jukebox plays.
// "noisiness" is spectral flatness inside each octave, weighted by how loud the octave is:
// near 0 = clean tones, near 1 = static. Brown noise is noise on purpose (~0.9).
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch } from "./harness.js";

const OUT = path.resolve(process.argv[2] || "scapes-out");
const SECONDS = Number(process.argv[3] || 30);
const RATE = 44100;

function fft(re, im) {   // in place, radix 2
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const a = -2 * Math.PI / len, wr = Math.cos(a), wi = Math.sin(a);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const ur = re[i + k], ui = im[i + k], vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci, vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr;
        re[i + k] = ur + vr; im[i + k] = ui + vi; re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
        [cr, ci] = [cr * wr - ci * wi, cr * wi + ci * wr];
      }
    }
  }
}

export function measure(x, rate = RATE) {
  const N = 4096; let flat = 0, frames = 0, peak = 0, sq = 0;
  for (const v of x) { peak = Math.max(peak, Math.abs(v)); sq += v * v; }
  for (let s = rate; s + N < x.length; s += N) {          // skip the first second (fade in)
    const re = new Float64Array(N), im = new Float64Array(N);
    for (let i = 0; i < N; i++) re[i] = x[s + i] * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / N));
    fft(re, im);
    let sum = 0, weight = 0;
    for (let lo = 62.5; lo < 8000; lo *= 2) {
      let lg = 0, ar = 0, m = 0;
      for (let k = Math.ceil(lo * N / rate); k < Math.min(N / 2, lo * 2 * N / rate); k++) { const p = re[k] * re[k] + im[k] * im[k] + 1e-30; lg += Math.log(p); ar += p; m++; }
      if (m > 2) { sum += (Math.exp(lg / m) / (ar / m)) * ar; weight += ar; }
    }
    if (weight > 1e-9) { flat += sum / weight; frames++; }
  }
  return { noisiness: +(flat / frames).toFixed(3), peak: +peak.toFixed(3), rms: +Math.sqrt(sq / x.length).toFixed(4) };
}

function wav(left, right, rate) {
  const n = left.length, b = Buffer.alloc(44 + n * 4);
  b.write("RIFF", 0); b.writeUInt32LE(36 + n * 4, 4); b.write("WAVE", 8); b.write("fmt ", 12);
  b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(2, 22); b.writeUInt32LE(rate, 24);
  b.writeUInt32LE(rate * 4, 28); b.writeUInt16LE(4, 32); b.writeUInt16LE(16, 34); b.write("data", 36); b.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) {
    b.writeInt16LE(Math.round(Math.max(-1, Math.min(1, left[i])) * 32767), 44 + i * 4);
    b.writeInt16LE(Math.round(Math.max(-1, Math.min(1, right[i])) * 32767), 46 + i * 4);
  }
  return b;
}

export async function render(page, id, seconds = SECONDS) {
  const ch = await page.evaluate(async (id, seconds, rate) => {
    const ctx = new OfflineAudioContext(2, rate * seconds, rate);
    window.EduScapes.start(ctx, ctx.destination, id, 7);
    const buf = await ctx.startRendering();
    return [0, 1].map((c) => Array.from(buf.getChannelData(c)));
  }, id, seconds, RATE);
  return ch.map((a) => Float32Array.from(a));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const v = makeVault("Render"), server = await startServer(v, await freePort()), browser = await launch();
  const page = await browser.newPage();
  await page.goto(server.url, { waitUntil: "networkidle0" });
  fs.mkdirSync(OUT, { recursive: true });
  for (const id of ["night", "rain", "noise"]) {
    const [l, r] = await render(page, id);
    fs.writeFileSync(path.join(OUT, id + ".wav"), wav(l, r, RATE));
    console.log(id.padEnd(6), JSON.stringify(measure(l)), "→", path.join(OUT, id + ".wav"));
  }
  await browser.close(); await stopServer(server); fs.rmSync(v.dir, { recursive: true, force: true });
}
