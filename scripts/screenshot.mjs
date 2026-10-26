// Screenshot the demo with a scenario rendered: start the server and `google-chrome --headless=new --remote-debugging-port=9333`, then
// node scripts/screenshot.mjs 9333 http://127.0.0.1:8000/ docs/screenshot.png [width]   (prints the footer, horizontal overflow and any JS errors)
const [,, port, url, out, widthArg] = process.argv;
const width = Number(widthArg || 1400), mobile = width < 600;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let targets; for (let i = 0; i < 50; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch { await sleep(200); } }
const page = targets.find(t => t.type === 'page' && t.url === 'about:blank') || targets.find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const pending = new Map(); const errors = [];
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text); if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errors.push(m.params.entry.text + ' ' + (m.params.entry.url||'')); };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width, height: mobile ? 1600 : 1100, deviceScaleFactor: 1, mobile });
await send('Page.navigate', { url }); await sleep(1500);
await send('Runtime.evaluate', { expression: "[...document.querySelectorAll('#scenarios button')][2].click()" }); await sleep(1500);
const footer = await send('Runtime.evaluate', { expression: "document.querySelector('footer').textContent", returnByValue: true });
const overflow = await send('Runtime.evaluate', { expression: "document.documentElement.scrollWidth - window.innerWidth", returnByValue: true });
const result = await send('Runtime.evaluate', { expression: "(document.querySelector('#result')||document.body).innerText.slice(0, 300)", returnByValue: true });
const shot = await send('Page.captureScreenshot', { format: 'png' });
(await import('fs')).writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
console.log('footer:', footer.result.result.value); console.log('overflow_px:', overflow.result.result.value); console.log('result:', JSON.stringify(result.result.result.value)); console.log('errors:', JSON.stringify(errors));
ws.close(); process.exit(0);
