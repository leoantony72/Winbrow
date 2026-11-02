// Runs the built renderer in Electron without starting the automation sidecar.
const { app, BrowserWindow } = require("electron");
const { resolve } = require("node:path");
const { mkdirSync, writeFileSync } = require("node:fs");
const assert = require("node:assert/strict");
const output = resolve(__dirname, "../../logs/ui-smoke");
const wait = (ms) => new Promise((done) => setTimeout(done, ms));
const errors = [];
let win;
const deadline = setTimeout(() => {
  console.error("Electron UI smoke timed out");
  app.exit(1);
}, 45000);

app
  .whenReady()
  .then(async () => {
    mkdirSync(output, { recursive: true });
    win = new BrowserWindow({
      show: false,
      width: 1180,
      height: 850,
      webPreferences: { contextIsolation: true, nodeIntegration: false },
    });
    win.webContents.on("console-message", (_event, level, message) => {
      if (level >= 2 && !message.includes("Electron Security Warning"))
        errors.push(message);
    });
    const load = async (query) => {
      await win.loadFile(resolve(__dirname, "../dist/index.html"), { query });
      await wait(1000);
      const result = await win.webContents.executeJavaScript(`({
      text: document.body.innerText,
      viewportHeight: innerHeight,
      overflow: document.documentElement.scrollWidth > innerWidth,
      composer: (() => { const el = document.querySelector('textarea'); if (!el) return null; const r = el.getBoundingClientRect(); return {top:r.top,bottom:r.bottom}; })(),
      phase: document.querySelector('[data-phase]')?.getAttribute('data-phase'),
      island: (() => {const el=document.querySelector('.island'); if(!el)return null; const r=el.getBoundingClientRect(); return {width:r.width,height:r.height,background:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color};})()
    })`);
      assert.equal(result.overflow, false, JSON.stringify({ query, result }));
      return result;
    };
    let page = await load({ win: "dashboard", demo: "idle" });
    assert.match(page.text, /Less busywork/);
    assert.ok(
      page.composer &&
        page.composer.top >= 0 &&
        page.composer.bottom <= page.viewportHeight,
      "Composer must remain visible",
    );
    await win.webContents.executeJavaScript(
      `document.querySelector('.example').click()`,
    );
    assert.ok(
      await win.webContents.executeJavaScript(
        `document.querySelector('textarea').value.length > 0`,
      ),
    );
    writeFileSync(
      resolve(output, "dashboard.png"),
      (await win.webContents.capturePage()).toPNG(),
    );
    page = await load({ win: "dashboard", demo: "done" });
    assert.match(page.text, /Invoice summary/);
    writeFileSync(
      resolve(output, "result.png"),
      (await win.webContents.capturePage()).toPNG(),
    );
    await win.webContents.executeJavaScript(
      `Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Server').click()`,
    );
    assert.match(
      await win.webContents.executeJavaScript("document.body.innerText"),
      /Server activity/,
    );
    const serverLayout = await win.webContents.executeJavaScript(`(() => {
      const root = document.querySelector('.activity');
      const scroller = document.querySelector('.connection-scroll');
      if (!root || !scroller) return null;
      const rootStyle = getComputedStyle(root);
      const scrollStyle = getComputedStyle(scroller);
      return {
        rootDisplay: rootStyle.display,
        rootMinHeight: rootStyle.minHeight,
        scrollOverflow: scrollStyle.overflowY,
        scrollMinHeight: scrollStyle.minHeight,
        rootHeight: root.clientHeight,
        scrollHeight: scroller.clientHeight,
      };
    })()`);
    assert.ok(serverLayout, "Server layout nodes are missing");
    assert.equal(serverLayout.rootDisplay, "flex", JSON.stringify(serverLayout));
    assert.equal(serverLayout.rootMinHeight, "0px", JSON.stringify(serverLayout));
    assert.equal(serverLayout.scrollOverflow, "auto", JSON.stringify(serverLayout));
    assert.equal(serverLayout.scrollMinHeight, "0px", JSON.stringify(serverLayout));
    assert.ok(
      serverLayout.scrollHeight <= serverLayout.rootHeight,
      JSON.stringify(serverLayout),
    );
    const scrollCheck = await win.webContents.executeJavaScript(`(() => {
      const scroller = document.querySelector('.connection-scroll');
      const filler = document.createElement('div');
      filler.style.height = '2400px';
      filler.style.flex = '0 0 auto';
      scroller.appendChild(filler);
      const canScroll = scroller.scrollHeight > scroller.clientHeight;
      scroller.scrollTop = scroller.scrollHeight;
      const scrolled = scroller.scrollTop > 0;
      const top = scroller.scrollTop;
      filler.remove();
      return { canScroll, scrolled, top };
    })()`);
    assert.ok(scrollCheck.canScroll, JSON.stringify(scrollCheck));
    assert.ok(scrollCheck.scrolled, JSON.stringify(scrollCheck));
    for (const state of [
      "idle",
      "listening",
      "speaking",
      "working",
      "confirm",
      "control",
      "done",
      "error",
    ]) {
      for (const open of ["0", "1"]) {
        page = await load({ win: "island", demo: state, open });
        assert.ok(page.island && page.island.height > 20, "Island must render");
        assert.ok(page.island.width <= 460.5, "Island exceeds overlay width");
        if (state === "confirm") assert.match(page.text, /Allow/);
        if (state === "control") assert.match(page.text, /Stop/);
        if (state === "confirm" && open === "1")
          writeFileSync(
            resolve(output, "confirmation.png"),
            (await win.webContents.capturePage()).toPNG(),
          );
      }
    }
    win.setSize(640, 720);
    page = await load({ win: "dashboard", demo: "idle" });
    assert.ok(
      page.composer && page.composer.bottom <= page.viewportHeight,
      "Narrow composer must remain visible",
    );
    writeFileSync(
      resolve(output, "dashboard-narrow.png"),
      (await win.webContents.capturePage()).toPNG(),
    );
    await load({ win: "component-demo" });
    assert.equal(errors.length, 0, errors.join("\n"));
    console.log(
      "PASS: dashboard, results, Server navigation, 16 island layouts, narrow layout, and component demo; no renderer errors",
    );
    console.log("Screenshots: " + output);
  })
  .then(() => {
    clearTimeout(deadline);
    app.quit();
  })
  .catch((error) => {
    console.error(error);
    clearTimeout(deadline);
    app.exit(1);
  });
