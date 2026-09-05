DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sentinel Shield - Live</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root{--bg:#0b0f14;--card:#121822;--line:#1f2937;--txt:#e5e7eb;
        --dim:#94a3b8;--red:#ef4444;--grn:#10b981;--org:#f59e0b;--blu:#3b82f6}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);
       font:14px/1.45 ui-monospace,Menlo,Consolas,monospace;padding:24px}
  h1{font-size:20px;margin-bottom:4px}
  .sub{color:var(--dim);margin-bottom:20px}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;
       background:var(--grn);margin-right:6px;animation:pulse 1.6s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  .cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
  .card{background:var(--card);border:1px solid var(--line);
        border-radius:10px;padding:14px 18px;min-width:150px}
  .card b{font-size:26px;display:block}
  .card span{color:var(--dim);font-size:11px;text-transform:uppercase;
             letter-spacing:.08em}
  .grid{display:grid;grid-template-columns:1fr 320px;gap:16px}
  @media(max-width:900px){.grid{grid-template-columns:1fr}}
  .panel{background:var(--card);border:1px solid var(--line);
         border-radius:10px;padding:14px;min-height:200px}
  .panel h2{font-size:13px;color:var(--dim);text-transform:uppercase;
            letter-spacing:.08em;margin-bottom:10px}
  .ev{border-bottom:1px solid var(--line);padding:8px 4px;display:flex;
      gap:10px;align-items:baseline;flex-wrap:wrap}
  .ev:last-child{border-bottom:none}
  .badge{padding:1px 8px;border-radius:99px;font-size:11px;font-weight:700;
         background:#1e3a8a;color:#bfdbfe}
  .b-XSS,.b-SQLInjection,.b-CommandInjection,.b-PathTraversal,
  .b-PromptInjection,.b-ContextOverwrite,.b-CreditTamper,.b-PlanSpoofing,
  .b-IDORAttempt,.b-PrivilegeEscalation{background:#7f1d1d;color:#fecaca}
  .b-RateFlooding,.b-KnownScanner,.b-SpamContent,.b-HiddenText{
      background:#78350f;color:#fde68a}
  .b-AutoBan,.b-AccountSuspended{background:#14532d;color:#bbf7d0}
  .ip{color:var(--blu)}
  .sample{color:var(--dim);word-break:break-all;width:100%;font-size:12px}
  .act-banned{color:var(--red);font-weight:700}
  .act-blocked{color:var(--org)}
  button{background:#1f2937;color:var(--txt);border:1px solid var(--line);
         border-radius:6px;padding:3px 10px;cursor:pointer;font-size:12px}
  button:hover{background:var(--red);border-color:var(--red)}
  li{list-style:none;display:flex;justify-content:space-between;gap:8px;
     padding:6px 2px;border-bottom:1px solid var(--line);align-items:center}
  .empty{color:var(--dim);padding:20px 0;text-align:center}
  footer{margin-top:18px;color:var(--dim);font-size:11px}
</style>
</head>
<body>
<h1><span class="dot"></span>SENTINEL SHIELD</h1>
<div class="sub" id="backend">loading...</div>
<div class="cards">
  <div class="card"><b id="s-det">0</b><span>attacks detected</span></div>
  <div class="card"><b id="s-blk">0</b><span>requests blocked</span></div>
  <div class="card"><b id="s-ban">0</b><span>bans (ip+acct)</span></div>
  <div class="card"><b id="s-rul">0</b><span>learned rules</span></div>
  <div class="card"><b id="s-pat">0</b><span>live patches</span></div>
</div>
<div class="grid">
  <div class="panel"><h2>live attack feed</h2>
    <div id="feed"><div class="empty">waiting for attacks...</div></div></div>
  <div class="panel"><h2>bans (ip / account)</h2>
    <ul id="bans"></ul><div id="nobans" class="empty">none</div></div>
</div>
<footer>X-Shield: active &middot; polls every 2s</footer>
<script>
const BOOT = __BOOTSTRAP__;
const esc = s => String(s??"").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let lastTs = 0;
function renderStats(st){
  document.getElementById("s-det").textContent = st.stats.attacks_detected;
  document.getElementById("s-blk").textContent = st.stats.requests_blocked;
  document.getElementById("s-ban").textContent = st.stats.ips_banned;
  document.getElementById("s-rul").textContent = st.learned_rules;
  document.getElementById("s-pat").textContent = st.live_patches.length;
  document.getElementById("backend").textContent =
    "backend: " + st.backend +
    " · cloudflare edge-sync: " + (st.cloudflare_sync ? "ON" : "off");
  const ul = document.getElementById("bans");
  const ips = Object.entries(st.banned_ips||{});
  document.getElementById("nobans").style.display = ips.length?"none":"block";
  ul.innerHTML = ips.map(([k,u]) =>
    `<li><span class="ip">${esc(k)}</span>`+
    `<span style="color:var(--dim)">until ${esc(u)}</span>`+
    `<button onclick="unban('${esc(k)}')">unban</button></li>`).join("");
}
async function unban(k){
  await fetch("/shield/unban/"+encodeURIComponent(k),
    {headers:{"X-Admin-Token":document.cookie.match(/shield_admin=([^;]+)/)?.[1]||""}});
  refreshStatus();
}
function addEvents(events){
  if(!events.length) return;
  const feed = document.getElementById("feed");
  if(feed.querySelector(".empty")) feed.innerHTML = "";
  for(const e of events){
    lastTs = Math.max(lastTs, e.ts||0);
    const div = document.createElement("div");
    div.className = "ev";
    div.innerHTML =
      `<span class="badge b-${esc(e.type)}">${esc(e.type)}</span>`+
      `<span class="ip">${esc(e.ip)}</span>`+
      `<span class="act-${esc(e.action)}">${esc(e.action)}</span>`+
      `<span style="color:var(--dim)">via ${esc(e.source)}</span>`+
      `<span class="sample">${esc(e.sample)}</span>`;
    feed.prepend(div);
  }
  while(feed.children.length > 100) feed.lastChild.remove();
}
async function refreshStatus(){
  try{ const r = await fetch("/shield/status");
    if(r.status===403){location.href="/shield/dashboard";return;}
    renderStats(await r.json()); }catch(_){}
}
async function pollEvents(){
  try{ const r = await fetch("/shield/events?since="+lastTs);
    if(r.ok) addEvents((await r.json()).events); }catch(_){}
}
renderStats(BOOT); refreshStatus(); pollEvents();
setInterval(refreshStatus, 5000); setInterval(pollEvents, 2000);
</script>
</body>
</html>""",
