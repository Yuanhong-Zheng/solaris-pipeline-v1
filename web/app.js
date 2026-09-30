'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const FPS = 20, LAST = 256;
let data, selected, videos = [], playing = false, frame = 0, view = 'both', generation = 0;
let callbackId = null, seekVersion = 0;
const labels = {forward:'前进', back:'后退', left:'左移', right:'右移', jump:'跳跃', sprint:'疾跑', sneak:'潜行',
  attack:'攻击', use:'使用', place_block:'放置方块', place_entity:'放置实体', mine:'挖掘', mount:'上坐骑', dismount:'下坐骑'};

function actionDescription(action) {
  const keys = Object.entries(labels).filter(([key]) => action[key]).map(([,label]) => label);
  const [yaw, pitch] = action.camera || [0,0];
  if (Math.abs(yaw) > 1e-7) keys.push('转向 ' + (yaw * 180 / Math.PI).toFixed(2) + '°');
  if (Math.abs(pitch) > 1e-7) keys.push('俯仰 ' + (pitch * 180 / Math.PI).toFixed(2) + '°');
  return keys.join(' · ') || '无按键 / 保持视角';
}
function showFrame(value) {
  frame = Math.max(0, Math.min(LAST, value));
  $('#frame').value = frame + 1;
  $('#scrubber').value = frame;
  $('#time').textContent = (frame / FPS).toFixed(2) + ' s';
  for (const p of ['alpha','bravo']) $('#action-' + p).textContent = actionDescription(selected.actions[p][frame]);
  drawTimeline();
}
function drawTimeline() {
  const canvas = $('#actions-timeline'), ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height, left = 52, track = w - left - 6;
  ctx.clearRect(0,0,w,h);
  ctx.font = '10px system-ui';
  ['alpha','bravo'].forEach((player, playerIndex) => {
    ['移动','转向','放置'].forEach((label, row) => {
      const y = 4 + (playerIndex * 3 + row) * 15;
      ctx.fillStyle = '#6b756c'; ctx.fillText((playerIndex ? 'B ' : 'A ') + label, 0, y+10);
      ctx.fillStyle = '#dfe3d8'; ctx.fillRect(left,y,track,10);
      selected.actions[player].forEach((a, index) => {
        const active = row === 0 ? ['forward','back','left','right','jump'].some(k => a[k]) : row === 1 ? (a.camera || []).some(v => Math.abs(v)>1e-7) : a.place_block;
        if (active) {ctx.fillStyle = ['#458471','#c79040','#6b62a1'][row]; ctx.fillRect(left+index/257*track,y,Math.max(1,track/257),10);}
      });
    });
  });
  const x = left + (frame + 0.5) / 257 * track;
  ctx.strokeStyle = '#21372c';ctx.lineWidth = 2;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
}
function stopClock() {
  if (callbackId != null && videos[0] && videos[0].cancelVideoFrameCallback) videos[0].cancelVideoFrameCallback(callbackId);
  callbackId = null;
}
function pauseAll(align = true) {
  playing = false;
  stopClock();
  videos.forEach(v => v.pause());
  $('#play').textContent = '▶ 同步播放';
  $('#play').setAttribute('aria-label', '同步播放');
  if (align && videos[0] && videos[0].readyState >= 1) {
    const target = Math.min(LAST, Math.floor(videos[0].currentTime * FPS + .001));
    showFrame(target);
    videos.forEach(v => { if (v.readyState >= 1) v.currentTime = (target + .01) / FPS; });
  }
}
async function ready(video) {
  if (video.readyState >= 1) return;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error('视频载入超时')), 15000);
    const onReady = () => finish();
    const onError = () => finish(new Error('视频载入失败：' + video.getAttribute('src')));
    function finish(error) {clearTimeout(timer);video.removeEventListener('loadedmetadata',onReady);video.removeEventListener('error',onError);error ? reject(error) : resolve();}
    video.addEventListener('loadedmetadata',onReady,{once:true});
    video.addEventListener('error',onError,{once:true});
  });
}
async function seekTo(value) {
  const token = ++seekVersion;
  pauseAll(false);
  const target = Math.max(0,Math.min(LAST,Math.round(Number(value) || 0)));
  showFrame(target);
  try {
    await Promise.all(videos.map(ready));
    if (token !== seekVersion) return;
    videos.forEach(v => {v.currentTime = (target + .01) / FPS;});
    $('#media-status').textContent = '已同步暂停在第 ' + (target + 1) + ' 帧 · ← / → 逐帧，空格播放 / 暂停';
  } catch(error) {$('#media-status').textContent = error.message;}
}
function tick(now, metadata) {
  if (!playing || !videos[0]) return;
  const time = metadata ? metadata.mediaTime : videos[0].currentTime;
  showFrame(Math.min(LAST, Math.floor(time*FPS+.001)));
  const leaderTime = videos[0].currentTime;
  for (const v of videos.slice(1)) {
    if (!v.seeking && v.readyState >= 2 && Math.abs(v.currentTime-leaderTime)>.075) v.currentTime=leaderTime;
  }
  if (videos[0].requestVideoFrameCallback) callbackId=videos[0].requestVideoFrameCallback(tick);
}
async function startPlayback() {
  if (playing) {pauseAll();return;}
  const token = generation;
  $('#play').disabled = true;
  $('#media-status').textContent = '正在准备同步播放…';
  try {
    await Promise.all(videos.map(ready));
    if (token !== generation) return;
    if (frame >= LAST) await seekTo(0);
    playing = true;
    videos.forEach(v => {v.playbackRate=Number($('#speed').value);});
    await Promise.all(videos.map(v=>v.play()));
    if (token !== generation) {pauseAll(false);return;}
    $('#play').textContent = 'Ⅱ 同步暂停';
    $('#play').setAttribute('aria-label', '同步暂停');
    $('#media-status').textContent = '4 个视角同步播放 · 暂停后可逐帧对照';
    stopClock();
    if (videos[0].requestVideoFrameCallback) callbackId=videos[0].requestVideoFrameCallback(tick);
  } catch(error) {pauseAll(false);$('#media-status').textContent='播放未开始：'+error.message;}
  finally {$('#play').disabled=false;}
}
function setView(value) {
  view=value;
  document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));
  document.querySelectorAll('.video-tile').forEach(tile=>{tile.hidden=view!=='both'&&tile.dataset.player!==view;});
}
function disposeVideos() {
  videos.forEach(v=>{v.pause();v.removeAttribute('src');v.load();});
  videos=[];
  for (const id of ['comparison','baseline']) {const v=$('#'+id);v.pause();v.removeAttribute('src');v.load();}
}
function selectScene(name) {
  generation++; seekVersion++;
  pauseAll(false);disposeVideos();
  selected=data.datasets.find(d=>d.name===name)||data.datasets[0];
  history.replaceState(null,'','#'+selected.name);
  document.querySelectorAll('[data-scene]').forEach(button=>button.setAttribute('aria-current',String(button.dataset.scene===selected.name)));
  $('#scene-id').textContent=selected.name+' / '+selected.category;
  $('#scene-title').textContent=selected.label;
  $('#instruction').textContent=selected.instruction;
  $('#video-grid').innerHTML=['alpha','bravo'].map(p=>['gt','blender'].map(kind=>{
    const item=selected.players[p];
    return '<div class="video-tile" data-player="'+p+'"><video muted playsinline preload="auto" src="'+esc(item[kind])+'" poster="'+esc(kind==='gt'?item.input:item.poster)+'" aria-label="'+p+' '+kind+'"></video><span class="badge">'+(p==='alpha'?'Alpha':'Bravo')+'</span><button class="fullscreen" aria-label="全屏 '+p+' '+kind+'">全屏</button></div>';
  }).join('')).join('');
  videos=Array.from(document.querySelectorAll('#video-grid video'));
  videos.forEach(v=>{
    v.muted=true;
    v.addEventListener('error',()=>{$('#media-status').textContent='视频无法载入：'+v.getAttribute('src');pauseAll(false);});
  });
  videos[0].addEventListener('ended',()=>{pauseAll(false);showFrame(LAST);$('#media-status').textContent='播放完成 · 共 257 帧 / 12.85 秒';});
  videos[0].addEventListener('timeupdate',()=>{if(playing&&!videos[0].requestVideoFrameCallback)tick();});
  document.querySelectorAll('.fullscreen').forEach(button=>button.addEventListener('click',()=>{
    const v=button.parentElement.querySelector('video');
    if(v.requestFullscreen)v.requestFullscreen().catch(e=>{$('#media-status').textContent=e.message;});
  }));
  $('#inputs').innerHTML=['alpha','bravo'].map(p=>'<figure><figcaption>'+p.toUpperCase()+' · 推理输入第 1 帧</figcaption><a href="'+esc(selected.players[p].input)+'" target="_blank" rel="noopener"><img src="'+esc(selected.players[p].input)+'" alt="'+p+' 输入首帧"></a></figure>').join('');
  $('#previews').innerHTML=['alpha','bravo'].map(p=>selected.players[p].previews.map(item=>'<button data-frame="'+item.frame+'"><img loading="lazy" src="'+esc(item.path)+'" alt="'+p+' 第 '+item.frame+' 帧"><span>'+p.toUpperCase()+' · 第 '+item.frame+' 帧</span></button>').join('')).join('');
  document.querySelectorAll('[data-frame]').forEach(b=>b.addEventListener('click',()=>seekTo(Number(b.dataset.frame)-1)));
  $('#comparison').src=selected.downloads.comparison;
  $('#context-images').innerHTML=[['keyframes','原三帧 GT 参考'],['actions','原动作图']].map(([key,label])=>'<figure><figcaption>'+label+'</figcaption><a href="'+esc(selected.context[key])+'" target="_blank" rel="noopener"><img loading="lazy" src="'+esc(selected.context[key])+'" alt="'+esc(label)+'"></a></figure>').join('');
  $('#baseline').src=selected.downloads.solaris;
  const links=[['Alpha 渲染 MP4',selected.players.alpha.blender],['Bravo 渲染 MP4',selected.players.bravo.blender],['GT / Blender 四象限',selected.downloads.comparison],['Blender 工程',selected.downloads.blend],['输入动作 JSON',selected.downloads.condition],['输入来源',selected.downloads.provenance],['建模参数',selected.downloads.metadata],['视频校验记录',selected.downloads.validation]];
  $('#downloads').innerHTML=links.map(([label,path])=>'<a href="'+esc(path)+'" download>'+esc(label)+' ↓</a>').join('');
  const a=selected.windows.alpha,b=selected.windows.bravo;
  $('#technical').innerHTML='<p><b>规格：</b>两路 Blender 渲染各 1280×704；GT 单视角 640×352；四象限合成 1280×704。所有视频 20 fps、257 帧、12.85 秒；帧时间戳 0.00–12.80 秒。GT 来源是此前保存的原推理合成视频。</p>'+
    '<p><b>动作窗口（从 0 编号）：</b>Alpha '+a.start+'–'+(a.stop_exclusive-1)+'；Bravo '+b.start+'–'+(b.stop_exclusive-1)+'。第 1 帧对应首帧条件，动作 t 驱动到 t+1。</p>'+
    '<p><b>建模方法：</b>依据输入首帧估计几何、初始位置与朝向，用键鼠动作做运动积分；两台摄像机观察共享物体。中文任务说明是对动作场景的整理，不是原数据中的文本 prompt。渲染和 H.264 编码均使用 CPU。</p>'+
    '<p><b>当前近似：</b>地形、人物、材质、运动惯性和放置目标采用简化模型，未复刻 Minecraft 完整碰撞与交互逻辑；HUD 未建模。视觉一致性由你在本页比较，程序只检查规格和完整解码。</p>';
  $('#media-status').textContent='共享时间轴 · 第 1 帧为输入时刻 · ← / → 逐帧，空格播放 / 暂停';
  showFrame(0);setView(view);
}
$('#play').addEventListener('click',startPlayback);
$('#previous').addEventListener('click',()=>seekTo(frame-1));
$('#next').addEventListener('click',()=>seekTo(frame+1));
$('#reset').addEventListener('click',()=>seekTo(0));
$('#scrubber').addEventListener('input',e=>seekTo(e.target.value));
$('#frame').addEventListener('change',e=>seekTo(Number(e.target.value)-1));
$('#speed').addEventListener('change',()=>videos.forEach(v=>{v.playbackRate=Number($('#speed').value);}));
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
document.addEventListener('keydown',e=>{
  if (!selected || ['INPUT','SELECT','TEXTAREA','BUTTON','SUMMARY','A'].includes(document.activeElement.tagName))return;
  if(e.code==='Space'){e.preventDefault();startPlayback();}
  if(e.code==='ArrowRight'){e.preventDefault();seekTo(frame+1);}
  if(e.code==='ArrowLeft'){e.preventDefault();seekTo(frame-1);}
});
for (const id of ['comparison','baseline']) $('#'+id).addEventListener('play',()=>pauseAll());
$('#baseline-panel').addEventListener('toggle',e=>{if(!e.target.open){$('#comparison').pause();$('#baseline').pause();}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseAll();});
window.addEventListener('hashchange',()=>{const name=location.hash.slice(1);if(data&&selected.name!==name)selectScene(name);});
fetch('data.json').then(response=>{if(!response.ok)throw Error('数据请求失败：'+response.status);return response.json();}).then(result=>{
  data=result;
  $('#scenes').innerHTML=data.datasets.map((d,i)=>'<button data-scene="'+esc(d.name)+'" aria-current="false"><span class="number">'+String(i+1).padStart(2,'0')+'</span><span>'+esc(d.label)+'<small>'+esc(d.category)+'</small></span></button>').join('');
  document.querySelectorAll('[data-scene]').forEach(b=>b.addEventListener('click',()=>selectScene(b.dataset.scene)));
  $('#build-date').textContent='生成于 '+data.meta.generated_utc.slice(0,16).replace('T',' ')+' UTC';
  $('#loading').hidden=true;$('#workspace').hidden=false;
  selectScene(location.hash.slice(1));
}).catch(error=>{$('#loading').textContent='页面载入失败：'+error.message;});
