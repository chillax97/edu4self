import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, closeBrowser, openPage, closePage, sleep } from "./harness.js";

const OUT = path.join(ENGINE, "docs", "images");
const ROOMS = ["bar", "library", "space", "train", "tea"];
const PAGE = { width: 1440, height: 900, hour: 21, date: "2026-11-20" };

const v = makeVault("Kim");
const server = await startServer(v, await freePort());
const browser = await launch();
const saved = [];

async function setTheme(id) {
  const cfg = (await (await fetch(server.url + "api/config")).json()).config;
  await fetch(server.url + "api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config: { ...cfg, theme: id } }),
  });
}

async function shot(page, rel) {
  await sleep(800);
  if (page.errors.length) throw new Error(rel + ": " + page.errors.join(" | "));
  const p = path.join(OUT, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  await page.screenshot({ path: p });
  saved.push(p);
}

try {
  for (const id of ROOMS) {
    await setTheme(id);
    const page = await openPage(browser, server.url, { ...PAGE, view: "bar" });
    await shot(page, path.join("rooms", id + ".png"));
    if (id === "bar") {
      fs.copyFileSync(path.join(OUT, "rooms", "bar.png"), path.join(OUT, "bar.png"));
      saved.push(path.join(OUT, "bar.png"));
    }
    await closePage(page);
  }

  await setTheme("bar");

  let page = await openPage(browser, server.url, { ...PAGE, view: "classic" });
  await shot(page, "classic.png");
  await closePage(page);

  page = await openPage(browser, server.url, { ...PAGE, view: "bar" });
  await page.click('[data-room="back"]');
  await page.waitForSelector(".room.is-back");
  await shot(page, "backroom.png");
  await closePage(page);

  page = await openPage(browser, server.url, { ...PAGE, view: "bar" });
  await page.click("#btn-settings");
  await page.waitForSelector("#settings:not([hidden]) #set-name");
  await shot(page, "settings.png");
  await closePage(page);
} finally {
  await closeBrowser(browser);
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
}

for (const p of saved) console.log(p);
