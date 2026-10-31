// The soundscapes, rendered offline with the real scapes.js: musical ones stay clean, none clip, all make sound.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { makeVault, freePort, startServer, stopServer, launch } from "./harness.js";
import { render, measure } from "./scapes.js";

let v, server, browser, page;
before(async () => {
  v = makeVault("Sound"); server = await startServer(v, await freePort()); browser = await launch();
  page = await browser.newPage(); await page.goto(server.url, { waitUntil: "networkidle0" });
});
after(async () => { await browser?.close(); await stopServer(server); fs.rmSync(v.dir, { recursive: true, force: true }); });

// noisiness: 0 = clean tones, 1 = static. Rain is noise by nature and has to be heard (it measures
// ~0.44 with the piano, 0.57 alone); the limit catches it turning into plain static like brown noise (~0.6-0.9).
const LIMITS = { night: 0.12, rain: 0.55, noise: 1 };
for (const id of Object.keys(LIMITS)) {
  test(`soundscape ${id}: audible, no clipping, noisiness under ${LIMITS[id]}`, async () => {
    const [left] = await render(page, id, 12);
    const m = measure(left);
    assert.ok(m.rms > 0.01, `${id} is audible: ${JSON.stringify(m)}`);
    assert.ok(m.peak < 0.98, `${id} doesn't clip: ${JSON.stringify(m)}`);
    assert.ok(m.noisiness < LIMITS[id], `${id} is clean enough: ${JSON.stringify(m)}`);
  });
}
