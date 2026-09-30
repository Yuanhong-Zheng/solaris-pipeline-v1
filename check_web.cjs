// Functional checks only: no screenshots or judgments of rendered scene quality.
// NODE_PATH=<directory containing playwright> node check_web.cjs [site URL]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const url = process.argv[2] || 'http://10.80.198.139:21007/d/solaris-gpt-blender/';
(async () => {
  const browser = await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
  const page = await browser.newPage({viewport:{width:1440,height:1080}});
  const errors=[],badResponses=[],results=[];
  page.on('pageerror', error=>errors.push(error.message));
  page.on('response', response=>{if(response.status()>=400)badResponses.push([response.status(),response.url()]);});
  try {
    await page.goto(url,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('#workspace:not([hidden])');
    const names = await page.locator('[data-scene]').evaluateAll(nodes=>nodes.map(n=>n.dataset.scene));
    assert.equal(names.length,7);
    async function ready() {
      await page.waitForFunction(()=>{
        const vs=[...document.querySelectorAll('#video-grid video')];
        return vs.length===4 && vs.every(v=>v.readyState>=2&&!v.error&&!v.seeking);
      },null,{timeout:30000});
    }
    for (const name of names) {
      await page.locator('[data-scene="'+name+'"]').click();
      await ready();
      const specs=await page.locator('#video-grid video').evaluateAll(vs=>vs.map(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration})));
      assert.deepEqual(specs.map(v=>[v.width,v.height]),[[640,352],[1280,704],[640,352],[1280,704]]);
      assert(specs.every(v=>Math.abs(v.duration-12.85)<.002));
      await page.locator('#frame').fill('86');
      await page.locator('#frame').dispatchEvent('change');
      await ready();
      await page.waitForFunction(()=>[...document.querySelectorAll('#video-grid video')].every(v=>Math.abs(v.currentTime-4.2505)<.003));
      await page.locator('#next').click();
      await page.waitForFunction(()=>document.querySelector('#frame').value==='87');
      await ready();
      await page.locator('#previous').click();
      await ready();
      assert.equal(await page.locator('#frame').inputValue(),'86');
      await page.locator('#reset').click();
      await ready();
      await page.locator('#play').click();
      await page.waitForFunction(()=>[...document.querySelectorAll('#video-grid video')].every(v=>!v.paused&&v.currentTime>.6),null,{timeout:20000});
      await page.waitForFunction(()=>document.querySelector('#play').textContent.includes('暂停'));
      await page.locator('#play').click();
      await ready();
      const pauseState=await page.locator('#video-grid video').evaluateAll(vs=>vs.map(v=>({time:v.currentTime,paused:v.paused})));
      assert(pauseState.every(v=>v.paused));
      const drift=Math.max(...pauseState.map(v=>v.time))-Math.min(...pauseState.map(v=>v.time));
      assert(drift<.003,'Pause drift: '+drift);
      await page.locator('[data-view="alpha"]').click();
      assert.equal(await page.locator('.video-tile:visible').count(),2);
      await page.locator('[data-view="bravo"]').click();
      assert.equal(await page.locator('.video-tile:visible').count(),2);
      await page.locator('[data-view="both"]').click();
      assert.equal(await page.locator('.video-tile:visible').count(),4);
      const hrefs=await page.locator('#downloads a').evaluateAll(nodes=>nodes.map(n=>n.href));
      for(const href of hrefs) {
        const response=await page.request.head(href);
        assert.equal(response.status(),200,href);
        assert(Number(response.headers()['content-length'])>0,href);
      }
      results.push({scene:name,play_pause_seek_step_views_downloads:'pass',paused_time_drift:drift});
      console.log('WEB_PASS',name);
    }
    // Playback rate and replay from the final frame.
    await page.locator('#speed').selectOption('0.5');
    assert((await page.locator('#video-grid video').evaluateAll(vs=>vs.map(v=>v.playbackRate))).every(r=>r===.5));
    await page.locator('#frame').fill('257');
    await page.locator('#frame').dispatchEvent('change');
    await ready();
    await page.locator('#play').click();
    await page.waitForFunction(()=>[...document.querySelectorAll('#video-grid video')].every(v=>!v.paused&&v.currentTime<2));
    await page.locator('#play').click();
    await ready();
    // Mobile layout without opening or visually inspecting rendered frames.
    await page.setViewportSize({width:390,height:844});
    await page.waitForFunction(()=>document.documentElement.scrollWidth<=window.innerWidth+1);
    assert.equal(await page.locator('.video-tile:visible').count(),4);
    assert.deepEqual(errors,[]);
    assert.deepEqual(badResponses,[]);
    const range=await page.request.get(new URL('videos/eval_structure_blender_alpha.mp4',url).href,{headers:{Range:'bytes=0-1023'}});
    assert.equal(range.status(),206);assert.equal((await range.body()).length,1024);
    const report={url,checked_utc:new Date().toISOString(),scenes:results,mobile_390px:'pass',range_requests:'pass',playback_rate:'pass',replay_from_end:'pass',page_errors:errors,http_errors:badResponses,visual_quality_inspected:false};
    fs.writeFileSync(path.join(__dirname,'web_validation.json'),JSON.stringify(report,null,2)+'\n');
    console.log('WEB_ALL_PASS',names.length);
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
