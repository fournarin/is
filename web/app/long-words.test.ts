/**
 * Text a person typed never widens a screen past the phone it is on.
 *
 * On 2026-09-29 an operator's report with one long unbroken run of characters
 * (a pasted part number, a URL, a key held down) reached the shift lead's board
 * as a proposal. `.board` is a grid, a `1fr` track never shrinks below its
 * content's min-content width, and one unbreakable word made that 94,953px. Every
 * card on the board was cut off at the right edge and the confirm buttons had no
 * visible label, so the whole shift's work could not be read. Every HTTP-level
 * screen check passed, because the HTML was right and the layout was not.
 *
 * So this renders `globals.css` in a real headless Chrome at phone width and
 * measures the page. No new package: Chrome's DevTools protocol over the
 * WebSocket that Node ships. CI runs on ubuntu-latest, which has Chrome; on a
 * machine without it the test is skipped rather than passed, and under CI it
 * fails instead.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

const CHROMES = [
  process.env.CHROME_PATH ?? "",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
];
const chrome = CHROMES.find((path) => path !== "" && existsSync(path));

const PHONE = 390; // the width the screens are designed at (ADR-093)
const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");

// Characters with no break opportunity in them: Thai with no spaces is broken by
// a dictionary, but a run of one letter, a part number or a URL is not.
const LONG = [
  "ข".repeat(400),
  "SN-" + "A1B2C3D4".repeat(40),
  "http://plant.local/" + "x".repeat(300),
].join(" ");

// The shapes the screens are built from, with the class names they use: the
// shift lead's board (`app/board/page.tsx`), the technician's job card
// (`app/work/page.tsx`), and a plain page with an error line.
const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><style>${css}</style></head>
<body><header class="appbar"><div class="appbar-inner"><span class="brand">x</span></div></header>
<main>
  <p class="error" role="alert">${LONG}</p>
  <div class="board">
    <section class="column"><h2>รอคุณยืนยัน <span class="count">1</span></h2>
      <article class="ticket planned"><div class="ticket-head"><span class="machine-small">MC-001</span></div>
        <p>${LONG}</p><p class="muted">${LONG}</p>
        <div class="actions"><form><button class="ok">✓ ยืนยัน</button></form></div>
      </article>
    </section>
    <section class="column"><h2>ช่างกำลังทำ</h2></section>
  </div>
  <section class="card job planned"><p class="machine">MC-001</p><p>${LONG}</p></section>
</main></body></html>`;

async function measure(executable: string): Promise<{ page: number; widest: string }> {
  const profile = mkdtempSync(join(tmpdir(), "pdm-long-words-"));
  // Port 0: Chrome picks a free one and says which on stderr. A fixed port
  // guessed here can be taken, and a CI runner is slower to start than a laptop.
  const browser = spawn(
    executable,
    [
      "--headless=new",
      "--remote-debugging-port=0",
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--no-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      `--window-size=${PHONE},844`,
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );
  let said = "";
  const listening = new Promise<string>((resolve, reject) => {
    browser.stderr.on("data", (chunk: Buffer) => {
      said += chunk.toString();
      const found = /DevTools listening on ws:\/\/[^:]+:(\d+)\//.exec(said);
      if (found?.[1] !== undefined) resolve(found[1]);
    });
    browser.once("exit", (code) => reject(new Error(`Chrome exited (${code}): ${said.slice(-500)}`)));
    setTimeout(
      () => reject(new Error(`Chrome said nothing usable in 60s: ${said.slice(-500)}`)),
      60_000,
    ).unref();
  });
  try {
    const port = await listening;
    let socketUrl: string | undefined;
    for (let attempt = 0; attempt < 300 && socketUrl === undefined; attempt++) {
      try {
        const targets = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()) as {
          type: string;
          webSocketDebuggerUrl: string;
        }[];
        socketUrl = targets.find((target) => target.type === "page")?.webSocketDebuggerUrl;
      } catch {
        // not answering yet
      }
      if (socketUrl === undefined) await new Promise((resolve) => setTimeout(resolve, 100));
    }
    assert.ok(socketUrl, `headless Chrome listed no page: ${said.slice(-500)}`);

    const socket = new WebSocket(socketUrl);
    await new Promise((resolve) => socket.addEventListener("open", resolve));
    let next = 0;
    const waiting = new Map<number, (result: unknown) => void>();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data)) as { id?: number; result?: unknown };
      if (message.id !== undefined) waiting.get(message.id)?.(message.result);
    });
    const send = (method: string, params: object = {}): Promise<unknown> =>
      new Promise((resolve) => {
        next += 1;
        waiting.set(next, resolve);
        socket.send(JSON.stringify({ id: next, method, params }));
      });

    await send("Emulation.setDeviceMetricsOverride", {
      width: PHONE,
      height: 844,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const frame = (await send("Page.getFrameTree")) as { frameTree: { frame: { id: string } } };
    await send("Page.setDocumentContent", { frameId: frame.frameTree.frame.id, html: PAGE });
    const evaluated = (await send("Runtime.evaluate", {
      returnByValue: true,
      expression: `(() => {
        let widest = "";
        let most = 0;
        for (const el of document.querySelectorAll("body *")) {
          const width = el.getBoundingClientRect().width;
          if (width > most) { most = width; widest = el.tagName + "." + el.className; }
        }
        return { page: document.documentElement.scrollWidth, widest: widest + " " + Math.round(most) + "px" };
      })()`,
    })) as { result: { value: { page: number; widest: string } } };
    socket.close();
    return evaluated.result.value;
  } finally {
    const exited = new Promise((resolve) => browser.once("exit", resolve));
    browser.kill();
    await exited;
    rmSync(profile, { recursive: true, force: true, maxRetries: 5 });
  }
}

test("a long unbroken word does not widen any screen past a phone", { skip: chrome === undefined && !process.env.CI }, async () => {
  assert.ok(chrome, "no Chrome to render the stylesheet with, and CI must have one");
  const { page, widest } = await measure(chrome);
  assert.ok(page <= PHONE, `the page is ${page}px wide on a ${PHONE}px phone; widest element: ${widest}`);
});
