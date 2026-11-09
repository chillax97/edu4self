// Shared setup for the browser tests: a throwaway vault, a server on a spare port, and Chrome.
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const here = path.dirname(fileURLToPath(import.meta.url));
export const ENGINE = path.resolve(here, "..", "..");
const CLI = path.join(ENGINE, "edu4self");

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
];

export function chromePath() {
  const p = CHROME_CANDIDATES.find((c) => c && fs.existsSync(c));
  if (!p) throw new Error("No Chrome found. Set CHROME_PATH.");
  return p;
}

// A new vault in a temp folder. Nothing outside it (or the temp config home) is touched.
export function makeVault(name = "Tester", extra = []) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "edu4self-e2e-"));
  // Claude Code is off unless a test brings its own stand-in, so a real install on this machine changes nothing
  const env = { ...process.env, EDU4SELF_CONFIG_HOME: path.join(dir, "cfg"), EDU4SELF_CLAUDE: path.join(dir, "no-claude"), EDU4SELF_REMINDERS: "0" };   // no real reminder mail from test servers
  const vault = path.join(dir, "vault");
  execFileSync("python3", [CLI, "init", vault, "--name", name, ...extra], { env, stdio: "pipe" });
  return { dir, vault, env };
}

// A port nothing is listening on, so a stray server can never answer for ours
export function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => { const p = srv.address().port; srv.close(() => resolve(p)); });
  });
}

export async function startServer(v, port) {
  const proc = spawn("python3", [CLI, "serve", "--vault", v.vault, "--port", String(port)], { env: v.env, stdio: "pipe" });
  let log = "";
  proc.stderr.on("data", (d) => (log += d));
  proc.stdout.on("data", (d) => (log += d));
  for (let i = 0; i < 60; i++) {
    try {
      if (proc.exitCode !== null) break;   // ours died (port taken?); don't trust whoever answers
      const r = await fetch(`http://127.0.0.1:${port}/api/health`);
      if (r.ok && (await r.json()).version) return { proc, url: `http://127.0.0.1:${port}/`, log: () => log };
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  proc.kill();
  throw new Error("server didn't start:\n" + log);
}

export async function stopServer(s) {
  if (!s || s.proc.exitCode !== null) return;
  const done = new Promise((r) => s.proc.once("exit", r));
  s.proc.kill("SIGINT");
  await done;
}

export async function launch() {
  return puppeteer.launch({
    executablePath: chromePath(),
    headless: true,
    args: ["--autoplay-policy=no-user-gesture-required", "--no-sandbox", "--mute-audio"],
  });
}

// Pin the page clock to `hour`:30 today (local time); it keeps ticking from there. Some of the bar's lines depend on
// the time of day (the volition voice, "Willpower"/"Grit", speaks only 5-9 and after 21), so a test that expects
// one must not depend on when it runs. Call before the first goto. Only the page clock moves, not the server's.
export async function pinClock(page, hour) {
  await page.evaluateOnNewDocument((h) => {
    const Real = Date, t = new Real(); t.setHours(h, 30, 0, 0);
    const off = t.getTime() - Real.now();
    class FDate extends Real {
      constructor(...a) { if (a.length) super(...a); else super(Real.now() + off); }
      static now() { return Real.now() + off; }
    }
    window.Date = FDate;
  }, hour);
}

// A page that records console errors and uncaught exceptions.
export async function openPage(browser, url, { width = 1440, height = 1000, view, block = false, hour } = {}) {
  const page = await browser.newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") page.errors.push(m.text()); });
  page.on("dialog", (d) => d.accept());
  await page.setViewport({ width, height });
  if (hour !== undefined) await pinClock(page, hour);
  await page.evaluateOnNewDocument((v, blk) => {
    localStorage.setItem("edu.onboarded.v1", "1"); sessionStorage.setItem("edu.giftask.later", "1");
    if (v) localStorage.setItem("edu.view.v1", v);
    // a focus block already running: the top bar is at its most crowded
    if (blk) { const n = Date.now(); localStorage.setItem("edu.block.v1", JSON.stringify({ block: "lessons", minutes: 50, start: n - 60000, end: n + 49 * 60000, water: 15, served: 0, drunk: 0 })); }
  }, view || "", block);
  await page.goto(url, { waitUntil: "networkidle0" });
  await page.waitForSelector("#app > :not(#loading)");
  return page;
}

// Close like a person closing a tab: navigating away fires pagehide, which hands the music back.
// (puppeteer's close() alone skips it, and the next tab would politely stay quiet for up to 10 s.)
export async function closePage(page) {
  await page.goto("about:blank");
  await page.close();
}

// A short, valid WAV file: a few seconds of a quiet 440 Hz tone, named "Test Tone.wav" unless you pick a name.
export function wavFile(dir, seconds = 3, name = "Test Tone.wav") {
  const rate = 8000, n = rate * seconds, buf = Buffer.alloc(44 + n * 2);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write("WAVE", 8);
  buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(rate, 24); buf.writeUInt32LE(rate * 2, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write("data", 36); buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) buf.writeInt16LE(Math.round(3000 * Math.sin(2 * Math.PI * 440 * i / rate)), 44 + i * 2);
  const p = path.join(dir, name);
  fs.writeFileSync(p, buf);
  return p;
}

export const readJSON = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
export const readLines = (p) => fs.readFileSync(p, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
