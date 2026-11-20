/* Optional browser smoke check. Uses an installed Chrome/Edge, no npm packages.
   Run: node presentation_demo/browser_check.cjs [absolute browser executable] */
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {pathToFileURL} = require('node:url');
const assert = require('node:assert/strict');

(async () => {
  const executable = process.argv[2] || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'xai-demo-browser-'));
  const output = path.join(__dirname, 'qa-output');
  fs.mkdirSync(output, {recursive:true});
  const browser = spawn(executable, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${profile}`, pathToFileURL(path.join(__dirname,'index.html')).href], {windowsHide:true, stdio:['ignore','ignore','pipe']});
  let socket;
  try {
    const devtoolsURL = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(Error('Browser startup timed out')), 20000);
      browser.once('error', e => {clearTimeout(timeout); reject(e);});
      browser.stderr.on('data', data => {const match=data.toString().match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match) {clearTimeout(timeout); resolve(match[1]);}});
    });
    const port = new URL(devtoolsURL).port;
    const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const page = pages.find(p => p.type === 'page');
    socket = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve,reject) => {socket.onopen=resolve; socket.onerror=reject;});
    let nextId=0;
    const pending = new Map(), errors=[];
    socket.onmessage = event => {
      const msg=JSON.parse(event.data);
      if(msg.id && pending.has(msg.id)){const {resolve,reject}=pending.get(msg.id);pending.delete(msg.id);msg.error?reject(Error(JSON.stringify(msg.error))):resolve(msg.result);}
      if(msg.method==='Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.text);
    };
    function call(method,params={}) {return new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});}
    async function run(expression) {const res=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(res.exceptionDetails)throw Error(JSON.stringify(res.exceptionDetails));return res.result.value;}
    await call('Runtime.enable'); await call('Page.enable');
    await call('Page.navigate', {url:pathToFileURL(path.join(__dirname,'index.html')).href});
    await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
    await run(`new Promise(resolve => { const deadline=Date.now()+10000; const timer=setInterval(()=>{if(document.querySelectorAll('.case').length===3 || Date.now()>deadline){clearInterval(timer);resolve();}},100); })`);
    console.log(await run('JSON.stringify({url:location.href,title:document.title,cases:document.querySelectorAll(".case").length})'));
    if(errors.length) console.log('Browser exceptions:',errors);
    assert.equal(await run('document.querySelectorAll(".case").length'),3);
    assert.equal(await run('document.querySelectorAll(".lens").length'),2);
    assert.match(await run('document.querySelector("#stage").textContent'),/Lean toward acceptance/);
    await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true}).then(r=>fs.writeFileSync(path.join(output,'desktop.png'),Buffer.from(r.data,'base64')));
    for (let i=0;i<3;i++) {
      await run(`document.querySelector('[data-case="${i}"]').click()`);
      for(const tab of ['evidence','summaries','recommendation','discussion']) {
        await run(`document.querySelector('[data-stage="${tab}"]').click()`);
        assert.ok((await run('document.querySelector("#stage").textContent')).length>150,`${i}: ${tab}`);
        assert.equal(await run('document.documentElement.scrollWidth > innerWidth'),false,`${tab} desktop overflow`);
      }
    }
    for(const scenario of ['operations','communication','exploration']) {
      await run(`document.querySelector('[data-scenario="${scenario}"]').click()`);
      assert.equal(await run(`document.querySelector('[data-scenario="${scenario}"]').getAttribute('aria-pressed')`),'true');
    }
    await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true}).then(r=>fs.writeFileSync(path.join(output,'discussion.png'),Buffer.from(r.data,'base64')));
    await run(`document.querySelector('[data-case="0"]').click(); document.querySelector('[data-stage="recommendation"]').click(); const slider=document.querySelector('#threshold'); slider.value=27; slider.dispatchEvent(new Event('input'));`);
    assert.equal(await run('document.querySelector("#threshold-value").textContent'),'27 min');
    assert.equal(await run('document.querySelector("#agreement").textContent'),'Same recommendation');
    await run(`document.querySelector('#reset').click(); document.querySelector('#focus').click();`);
    assert.equal(await run('document.querySelector("#threshold-value").textContent'),'50 min');
    assert.equal(await run('document.body.classList.contains("focus")'),true);
    await run(`document.querySelector('#focus').click(); document.querySelector('#method-button').click();`);
    assert.equal(await run('document.querySelector("#method").hidden'),false);
    await run(`document.querySelector('#method-button').click(); window.scrollTo(0,0);`);
    await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    for(const tab of ['recommendation','evidence','summaries','discussion']) {
      await run(`document.querySelector('[data-stage="${tab}"]').click()`);
      assert.equal(await run('document.documentElement.scrollWidth > innerWidth'),false,`${tab} mobile overflow`);
    }
    await run(`document.querySelector('[data-stage="recommendation"]').click(); window.scrollTo(0,0);`);
    await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true}).then(r=>fs.writeFileSync(path.join(output,'mobile.png'),Buffer.from(r.data,'base64')));
    await call('Page.printToPDF',{landscape:true,printBackground:true}).then(r=>fs.writeFileSync(path.join(output,'comparison.pdf'),Buffer.from(r.data,'base64')));
    assert.deepEqual(errors,[]);
    console.log('PASS: 3 cases × 4 views; 3 discussion scenarios; threshold/reset; presentation/method; desktop/mobile overflow; PDF render.');
    console.log('Screenshots and PDF: presentation_demo/qa-output/');
    await call('Browser.close');
  } finally {
    if(socket && socket.readyState===1){socket.send(JSON.stringify({id:99999,method:'Browser.close'}));await new Promise(resolve=>setTimeout(resolve,300));socket.close();}
    browser.kill();browser.stderr.destroy();browser.unref();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
