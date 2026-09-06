const $ = s => document.querySelector(s);
const money = c => '$' + (c/100).toFixed(c%100===0?0:2);
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
let SPOTS=[], HH=false, QUERY='', MAP=null, MARKERS={};
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches || location.search.includes('still');
const shownPrice = s => (HH && s.hh_price_cents) ? s.hh_price_cents : s.price_cents;
const BOXES = {
  'Deer District':[43.0430,43.0480,-87.9190,-87.9120], 'Theater District':[43.0370,43.0430,-87.9170,-87.9085],
  'Third Ward':[43.0295,43.0370,-87.9125,-87.9000], "Walker's Point":[43.0160,43.0300,-87.9200,-87.9000],
  'Brady Street':[43.0450,43.0565,-87.9100,-87.8850], 'North Avenue':[43.0565,43.0620,-87.9160,-87.8800],
  'Downtown':[43.0350,43.0465,-87.9300,-87.8980]
};
const MATCH = ['Deer District','Theater District','Third Ward',"Walker's Point",'Brady Street','North Avenue','Downtown'];
const CORE = ['Deer District','Theater District','Downtown','Third Ward',"Walker's Point",'Brady Street','North Avenue'];
const districtOf = s => { for (const n of MATCH){const b=BOXES[n]; if(s.lat>=b[0]&&s.lat<=b[1]&&s.lng>=b[2]&&s.lng<=b[3]) return n;} return null; };
const visible = s => {
  if (HH && !s.happy_hour) return false;
  const q=QUERY.trim().toLowerCase(); if(!q) return true;
  return s.name.toLowerCase().includes(q)||(s.neighborhood||'').toLowerCase().includes(q)||(districtOf(s)||'').toLowerCase().includes(q)||s.items.some(it=>it.item.toLowerCase().includes(q));
};
let SECTN=0;
function bandHtml(name,list){
  SECTN++;
  return `<div class="sect"><span class="si">${String(SECTN).padStart(2,'0')}</span><span class="sn">${esc(name)}</span><span class="sc">${list.length} SPOT${list.length===1?'':'S'}</span></div>`;
}
function tileHtml(s){
  const p=shownPrice(s);
  return `<button class="row" data-guid="${s.guid}" type="button">
    <span class="rn">${esc(s.name)}</span>${s.happy_hour?'<span class="hh">HH</span>':''}
    <span class="rp">${money(p)}</span></button>`;
}
function renderWall(){
  SECTN=0;
  let html='';
  const used=new Set();
  CORE.forEach(n=>{
    const l=SPOTS.filter(s=>districtOf(s)===n&&visible(s)).sort((a,b)=>shownPrice(a)-shownPrice(b)||a.name.localeCompare(b.name));
    if(!l.length) return;
    l.forEach(s=>used.add(s.guid));
    html+=bandHtml(n,l)+'<div class="list">'+l.map(tileHtml).join('')+'</div>';
  });
  const rest=SPOTS.filter(s=>!used.has(s.guid)&&visible(s));
  const hoods={};
  rest.forEach(s=>{const h=s.neighborhood||'Milwaukee';(hoods[h]=hoods[h]||[]).push(s);});
  Object.keys(hoods).sort().forEach(h=>{ if(hoods[h].length>=3){
    const l=hoods[h].sort((a,b)=>shownPrice(a)-shownPrice(b)||a.name.localeCompare(b.name));
    html+=bandHtml(h,l)+'<div class="list">'+l.map(tileHtml).join('')+'</div>';
    delete hoods[h]; } });
  const tail=[].concat(...Object.values(hoods)).sort((a,b)=>shownPrice(a)-shownPrice(b)||a.name.localeCompare(b.name));
  if(tail.length) html+=bandHtml('Around the metro',tail)+'<div class="list">'+tail.map(tileHtml).join('')+'</div>';
  const wall=$('#wall');
  wall.innerHTML=html||'<div style="padding:32px 12px;text-align:center;color:var(--muted)">Nothing on the wall matches that.</div>';
  wall.querySelectorAll('.row').forEach(t=>t.addEventListener('click',()=>openSpot(t.dataset.guid)));
  staggerIn(wall);
  watchSections();
}
function staggerIn(wall){
  const els=[...wall.querySelectorAll('.sect,.row')];
  if(REDUCED){ return; }
  wall.classList.add('entering');
  els.forEach((el,i)=>{ el.style.transitionDelay=(Math.min(i,24)*14)+'ms'; });
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    els.forEach(el=>el.classList.add('in'));
    setTimeout(()=>{
      wall.classList.remove('entering');
      els.forEach(el=>{ el.classList.remove('in'); el.style.transitionDelay=''; });
    }, 24*14+280);
  }));
}
let SEC_OBS=null;
function watchSections(){
  if(SEC_OBS) SEC_OBS.disconnect();
  const barH=document.getElementById('bar').offsetHeight;
  SEC_OBS=new IntersectionObserver(es=>{
    es.forEach(e=>e.target.classList.toggle('stuck', !e.isIntersecting && e.boundingClientRect.top<=barH+1));
  },{rootMargin:`-${barH+1}px 0px 0px 0px`, threshold:0});
  document.querySelectorAll('#wall .sect').forEach(s=>SEC_OBS.observe(s));
}
function tickStat(el,to,fmt){
  if(REDUCED){ el._v=to; el.textContent=fmt(to); return; }
  const from=el._v||0, t0=performance.now(), dur=520;
  function f(t){
    const k=Math.min(1,(t-t0)/dur), e=1-Math.pow(1-k,3);
    el.textContent=fmt(Math.round(from+(to-from)*e));
    if(k<1) requestAnimationFrame(f); else el._v=to;
  }
  requestAnimationFrame(f);
}
function updateStats(animate){
  const list=SPOTS.filter(visible);
  const spots=list.length;
  const cheapest=list.length?Math.min(...list.map(shownPrice)):0;
  const hh=list.filter(s=>s.happy_hour).length;
  const set=(id,to,fmt)=>{ const el=$(id); if(animate) tickStat(el,to,fmt); else { el._v=to; el.textContent=fmt(to); } };
  set('#stat-spots',spots,v=>String(v));
  set('#stat-cheapest',cheapest,v=>money(Math.round(v/100)*100));
  set('#stat-hh',hh,v=>String(v));
}
function openSpot(guid){
  const s=SPOTS.find(x=>x.guid===guid);
  const bd=$('#backdrop'), sh=$('#sheet');
  sh.innerHTML=`<div class="sname">${esc(s.name)}</div>
    <div class="shood">${esc(districtOf(s)||s.neighborhood||'Milwaukee')}</div>
    <div class="sitems">${s.items.map(it=>{
      const reg=it.price_cents?money(it.price_cents):''; const hhp=it.hh_price_cents?money(it.hh_price_cents)+' hh':'';
      const isHH=HH&&it.hh_price_cents;
      return `<div class="sitem"><span>${esc(it.item)}</span><b class="${isHH?'hh':''}">${isHH?hhp:(reg+(hhp?' · '+hhp:''))}</b></div>`;}).join('')}</div>
    <div class="saddr">${esc(s.address||'')}</div>
    <div class="row2"><button class="pin-link" data-pin="${s.guid}" type="button">Show on map</button><button class="close2" type="button">Close</button></div>`;
  sh.querySelector('.pin-link').addEventListener('click',()=>{closeSpot();openMap(s.guid);});
  sh.querySelector('.close2').addEventListener('click',closeSpot);
  bd.classList.remove('hidden'); sh.classList.remove('hidden');
  void sh.offsetHeight;
  bd.classList.add('open'); sh.classList.add('open');
}
function closeSpot(){
  const bd=$('#backdrop'), sh=$('#sheet');
  if(sh.classList.contains('hidden')) return;
  bd.classList.remove('open'); sh.classList.remove('open');
  setTimeout(()=>{ bd.classList.add('hidden'); sh.classList.add('hidden'); }, REDUCED?0:320);
}
$('#backdrop').addEventListener('click',closeSpot);
function popupHtml(s){
  return `<div style="font-weight:600;font-size:15px">${esc(s.name)}</div>`+
    s.items.map(it=>{const reg=it.price_cents?money(it.price_cents):'';const hhp=it.hh_price_cents?money(it.hh_price_cents)+' hh':'';
      const isHH=HH&&it.hh_price_cents;
      return `<div style="margin-top:8px;font-size:12px;display:flex;justify-content:space-between;gap:12px"><span>${esc(it.item)}</span><b style="font-family:'IBM Plex Mono',monospace;font-size:14px;${isHH?'color:var(--accent)':''}">${isHH?hhp:(reg+(hhp?' · '+hhp:''))}</b></div>`;}).join('')+
    `<div style="margin-top:12px;font-family:'IBM Plex Mono',monospace;font-size:10.5px;color:#6F6A5E">${esc(s.address||'')}</div>`;
}
function openMap(guid){
  const ov=$('#map-overlay');
  ov.classList.remove('hidden'); document.body.style.overflow='hidden';
  void ov.offsetHeight; ov.classList.add('open');
  if(!MAP){ MAP=L.map('map',{scrollWheelZoom:false});
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(MAP); }
  Object.values(MARKERS).forEach(m=>m.remove()); MARKERS={};
  const list=SPOTS.filter(visible);
  const minP=Math.min(...list.map(shownPrice));
  list.forEach(s=>{ const cheap=shownPrice(s)===minP;
    const icon=L.divIcon({className:'',html:`<div class="price-pin${cheap?' cheapest':''}">${money(shownPrice(s))}</div>`,iconSize:null,iconAnchor:[20,14]});
    MARKERS[s.guid]=L.marker([s.lat,s.lng],{icon}).addTo(MAP).bindPopup(popupHtml(s)); });
  $('#map-title').textContent=`${list.length} spots, pinned`;
  setTimeout(()=>{ MAP.invalidateSize();
    if(guid&&MARKERS[guid]){ const s=list.find(x=>x.guid===guid); MAP.setView([s.lat,s.lng],15); MARKERS[s.guid].openPopup(); }
    else MAP.fitBounds(L.latLngBounds(list.map(s=>[s.lat,s.lng])).pad(0.08)); },80);
}
function closeMap(){
  const ov=$('#map-overlay');
  if(ov.classList.contains('hidden')) return;
  ov.classList.remove('open'); document.body.style.overflow='';
  setTimeout(()=>ov.classList.add('hidden'), REDUCED?0:220);
}
$('#map-btn').addEventListener('click',()=>openMap());
$('#close-map').addEventListener('click',closeMap);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMap();closeSpot();}});
$('#hh-btn').addEventListener('click',()=>{
  HH=!HH; $('#hh-btn').classList.toggle('on',HH); $('#hh-btn').setAttribute('aria-pressed',HH);
  renderWall(); updateStats(true);
});
let FIND_T=null;
$('#find').addEventListener('input',e=>{
  QUERY=e.target.value;
  clearTimeout(FIND_T);
  FIND_T=setTimeout(()=>{ renderWall(); updateStats(false); },120);
});
function watchScroll(){
  const mast=document.querySelector('.mast'), bar=document.getElementById('bar');
  let ticking=false;
  addEventListener('scroll',()=>{
    if(ticking) return; ticking=true;
    requestAnimationFrame(()=>{
      document.body.classList.toggle('scrolled', mast.getBoundingClientRect().bottom<=bar.offsetHeight+8);
      ticking=false;
    });
  },{passive:true});
}
function setBarH(){ document.documentElement.style.setProperty('--bar-h', document.getElementById('bar').offsetHeight+'px'); }
addEventListener('resize',setBarH);
setBarH();
watchScroll();
fetch('data/martinis.json?v='+Date.now()).then(r=>r.json()).then(d=>{
  SPOTS=d.martinis;
  const dt=new Date(d.generated_at);
  const dateStr=dt.toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric',year:'numeric',timeZone:'America/Chicago'});
  $('#dt-date').textContent=dateStr;
  $('#hh-btn').innerHTML=`HH <sup>${SPOTS.filter(s=>s.happy_hour).length}</sup>`;
  renderWall();
  updateStats(true);
});
