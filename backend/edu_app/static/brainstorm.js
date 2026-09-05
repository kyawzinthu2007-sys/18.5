/* =========================================================================
   AI Brainstorm — interactive topic-first AI argument canvas.
   Self-contained module: reads the global `authToken`/`esc` helpers that
   app.js already defines, but owns all of its own state/DOM/fetches so it
   can't destabilise the existing Edu tools. Renders into #bsCanvasShell.
   ========================================================================= */
(function(){
  'use strict';

  const shell = document.getElementById('bsCanvasShell');
  if (!shell) return; // template didn't render the panel; nothing to do

  const REDUCE_MOTION = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const IS_MOBILE = () => window.innerWidth <= 760;

  function escHtml(s){
    if (typeof window.esc === 'function') return window.esc(s);
    return String(s == null ? '' : s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
  function getAuthToken(){
    return (typeof window.authToken !== 'undefined' && window.authToken) ||
           new URLSearchParams(window.location.search).get('token') || '';
  }

  const NODE_META = {
    topic:           { icon:'🎯', label:'TOPIC' },
    argument:        { icon:'💡', label:'ARGUMENT' },
    explanation:     { icon:'📖', label:'EXPLANATION' },
    example:         { icon:'🧪', label:'EXAMPLE' },
    evidence:        { icon:'📊', label:'EVIDENCE' },
    counterargument: { icon:'⚖️', label:'COUNTERARGUMENT' },
    rebuttal:        { icon:'🔥', label:'REBUTTAL' },
    conclusion:      { icon:'🏁', label:'CONCLUSION' },
  };

  const GENERATING_STAGES = [
    'Analyzing topic…',
    'Identifying arguments…',
    'Developing explanations…',
    'Generating examples…',
    'Checking logical flow…',
  ];

  // ---------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------
  const state = {
    phase: 'empty',        // empty | generating | ready | error
    topic: '',
    advanced: false,
    level: 'B2',
    errorMessage: '',
    nodesById: {},          // id -> node
    topicId: null,
    positions: {},          // id -> {x,y}
    collapsed: {},           // id -> bool (independent of node.collapsed for quick toggling)
    selectedId: null,
    zoom: 1,
    pan: { x: 0, y: 0 },
    enteringIds: new Set(), // ids currently animating in (desktop canvas)
    busyNodeIds: new Set(), // ids with an in-flight AI action
    justGenerated: false,   // show the success banner once after a fresh generation
  };

  function resetForNewMap(){
    state.nodesById = {};
    state.topicId = null;
    state.positions = {};
    state.collapsed = {};
    state.selectedId = null;
    state.enteringIds = new Set();
    state.busyNodeIds = new Set();
    state.zoom = 1;
    state.pan = { x: 0, y: 0 };
  }

  function nodeChildren(id){
    const n = state.nodesById[id];
    return (n && n.children) ? n.children.map(cid => state.nodesById[cid]).filter(Boolean) : [];
  }

  function branchTextFor(id, depth){
    depth = depth || 0;
    const n = state.nodesById[id];
    if (!n) return '';
    const meta = NODE_META[n.type] || { label: n.type };
    let out = `${'  '.repeat(depth)}${meta.label}: ${n.title}${n.content ? ' — ' + n.content : ''}\n`;
    nodeChildren(id).forEach(c => { out += branchTextFor(c.id, depth + 1); });
    return out;
  }

  // ---------------------------------------------------------------------
  // Auto layout (simple tidy tree: topic centered on top, children spread
  // horizontally beneath, grandchildren beneath those — avoids overlap by
  // giving each subtree a reserved horizontal slot).
  // ---------------------------------------------------------------------
  const LAYOUT = { nodeW: 248, nodeWTopic: 270, colGap: 34, rowGap: 220 };

  function computeSubtreeWidth(id){
    const n = state.nodesById[id];
    if (!n) return LAYOUT.nodeW;
    const visible = !state.collapsed[id];
    const kids = visible ? nodeChildren(id) : [];
    if (!kids.length) return (n.type === 'topic' ? LAYOUT.nodeWTopic : LAYOUT.nodeW);
    const total = kids.reduce((sum, k) => sum + computeSubtreeWidth(k.id), 0) + LAYOUT.colGap * (kids.length - 1);
    return Math.max(total, n.type === 'topic' ? LAYOUT.nodeWTopic : LAYOUT.nodeW);
  }

  function layoutSubtree(id, left, depth){
    const n = state.nodesById[id];
    if (!n) return;
    const w = n.type === 'topic' ? LAYOUT.nodeWTopic : LAYOUT.nodeW;
    const subtreeW = computeSubtreeWidth(id);
    const centerX = left + subtreeW / 2;
    state.positions[id] = { x: centerX - w / 2, y: depth * LAYOUT.rowGap };
    const visible = !state.collapsed[id];
    const kids = visible ? nodeChildren(id) : [];
    let cursor = left;
    kids.forEach(k => {
      const kw = computeSubtreeWidth(k.id);
      layoutSubtree(k.id, cursor, depth + 1);
      cursor += kw + LAYOUT.colGap;
    });
  }

  function runAutoLayout(){
    if (!state.topicId) return;
    layoutSubtree(state.topicId, 0, 0);
  }

  function treeBounds(){
    const layer = shell.querySelector('#bsNodesLayer');
    const xs = [], ys = [];
    Object.keys(state.positions).forEach(id => {
      if (state.collapsed[state.nodesById[id] && state.nodesById[id].parentId]) return; // hidden nodes still fine to skip visually
      const p = state.positions[id];
      const n = state.nodesById[id];
      const w = (n && n.type === 'topic') ? LAYOUT.nodeWTopic : LAYOUT.nodeW;
      // Prefer each node's real rendered height (available once it's in the
      // DOM, which it is by the time fitToScreen runs via
      // requestAnimationFrame) so "Fit" frames the actual tree instead of
      // over/under-estimating with a flat guess.
      const el = layer && layer.querySelector(`.bs-node[data-id="${cssEscape(id)}"]`);
      const h = el ? el.offsetHeight : 160;
      xs.push(p.x, p.x + w); ys.push(p.y, p.y + h);
    });
    if (!xs.length) return { minX:0, maxX:800, minY:0, maxY:500 };
    return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
  }

  // ---------------------------------------------------------------------
  // Network
  // ---------------------------------------------------------------------
  async function apiPost(path, body){
    const token = getAuthToken();
    const res = await fetch(path + (token ? ('?token=' + encodeURIComponent(token)) : ''), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json',
                 'Authorization': token ? ('Bearer ' + token) : '' },
      credentials: 'same-origin',
      body: JSON.stringify(Object.assign({ token }, body || {})),
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* fall through with null */ }
    return { ok: res.ok && data && data.ok !== false, status: res.status, data: data || {} };
  }

  function friendlyError(result, fallback){
    if (result.status === 401) return 'Please sign in to use AI Brainstorm.';
    if (result.status === 402) {
      const bal = typeof result.data.tsoCoins === 'number' ? ` Balance: ${result.data.tsoCoins} Credit.` : '';
      return (result.data.error || 'Not enough Credit for this feature.') + bal;
    }
    return result.data.error || fallback || 'Something went wrong. Please try again.';
  }

  // ---------------------------------------------------------------------
  // Actions: generate map
  // ---------------------------------------------------------------------
  async function generateMap(topic, advanced){
    state.phase = 'generating';
    state.topic = topic;
    state.advanced = advanced;
    render();
    runGeneratingAnimation();

    const result = await apiPost('/edu/api/brainstorm', { topic, advanced, level: state.level });
    if (!result.ok) {
      state.phase = 'error';
      state.errorMessage = friendlyError(result, 'Something went wrong while generating your ideas.');
      render();
      return;
    }
    resetForNewMap();
    const map = result.data.map || {};
    (map.nodes || []).forEach(n => { state.nodesById[n.id] = n; });
    state.topicId = map.topicId || (map.nodes && map.nodes[0] && map.nodes[0].id) || null;
    if (!state.topicId) {
      // The request came back ok:true but with no usable topic node — an
      // empty/malformed map. Surfacing this as an error (instead of
      // silently entering 'ready' with a look-functional-but-dead map) is
      // what stops "Build My Essay" and every other node action from
      // silently no-oping later with zero feedback to the user.
      state.phase = 'error';
      state.errorMessage = 'Your brainstorm map came back empty. Please try generating again.';
      render();
      return;
    }
    state.topic = (state.nodesById[state.topicId] || {}).title || topic;
    state.phase = 'ready';
    state.justGenerated = true;
    runAutoLayout();
    render();
    // Sequentially reveal nodes for the "cinematic build" effect on desktop,
    // or the vertical pulse -> connector-draw -> fade/scale sequence on mobile.
    if (!IS_MOBILE()) animateNodeReveal(); else animateMobileReveal();
  }

  let generatingTimer = null;
  function runGeneratingAnimation(){
    if (generatingTimer) clearInterval(generatingTimer);
    let stageIdx = 0;
    const stageEls = () => shell.querySelectorAll('.bs-stage');
    const tick = () => {
      const els = stageEls();
      els.forEach((el, i) => {
        el.classList.toggle('done', i < stageIdx);
        el.classList.toggle('active', i === stageIdx);
      });
      stageIdx++;
      if (stageIdx > GENERATING_STAGES.length) { clearInterval(generatingTimer); generatingTimer = null; }
    };
    tick();
    generatingTimer = setInterval(tick, REDUCE_MOTION ? 10 : 650);
  }

  function animateNodeReveal(){
    const order = bfsOrder();
    state.enteringIds = new Set(order);
    render();
    order.forEach((id, i) => {
      setTimeout(() => {
        state.enteringIds.delete(id);
        const el = shell.querySelector(`.bs-node[data-id="${cssEscape(id)}"]`);
        if (el) { el.classList.remove('bs-node-entering'); el.classList.add('bs-node-glow'); }
      }, REDUCE_MOTION ? 0 : 120 * (i + 1));
    });
  }

  // Mobile vertical tree reveal: for each node after the root, in BFS order —
  // (1) pulse the parent node already on screen, (2) draw the connector
  // line down from it, (3) fade/scale the new node in, (4) let its glow
  // settle. Node N+1 does not start until node N's steps have run, so
  // nodes never appear before the connector that leads to them (mandatory
  // per spec). Skips straight to the end state under reduced motion.
  function animateMobileReveal(){
    const order = bfsOrder();
    if (!order.length) return;
    state.enteringIds = new Set(order);
    render(); // renderMobile() adds bs-node-entering + connector starts undrawn
    if (REDUCE_MOTION) {
      state.enteringIds.clear();
      shell.querySelectorAll('.bs-mobile-tree .bs-node').forEach(el => el.classList.remove('bs-node-entering'));
      shell.querySelectorAll('.bs-mobile-connector').forEach(el => el.classList.add('bs-connector-drawn'));
      return;
    }
    const PULSE_MS = 160, CONNECTOR_MS = 220, SETTLE_MS = 200;
    let delay = 0;
    order.forEach((id, i) => {
      const wrap = () => shell.querySelector(`.bs-mobile-tree .bs-node[data-id="${cssEscape(id)}"]`)?.closest('.bs-mobile-node-wrap');
      if (i > 0) {
        const parentId = (state.nodesById[id] || {}).parentId;
        delay += PULSE_MS;
        setTimeout(() => {
          if (parentId) {
            const parentEl = shell.querySelector(`.bs-mobile-tree .bs-node[data-id="${cssEscape(parentId)}"]`);
            if (parentEl) { parentEl.classList.add('bs-node-parent-pulse'); setTimeout(() => parentEl.classList.remove('bs-node-parent-pulse'), 900); }
          }
          const connector = wrap()?.querySelector('.bs-mobile-connector');
          if (connector) connector.classList.add('bs-connector-drawn');
        }, delay);
        delay += CONNECTOR_MS;
      }
      const revealAt = delay;
      setTimeout(() => {
        state.enteringIds.delete(id);
        const el = shell.querySelector(`.bs-mobile-tree .bs-node[data-id="${cssEscape(id)}"]`);
        if (el) { el.classList.remove('bs-node-entering'); el.classList.add('bs-node-glow'); }
      }, revealAt);
      delay += SETTLE_MS;
    });
  }

  function bfsOrder(){
    if (!state.topicId) return [];
    const out = [];
    const queue = [state.topicId];
    while (queue.length) {
      const id = queue.shift();
      out.push(id);
      nodeChildren(id).forEach(c => queue.push(c.id));
    }
    return out;
  }

  function cssEscape(s){
    return String(s).replace(/[^a-zA-Z0-9_-]/g, m => '\\' + m);
  }

  // ---------------------------------------------------------------------
  // Actions: node-level AI operations
  // ---------------------------------------------------------------------
  async function regenerateBranch(id){
    const n = state.nodesById[id];
    if (!n || state.busyNodeIds.has(id)) return;
    state.busyNodeIds.add(id);
    render();
    const parent = n.parentId ? state.nodesById[n.parentId] : null;
    const context = parent ? branchTextFor(parent.id) : branchTextFor(id);
    const result = await apiPost('/edu/api/brainstorm/regenerate', {
      nodeType: n.type, topic: state.topic, context, level: state.level,
    });
    state.busyNodeIds.delete(id);
    if (!result.ok) {
      toast(friendlyError(result, 'Could not regenerate that branch.'), true);
      render();
      return;
    }
    const fresh = result.data.node || {};
    n.title = fresh.title || n.title;
    n.content = fresh.content || n.content;
    if (n.type === 'argument') {
      if (typeof fresh.strength === 'number') n.strength = fresh.strength;
      if (typeof fresh.relevance === 'number') n.relevance = fresh.relevance;
    }
    render();
    flashGlow(id);
  }

  async function improveNode(id){
    const n = state.nodesById[id];
    if (!n || state.busyNodeIds.has(id)) return;
    state.busyNodeIds.add(id);
    render();
    const result = await apiPost('/edu/api/brainstorm/improve', {
      nodeType: n.type, topic: state.topic, title: n.title, content: n.content, level: state.level,
    });
    state.busyNodeIds.delete(id);
    if (!result.ok) {
      toast(friendlyError(result, 'Could not improve that node.'), true);
      render();
      return;
    }
    const fresh = result.data.node || {};
    n.title = fresh.title || n.title;
    n.content = fresh.content || n.content;
    render();
    flashGlow(id);
  }

  async function convertToParagraph(id){
    const n = state.nodesById[id];
    if (!n) return;
    openParagraphModal({ status: 'loading' });
    const branchText = branchTextFor(id);
    const result = await apiPost('/edu/api/brainstorm/paragraph', { topic: state.topic, branchText });
    if (!result.ok) {
      openParagraphModal({ status: 'error', message: friendlyError(result, 'Could not build a paragraph from that branch.') });
      return;
    }
    openParagraphModal({ status: 'ready', paragraph: result.data.paragraph || '', nodeId: id });
  }

  function flashGlow(id){
    const el = shell.querySelector(`.bs-node[data-id="${cssEscape(id)}"]`);
    if (!el || REDUCE_MOTION) return;
    el.classList.remove('bs-node-glow');
    void el.offsetWidth;
    el.classList.add('bs-node-glow');
  }

  // ---------------------------------------------------------------------
  // Node CRUD (client-side; no AI call)
  // ---------------------------------------------------------------------
  function deleteNode(id){
    const n = state.nodesById[id];
    if (!n || n.type === 'topic') return;
    const toRemove = [];
    (function collect(nid){ toRemove.push(nid); nodeChildren(nid).forEach(c => collect(c.id)); })(id);
    if (n.parentId && state.nodesById[n.parentId]) {
      state.nodesById[n.parentId].children = state.nodesById[n.parentId].children.filter(c => c !== id);
    }
    toRemove.forEach(rid => { delete state.nodesById[rid]; delete state.positions[rid]; delete state.collapsed[rid]; });
    if (state.selectedId === id) state.selectedId = null;
    runAutoLayout();
    render();
  }

  function duplicateNode(id){
    const n = state.nodesById[id];
    if (!n || !n.parentId) return;
    const parent = state.nodesById[n.parentId];
    if (!parent) return;
    const copy = Object.assign({}, n, { id: 'n' + Math.random().toString(36).slice(2, 10), children: [] });
    state.nodesById[copy.id] = copy;
    const idx = parent.children.indexOf(id);
    parent.children.splice(idx + 1, 0, copy.id);
    runAutoLayout();
    render();
  }

  function editNodeContent(id, title, content){
    const n = state.nodesById[id];
    if (!n) return;
    n.title = title;
    n.content = content;
    render();
  }

  function toggleCollapse(id){
    state.collapsed[id] = !state.collapsed[id];
    runAutoLayout();
    render();
  }

  function copyNode(id){
    const n = state.nodesById[id];
    if (!n) return;
    const text = `${n.title}\n${n.content || ''}`.trim();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast('Copied to clipboard.'));
    }
  }

  // ---------------------------------------------------------------------
  // Toast (lightweight, local to this module)
  // ---------------------------------------------------------------------
  let toastTimer = null;
  function toast(msg, isError){
    let el = shell.querySelector('.bs-toast');
    if (!el) {
      el = document.createElement('div');
      el.className = 'bs-toast';
      el.style.cssText = 'position:absolute;left:50%;bottom:16px;transform:translateX(-50%);z-index:70;padding:10px 16px;border-radius:10px;font-size:12.5px;font-weight:600;max-width:88%;text-align:center;transition:opacity .2s ease;';
      shell.appendChild(el);
    }
    el.style.background = isError ? 'rgba(248,113,113,.16)' : 'rgba(52,211,153,.16)';
    el.style.border = '1px solid ' + (isError ? 'rgba(248,113,113,.4)' : 'rgba(52,211,153,.4)');
    el.style.color = isError ? '#fecaca' : '#a7f3d0';
    el.textContent = msg;
    el.style.opacity = '1';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.style.opacity = '0'; }, 3200);
  }

  // ---------------------------------------------------------------------
  // Empty state
  // ---------------------------------------------------------------------
  function renderEmpty(){
    shell.innerHTML = `
      <div class="bs-empty">
        <div class="bs-empty-icon" aria-hidden="true">🧠</div>
        <h3>Turn your essay topic into a clear argument.</h3>
        <p class="bs-empty-sub">Build arguments • Develop examples • Create stronger essays</p>
        ${state.phase === 'error' ? `
          <div class="bs-error-box">
            ${escHtml(state.errorMessage || 'Something went wrong while generating your ideas.')}
            <div class="bs-error-actions">
              <button type="button" class="bs-btn bs-btn-sm" id="bsRetryBtn">Try Again</button>
            </div>
          </div>` : ''}
        <form class="bs-topic-form" id="bsTopicForm">
          <input type="text" class="bs-topic-input" id="bsTopicInput" placeholder="Enter your IELTS topic…" maxlength="300" value="${escHtml(state.topic)}" autocomplete="off">
          <div class="bs-topic-row">
            <label class="bs-advanced-toggle"><input type="checkbox" id="bsAdvancedToggle" ${state.advanced ? 'checked' : ''}> Advanced (deeper arguments)</label>
          </div>
          <div class="bs-topic-row">
            <label class="bs-level-label" for="bsLevelSelect">CEFR level</label>
            <select class="bs-level-select" id="bsLevelSelect" aria-label="CEFR level">
              ${['A2','B1','B2','C1','C2'].map(l => `<option value="${l}" ${state.level===l?'selected':''}>${l}${l==='B2'?' (default)':''}</option>`).join('')}
            </select>
          </div>
          <div class="bs-topic-row">
            <button type="submit" class="bs-btn bs-btn-primary" id="bsGenerateBtn">✨ Generate Idea Map</button>
          </div>
        </form>
        <span class="bs-empty-footnote">Costs 5 Credit per map · Sign in required</span>
      </div>`;

    const form = shell.querySelector('#bsTopicForm');
    const input = shell.querySelector('#bsTopicInput');
    const advToggle = shell.querySelector('#bsAdvancedToggle');
    const levelSelect = shell.querySelector('#bsLevelSelect');
    form.addEventListener('submit', e => {
      e.preventDefault();
      const topic = (input.value || '').trim();
      if (!topic) { input.focus(); return; }
      if (topic.length < 8) { toast('Use a more descriptive topic.', true); return; }
      state.level = levelSelect.value;
      generateMap(topic, advToggle.checked);
    });
    const retryBtn = shell.querySelector('#bsRetryBtn');
    if (retryBtn) retryBtn.addEventListener('click', () => { state.phase = 'empty'; render(); });
  }

  // ---------------------------------------------------------------------
  // Generating state (cinematic sequence + skeleton)
  // ---------------------------------------------------------------------
  function renderGenerating(){
    shell.innerHTML = `
      <div class="bs-generating">
        <div class="bs-stage-list" role="status" aria-live="polite">
          ${GENERATING_STAGES.map(s => `
            <div class="bs-stage"><span class="bs-stage-dot" aria-hidden="true"></span><span>${escHtml(s)}</span><span class="bs-stage-check" aria-hidden="true">✓</span></div>
          `).join('')}
        </div>
        <div class="bs-skeleton-tree" aria-hidden="true">
          <div class="bs-skel-node w1"></div>
          <div class="bs-skel-node w2"></div>
          <div class="bs-skel-node w3"></div>
          <div class="bs-skel-node w2"></div>
        </div>
      </div>`;
  }

  // ---------------------------------------------------------------------
  // Toolbar (shared by desktop canvas + mobile tree header)
  // ---------------------------------------------------------------------
  function renderToolbar(){
    const zoomPct = Math.round(state.zoom * 100);
    return `
      <div class="bs-toolbar">
        <button type="button" class="bs-btn bs-btn-icon" id="bsNewMapBtn" title="Start a new map" aria-label="Start a new map">＋</button>
        <div class="bs-zoom-group" role="group" aria-label="Zoom controls">
          <button type="button" class="bs-btn" id="bsZoomOut" aria-label="Zoom out">−</button>
          <span class="bs-zoom-level" id="bsZoomLevel">${zoomPct}%</span>
          <button type="button" class="bs-btn" id="bsZoomIn" aria-label="Zoom in">+</button>
        </div>
        <button type="button" class="bs-btn" id="bsFitBtn">Fit</button>
        <button type="button" class="bs-btn" id="bsResetBtn">Reset</button>
        <div class="bs-toolbar-spacer"></div>
        <button type="button" class="bs-btn bs-btn-primary" id="bsBuildEssayBtn">✨ Build My Essay</button>
      </div>`;
  }

  function bindToolbar(){
    const q = sel => shell.querySelector(sel);
    q('#bsNewMapBtn')?.addEventListener('click', () => { state.phase = 'empty'; state.errorMessage=''; render(); });
    q('#bsZoomIn')?.addEventListener('click', () => setZoom(state.zoom + 0.1));
    q('#bsZoomOut')?.addEventListener('click', () => setZoom(state.zoom - 0.1));
    q('#bsFitBtn')?.addEventListener('click', fitToScreen);
    q('#bsResetBtn')?.addEventListener('click', () => { state.zoom = 1; state.pan = {x:0,y:0}; applyCanvasTransform(); updateZoomLabel(); });
    q('#bsBuildEssayBtn')?.addEventListener('click', buildEssayOutline);
  }

  function updateZoomLabel(){
    const el = shell.querySelector('#bsZoomLevel');
    if (el) el.textContent = Math.round(state.zoom * 100) + '%';
  }

  function setZoom(z){
    state.zoom = Math.max(0.4, Math.min(1.8, z));
    applyCanvasTransform();
    updateZoomLabel();
  }

  function applyCanvasTransform(){
    // #bsEdgesSvg is rendered *inside* .bs-canvas-inner (see renderCanvas()),
    // so it already inherits this transform from its parent in the DOM.
    // Previously this function also set the same transform directly on the
    // svg element, which meant the svg's pan/scale was applied twice
    // (once inherited, once explicit). That double-transform is exactly
    // why the connector lines drifted from their boxes: at low zoom the
    // extra scale pushed them far below the nodes, and at high zoom the
    // extra translate/scale nudged them off the node edges. The svg must
    // NOT receive its own transform — it rides along with .bs-canvas-inner.
    const inner = shell.querySelector('.bs-canvas-inner');
    if (inner) inner.style.transform = `translate(${state.pan.x}px, ${state.pan.y}px) scale(${state.zoom})`;
  }

  function fitToScreen(){
    const wrap = shell.querySelector('.bs-canvas-wrap');
    if (!wrap) return;
    const b = treeBounds();
    const treeW = (b.maxX - b.minX) || 800;
    const treeH = (b.maxY - b.minY) || 400;
    const availW = wrap.clientWidth - 60;
    const availH = wrap.clientHeight - 60;
    const z = Math.max(0.4, Math.min(1.4, Math.min(availW / treeW, availH / treeH)));
    state.zoom = z;
    state.pan = { x: (wrap.clientWidth - treeW * z) / 2 - b.minX * z, y: 40 };
    applyCanvasTransform();
    updateZoomLabel();
  }

  // ---------------------------------------------------------------------
  // Node card markup (shared between desktop absolute-positioned canvas
  // and mobile static vertical tree)
  // ---------------------------------------------------------------------
  function starString(n){
    const filled = Math.max(0, Math.min(5, n || 0));
    return '★'.repeat(filled) + '☆'.repeat(5 - filled);
  }

  function nodeCardHtml(n, opts){
    opts = opts || {};
    const meta = NODE_META[n.type] || { icon:'●', label:(n.type || '').toUpperCase() };
    const isCollapsed = !!state.collapsed[n.id];
    const isSelected = state.selectedId === n.id;
    const isBusy = state.busyNodeIds.has(n.id);
    const hasChildren = (n.children || []).length > 0;
    const scores = (n.type === 'argument' && (n.strength || n.relevance)) ? `
      <div class="bs-node-scores">
        ${n.strength ? `<span>Strength <span class="bs-node-stars">${starString(n.strength)}</span></span>` : ''}
        ${n.relevance ? `<span>IELTS <span class="bs-node-stars">${starString(n.relevance)}</span></span>` : ''}
      </div>` : '';
    const actions = isSelected ? `
      <div class="bs-node-actions">
        <button type="button" class="bs-node-action" data-act="improve" ${isBusy?'disabled':''}>✨ Improve</button>
        <button type="button" class="bs-node-action" data-act="regenerate" ${isBusy?'disabled':''}>↻ Regenerate</button>
        <button type="button" class="bs-node-action bs-node-action-primary" data-act="paragraph">→ Paragraph</button>
        ${n.type !== 'topic' ? `<button type="button" class="bs-node-action" data-act="add-supporting">+ Idea</button>` : ''}
        <button type="button" class="bs-node-action" data-act="copy">📋 Copy</button>
        <button type="button" class="bs-node-action" data-act="edit">✏️ Edit</button>
        ${n.type !== 'topic' ? `<button type="button" class="bs-node-action" data-act="duplicate">⧉ Duplicate</button>` : ''}
        ${hasChildren ? `<button type="button" class="bs-node-action" data-act="collapse">${isCollapsed?'🔽 Expand':'🔼 Collapse'}</button>` : ''}
        ${n.type !== 'topic' ? `<button type="button" class="bs-node-action" data-act="delete">🗑 Delete</button>` : ''}
      </div>` : '';
    return `
      <div class="bs-node${isSelected?' bs-node-selected':''}${isCollapsed?' bs-collapsed':''}"
           data-id="${escHtml(n.id)}" data-type="${escHtml(n.type)}" tabindex="0" role="button"
           aria-expanded="${!isCollapsed}" aria-label="${escHtml(meta.label)}: ${escHtml(n.title)}">
        <div class="bs-node-head">
          <span class="bs-node-icon" aria-hidden="true">${meta.icon}</span>
          <span class="bs-node-type-label">${escHtml(meta.label)}</span>
          <button type="button" class="bs-node-menu-btn" data-act="menu" aria-label="More actions" title="More actions">⋮</button>
        </div>
        <p class="bs-node-title">${escHtml(n.title)}</p>
        ${n.content ? `<p class="bs-node-content">${escHtml(n.content)}</p>` : ''}
        ${scores}
        ${hasChildren && !opts.mobile ? `<button type="button" class="bs-node-expand-btn" data-act="collapse">${isCollapsed ? `Expand (${(n.children||[]).length})` : 'Collapse'}</button>` : ''}
        ${actions}
        ${isBusy ? `<div class="bs-node-content" style="margin-top:8px;opacity:.7">◌ Generating…</div>` : ''}
      </div>`;
  }

  // ---------------------------------------------------------------------
  // Desktop infinite canvas
  // ---------------------------------------------------------------------
  function renderCanvas(){
    const successBanner = state.justGenerated ? `
      <div class="bs-success-banner">✓ <span><b>Idea Map Ready</b> — ${countSummary()}</span></div>` : '';
    shell.innerHTML = `
      ${successBanner}
      ${renderToolbar()}
      <div class="bs-canvas-wrap">
        <div class="bs-canvas-viewport" id="bsViewport">
          <div class="bs-canvas-inner" id="bsCanvasInner">
            <svg class="bs-edges-svg" id="bsEdgesSvg" width="4000" height="2400">
              <defs>
                <linearGradient id="bsEdgeGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stop-color="#8b5cf6"/>
                  <stop offset="1" stop-color="#60a5fa"/>
                </linearGradient>
              </defs>
              <g id="bsEdgesGroup"></g>
            </svg>
            <div id="bsNodesLayer"></div>
          </div>
        </div>
      </div>
      <div class="bs-mobile-tree" id="bsMobileTree"></div>`;

    bindToolbar();
    renderNodesAndEdges();
    bindCanvasInteractions();
    requestAnimationFrame(fitToScreen);
    state.justGenerated = false;
  }

  function countSummary(){
    const all = Object.values(state.nodesById);
    const counts = {};
    all.forEach(n => { counts[n.type] = (counts[n.type] || 0) + 1; });
    const parts = [];
    if (counts.argument) parts.push(`${counts.argument} argument${counts.argument===1?'':'s'}`);
    if (counts.example) parts.push(`${counts.example} example${counts.example===1?'':'s'}`);
    if (counts.counterargument) parts.push('1 counterargument');
    return `${all.length} idea${all.length===1?'':'s'} generated` + (parts.length ? ' · ' + parts.join(' · ') : '');
  }

  function renderNodesAndEdges(){
    const layer = shell.querySelector('#bsNodesLayer');
    const edgesGroup = shell.querySelector('#bsEdgesGroup');
    if (!layer || !edgesGroup) return;
    const ids = Object.keys(state.positions).filter(id => isVisible(id));
    layer.innerHTML = ids.map(id => nodeCardHtml(state.nodesById[id])).join('');
    ids.forEach(id => {
      const el = layer.querySelector(`.bs-node[data-id="${cssEscape(id)}"]`);
      if (!el) return;
      const pos = state.positions[id];
      el.style.left = pos.x + 'px';
      el.style.top = pos.y + 'px';
      if (state.enteringIds.has(id)) el.classList.add('bs-node-entering');
    });

    // Edges: parent -> each visible child, smooth curved path.
    let edgesHtml = '';
    ids.forEach(id => {
      const n = state.nodesById[id];
      if (!n || state.collapsed[id]) return;
      (n.children || []).forEach(cid => {
        if (!isVisible(cid) || !state.positions[cid]) return;
        edgesHtml += edgePathHtml(id, cid);
      });
    });
    edgesGroup.innerHTML = edgesHtml;
    applyCanvasTransform();
  }

  function isVisible(id){
    let n = state.nodesById[id];
    if (!n) return false;
    let guard = 0;
    while (n.parentId && guard++ < 50) {
      if (state.collapsed[n.parentId]) return false;
      n = state.nodesById[n.parentId];
      if (!n) break;
    }
    return true;
  }

  function nodeCenterBottom(id){
    const p = state.positions[id];
    const n = state.nodesById[id];
    if (!p || !n) return { x: 0, y: 0 };
    const w = n.type === 'topic' ? LAYOUT.nodeWTopic : LAYOUT.nodeW;
    return { x: p.x + w / 2, y: p.y + nodeRenderedHeight(id) };
  }
  function nodeCenterTop(id){
    const p = state.positions[id];
    const n = state.nodesById[id];
    if (!p || !n) return { x: 0, y: 0 };
    const w = n.type === 'topic' ? LAYOUT.nodeWTopic : LAYOUT.nodeW;
    return { x: p.x + w / 2, y: p.y };
  }

  // Reads the node card's true rendered height (offsetHeight) instead of
  // assuming a fixed 74px. Expanded nodes wrap to different heights
  // depending on their text length, so a fixed offset put the edge's
  // start point partway inside longer cards instead of at their real
  // bottom edge — most visible as "the connector line is in the wrong
  // place" once you zoom, since the absolute pixel error stays constant
  // while the node's on-screen size changes. Falls back to the old 74px
  // constant only if the element isn't in the DOM yet (e.g. mid-animation).
  function nodeRenderedHeight(id){
    const layer = shell.querySelector('#bsNodesLayer');
    const el = layer && layer.querySelector(`.bs-node[data-id="${cssEscape(id)}"]`);
    return el ? el.offsetHeight : 74;
  }

  function edgePathHtml(parentId, childId){
    const from = nodeCenterBottom(parentId);
    const to = nodeCenterTop(childId);
    const midY = (from.y + to.y) / 2;
    const d = `M ${from.x} ${from.y} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${to.y}`;
    const isNew = state.enteringIds.has(childId);
    return `<path class="bs-edge-path${isNew ? ' bs-edge-drawing' : ''}" d="${d}" data-from="${escHtml(parentId)}" data-to="${escHtml(childId)}"></path>`;
  }

  // ---------------------------------------------------------------------
  // Canvas interactions: pan (drag empty space), zoom (wheel), drag nodes,
  // click to select/expand, three-dot / right-click context menu.
  // ---------------------------------------------------------------------
  function bindCanvasInteractions(){
    const viewport = shell.querySelector('#bsViewport');
    const layer = shell.querySelector('#bsNodesLayer');
    if (!viewport || !layer) return;

    let panning = false, panStart = null, panOrigin = null;
    viewport.addEventListener('pointerdown', e => {
      if (e.target.closest('.bs-node')) return;
      panning = true; panStart = { x: e.clientX, y: e.clientY }; panOrigin = { ...state.pan };
      viewport.classList.add('grabbing');
      viewport.setPointerCapture(e.pointerId);
    });
    viewport.addEventListener('pointermove', e => {
      if (!panning) return;
      state.pan = { x: panOrigin.x + (e.clientX - panStart.x), y: panOrigin.y + (e.clientY - panStart.y) };
      applyCanvasTransform();
    });
    ['pointerup','pointercancel','pointerleave'].forEach(evt => viewport.addEventListener(evt, () => {
      panning = false; viewport.classList.remove('grabbing');
    }));
    viewport.addEventListener('wheel', e => {
      e.preventDefault();
      setZoom(state.zoom + (e.deltaY < 0 ? 0.08 : -0.08));
    }, { passive:false });

    // Node dragging
    let dragId = null, dragStart = null, dragOrigin = null, didDrag = false;
    layer.addEventListener('pointerdown', e => {
      const nodeEl = e.target.closest('.bs-node');
      if (!nodeEl || e.target.closest('button')) return;
      dragId = nodeEl.dataset.id;
      dragStart = { x: e.clientX, y: e.clientY };
      dragOrigin = { ...state.positions[dragId] };
      didDrag = false;
      nodeEl.setPointerCapture(e.pointerId);
      e.stopPropagation();
    });
    layer.addEventListener('pointermove', e => {
      if (!dragId) return;
      const dx = (e.clientX - dragStart.x) / state.zoom;
      const dy = (e.clientY - dragStart.y) / state.zoom;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) didDrag = true;
      if (!didDrag) return;
      state.positions[dragId] = { x: dragOrigin.x + dx, y: dragOrigin.y + dy };
      const el = layer.querySelector(`.bs-node[data-id="${cssEscape(dragId)}"]`);
      if (el) { el.style.left = state.positions[dragId].x + 'px'; el.style.top = state.positions[dragId].y + 'px'; }
      redrawEdgesOnly();
    });
    layer.addEventListener('pointerup', e => {
      if (dragId && !didDrag) selectOrExpand(dragId);
      dragId = null;
    });

    layer.addEventListener('click', e => {
      const btn = e.target.closest('[data-act]');
      if (!btn) return;
      const nodeEl = e.target.closest('.bs-node');
      const id = nodeEl && nodeEl.dataset.id;
      if (!id) return;
      const act = btn.dataset.act;
      if (act === 'menu') { openContextMenuNearElement(btn, id); return; }
      runNodeAction(act, id);
    });
    layer.addEventListener('contextmenu', e => {
      const nodeEl = e.target.closest('.bs-node');
      if (!nodeEl) return;
      e.preventDefault();
      openContextMenuAt(e.clientX, e.clientY, nodeEl.dataset.id);
    });
    layer.addEventListener('keydown', e => {
      const nodeEl = e.target.closest('.bs-node');
      if (!nodeEl) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectOrExpand(nodeEl.dataset.id); }
    });
  }

  function redrawEdgesOnly(){
    const edgesGroup = shell.querySelector('#bsEdgesGroup');
    if (!edgesGroup) return;
    let html = '';
    Object.keys(state.positions).forEach(id => {
      const n = state.nodesById[id];
      if (!n || state.collapsed[id] || !isVisible(id)) return;
      (n.children || []).forEach(cid => {
        if (!isVisible(cid) || !state.positions[cid]) return;
        html += edgePathHtml(id, cid);
      });
    });
    edgesGroup.innerHTML = html;
  }

  function selectOrExpand(id){
    state.selectedId = (state.selectedId === id) ? null : id;
    renderNodesAndEdges();
  }

  function runNodeAction(act, id){
    const n = state.nodesById[id];
    if (!n) return;
    if (act === 'regenerate') return regenerateBranch(id);
    if (act === 'improve') return improveNode(id);
    if (act === 'paragraph') return convertToParagraph(id);
    if (act === 'copy') return copyNode(id);
    if (act === 'delete') return deleteNode(id);
    if (act === 'duplicate') return duplicateNode(id);
    if (act === 'collapse') return toggleCollapse(id);
    if (act === 'edit') return openEditSheet(id);
    if (act === 'add-supporting') return addSupportingIdea(id);
  }

  function addSupportingIdea(parentId){
    const parent = state.nodesById[parentId];
    if (!parent) return;
    const id = 'n' + Math.random().toString(36).slice(2, 10);
    const type = parent.type === 'argument' ? 'explanation' : (parent.type === 'topic' ? 'argument' : 'example');
    state.nodesById[id] = { id, parentId, type, title: 'New idea', content: 'Click Edit to add your own idea here.', children: [], collapsed: false, strength: null, relevance: null };
    parent.children.push(id);
    runAutoLayout();
    render();
    setTimeout(() => flashGlow(id), 30);
  }

  // ---------------------------------------------------------------------
  // Context menu (desktop right-click OR the ⋮ button on any device)
  // ---------------------------------------------------------------------
  function closeContextMenu(){
    document.querySelectorAll('.bs-context-menu, .bs-sheet-backdrop').forEach(el => el.remove());
  }
  document.addEventListener('click', e => {
    if (!e.target.closest('.bs-context-menu')) closeContextMenu();
  });

  function contextMenuItemsHtml(n){
    const hasChildren = (n.children || []).length > 0;
    const rows = [
      ['improve', '✨ Improve'],
      ['regenerate', '↻ Regenerate'],
      n.type !== 'topic' ? ['add-supporting', '+ Add supporting idea'] : null,
      ['paragraph', '→ Convert to paragraph'],
      null, // sep
      ['copy', '📋 Copy'],
      ['edit', '✏️ Edit'],
      hasChildren ? ['collapse', state.collapsed[n.id] ? '🔽 Expand branch' : '🔼 Collapse branch'] : null,
      n.type !== 'topic' ? ['duplicate', '⧉ Duplicate'] : null,
      n.type !== 'topic' ? ['delete', '🗑 Delete'] : null,
    ];
    return rows.map(r => r === null ? '<div class="bs-context-sep"></div>' :
      `<button type="button" class="bs-context-item${r[0]==='delete'?' bs-context-danger':''}" data-act="${r[0]}">${r[1]}</button>`
    ).join('');
  }

  function openContextMenuAt(x, y, id){
    closeContextMenu();
    const n = state.nodesById[id];
    if (!n) return;
    const menu = document.createElement('div');
    menu.className = 'bs-context-menu';
    menu.innerHTML = contextMenuItemsHtml(n);
    document.body.appendChild(menu);
    const vw = window.innerWidth, vh = window.innerHeight;
    const rect = menu.getBoundingClientRect();
    menu.style.left = Math.min(x, vw - rect.width - 10) + 'px';
    menu.style.top = Math.min(y, vh - rect.height - 10) + 'px';
    menu.addEventListener('click', e => {
      const item = e.target.closest('[data-act]');
      if (!item) return;
      closeContextMenu();
      runNodeAction(item.dataset.act, id);
    });
  }

  function openContextMenuNearElement(el, id){
    const r = el.getBoundingClientRect();
    if (IS_MOBILE()) { openActionSheet(id); return; }
    openContextMenuAt(r.left, r.bottom + 4, id);
  }

  function openActionSheet(id){
    closeContextMenu();
    const n = state.nodesById[id];
    if (!n) return;
    const backdrop = document.createElement('div');
    backdrop.className = 'bs-sheet-backdrop';
    const sheet = document.createElement('div');
    sheet.className = 'bs-sheet';
    const meta = NODE_META[n.type] || { label: n.type };
    sheet.innerHTML = `<div class="bs-sheet-handle"></div><div class="bs-sheet-title">${escHtml(meta.label)} actions</div>${contextMenuItemsHtml(n)}`;
    backdrop.appendChild(sheet);
    document.body.appendChild(backdrop);
    backdrop.addEventListener('click', e => { if (e.target === backdrop) closeContextMenu(); });
    sheet.addEventListener('click', e => {
      const item = e.target.closest('[data-act]');
      if (!item) return;
      closeContextMenu();
      runNodeAction(item.dataset.act, id);
    });
  }

  // ---------------------------------------------------------------------
  // Edit sheet (inline edit for title/content — works on mobile + desktop)
  // ---------------------------------------------------------------------
  function openEditSheet(id){
    closeContextMenu();
    const n = state.nodesById[id];
    if (!n) return;
    const backdrop = document.createElement('div');
    backdrop.className = 'bs-modal-backdrop';
    backdrop.innerHTML = `
      <div class="bs-modal">
        <h3>Edit node</h3>
        <label class="bs-visually-hidden" for="bsEditTitle">Title</label>
        <input type="text" id="bsEditTitle" class="bs-topic-input" style="margin-bottom:10px" value="${escHtml(n.title)}" maxlength="80">
        <label class="bs-visually-hidden" for="bsEditContent">Content</label>
        <textarea id="bsEditContent" class="bs-topic-input" style="min-height:110px;resize:vertical" maxlength="400">${escHtml(n.content || '')}</textarea>
        <div class="bs-modal-actions" style="margin-top:12px">
          <button type="button" class="bs-btn" id="bsEditCancel">Cancel</button>
          <button type="button" class="bs-btn bs-btn-primary" id="bsEditSave">Save</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);
    backdrop.querySelector('#bsEditCancel').addEventListener('click', () => backdrop.remove());
    backdrop.addEventListener('click', e => { if (e.target === backdrop) backdrop.remove(); });
    backdrop.querySelector('#bsEditSave').addEventListener('click', () => {
      const title = backdrop.querySelector('#bsEditTitle').value.trim() || n.title;
      const content = backdrop.querySelector('#bsEditContent').value.trim();
      editNodeContent(id, title, content);
      backdrop.remove();
    });
  }

  // ---------------------------------------------------------------------
  // Paragraph conversion modal
  // ---------------------------------------------------------------------
  function openParagraphModal(opts){
    let backdrop = document.querySelector('.bs-modal-backdrop[data-bs-paragraph]');
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.className = 'bs-modal-backdrop';
      backdrop.setAttribute('data-bs-paragraph', '1');
      document.body.appendChild(backdrop);
      backdrop.addEventListener('click', e => { if (e.target === backdrop) backdrop.remove(); });
    }
    let inner = '';
    if (opts.status === 'loading') {
      inner = `<h3>Converting to paragraph…</h3><div class="bs-skeleton-tree"><div class="bs-skel-node w2"></div><div class="bs-skel-node w1"></div><div class="bs-skel-node w3"></div></div>`;
    } else if (opts.status === 'error') {
      inner = `<h3>Couldn't build a paragraph</h3><div class="bs-error-box">${escHtml(opts.message)}</div>
        <div class="bs-modal-actions" style="margin-top:14px"><button type="button" class="bs-btn" id="bsParaClose">Close</button></div>`;
    } else {
      inner = `<h3>Generated paragraph</h3>
        <div class="bs-modal-para" id="bsParaText">${escHtml(opts.paragraph)}</div>
        <div class="bs-modal-actions">
          <button type="button" class="bs-btn" id="bsParaCancel">Cancel</button>
          <button type="button" class="bs-btn" id="bsParaCopy">📋 Copy</button>
          <button type="button" class="bs-btn bs-btn-primary" id="bsParaInsert">Insert into Essay</button>
        </div>`;
    }
    backdrop.innerHTML = `<div class="bs-modal">${inner}</div>`;
    backdrop.querySelector('#bsParaClose')?.addEventListener('click', () => backdrop.remove());
    backdrop.querySelector('#bsParaCancel')?.addEventListener('click', () => backdrop.remove());
    backdrop.querySelector('#bsParaCopy')?.addEventListener('click', () => {
      const text = opts.paragraph || '';
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(() => toast('Paragraph copied.'));
    });
    backdrop.querySelector('#bsParaInsert')?.addEventListener('click', () => {
      const editor = document.getElementById('generatedEditor') || document.getElementById('editor');
      if (editor) {
        const sep = editor.value.trim() ? '\n\n' : '';
        editor.value = editor.value + sep + opts.paragraph;
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        const card = document.getElementById('generatedEditorCard');
        if (card) { card.hidden = false; card.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
        toast('Inserted into your essay editor.');
      } else {
        toast('Could not find the essay editor — paragraph copied instead.');
        if (navigator.clipboard) navigator.clipboard.writeText(opts.paragraph || '');
      }
      backdrop.remove();
    });
  }

  // ---------------------------------------------------------------------
  // Mobile: vertical interactive tree (no drag/pan/zoom required)
  // ---------------------------------------------------------------------
  function renderMobile(){
    const successBanner = state.justGenerated ? `
      <div class="bs-success-banner">✓ <span><b>Idea Map Ready</b> — ${countSummary()}</span></div>` : '';
    shell.innerHTML = `
      ${successBanner}
      <div class="bs-toolbar">
        <button type="button" class="bs-btn bs-btn-icon" id="bsNewMapBtn" aria-label="Start a new map">＋</button>
        <div class="bs-toolbar-spacer"></div>
        <button type="button" class="bs-btn bs-btn-primary" id="bsBuildEssayBtn">✨ Build My Essay</button>
      </div>
      <div class="bs-mobile-tree" id="bsMobileTree"></div>`;
    bindToolbar();
    const tree = shell.querySelector('#bsMobileTree');
    tree.innerHTML = renderMobileBranch(state.topicId);
    tree.querySelectorAll('.bs-node').forEach(el => {
      if (state.enteringIds.has(el.dataset.id)) el.classList.add('bs-node-entering');
    });
    tree.addEventListener('click', e => {
      const btn = e.target.closest('[data-act]');
      const nodeEl = e.target.closest('.bs-node');
      if (!nodeEl) return;
      const id = nodeEl.dataset.id;
      if (btn) {
        const act = btn.dataset.act;
        if (act === 'menu') { openActionSheet(id); return; }
        if (act === 'collapse') { runNodeAction('collapse', id); return; }
        runNodeAction(act, id);
        return;
      }
      // Tap card body: toggle select (expand detail / collapse again)
      selectMobile(id);
    });
    state.justGenerated = false;
  }

  function selectMobile(id){
    state.selectedId = (state.selectedId === id) ? null : id;
    const tree = shell.querySelector('#bsMobileTree');
    if (tree) tree.innerHTML = renderMobileBranch(state.topicId);
  }

  function renderMobileBranch(id, isFirst){
    const n = state.nodesById[id];
    if (!n) return '';
    // Connectors default to "drawn" (their resting state) so ordinary
    // re-renders (tapping a card, collapsing a branch) don't replay the
    // reveal animation — only nodes still pending their first reveal
    // (tracked in state.enteringIds, cleared as animateMobileReveal runs)
    // render their connector undrawn, ready for that sequence to animate.
    const stillEntering = state.enteringIds.has(id);
    const connectorClass = stillEntering ? 'bs-mobile-connector' : 'bs-mobile-connector bs-connector-drawn';
    let html = `<div class="bs-mobile-node-wrap">${isFirst === false ? `<div class="${connectorClass}" aria-hidden="true"></div>` : ''}${nodeCardHtml(n, { mobile:true })}</div>`;
    if (!state.collapsed[id]) {
      nodeChildren(id).forEach(c => { html += renderMobileBranch(c.id, false); });
    }
    return html;
  }

  // ---------------------------------------------------------------------
  // Build My Essay — converts the map structure into an outline, then
  // offers to convert each branch via the same paragraph endpoint
  // (reuses existing credit/API logic, no bypass).
  // ---------------------------------------------------------------------
  function buildEssayOutline(){
    if (!state.topicId) { toast('Generate a brainstorm map first.', true); return; }
    const args = nodeChildren(state.topicId).filter(n => n.type === 'argument');
    const counter = nodeChildren(state.topicId).find(n => n.type === 'counterargument');
    const conclusion = nodeChildren(state.topicId).find(n => n.type === 'conclusion');
    const backdrop = document.createElement('div');
    backdrop.className = 'bs-modal-backdrop';
    const rows = [
      ['Introduction', state.topic],
      ...args.map((a, i) => [`Body Paragraph ${i + 1}`, a.title]),
      counter ? ['Counterargument', counter.title] : null,
      conclusion ? ['Conclusion', conclusion.title] : null,
    ].filter(Boolean);
    backdrop.innerHTML = `
      <div class="bs-modal">
        <h3>Essay outline</h3>
        <p style="margin:0 0 4px;font-size:12.5px;color:var(--bsg-ink-dim)">Built from your idea map. Convert each section to a paragraph, then assemble them in the essay editor below.</p>
        <div class="bs-outline">
          ${rows.map(r => `<div class="bs-outline-item"><b>${escHtml(r[0])}</b><span class="bs-outline-arrow">→</span><span>${escHtml(r[1])}</span></div>`).join('')}
        </div>
        <div class="bs-modal-actions" style="margin-top:16px">
          <button type="button" class="bs-btn" id="bsOutlineClose">Close</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);
    backdrop.addEventListener('click', e => { if (e.target === backdrop) backdrop.remove(); });
    backdrop.querySelector('#bsOutlineClose').addEventListener('click', () => backdrop.remove());
  }

  // ---------------------------------------------------------------------
  // Ambient background: neural grid + floating particles (low-cost canvas
  // animation, paused off-screen and reduced on mobile / low-power).
  // ---------------------------------------------------------------------
  function initBackground(){
    if (REDUCE_MOTION) return;
    const gridCanvas = document.getElementById('bsGridCanvas');
    const particleCanvas = document.getElementById('bsParticleCanvas');
    if (!gridCanvas || !particleCanvas) return;
    const gctx = gridCanvas.getContext('2d');
    const pctx = particleCanvas.getContext('2d');
    let w = 0, h = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);
    let particles = [];
    let raf = null;
    let gridOffset = 0;
    let visible = true;

    function resize(){
      const rect = shell.closest('.brainstorm-panel').getBoundingClientRect();
      w = rect.width; h = Math.max(rect.height, 420);
      [gridCanvas, particleCanvas].forEach(c => { c.width = w * dpr; c.height = h * dpr; c.style.width = w+'px'; c.style.height = h+'px'; });
      gctx.setTransform(dpr,0,0,dpr,0,0);
      pctx.setTransform(dpr,0,0,dpr,0,0);
      const count = IS_MOBILE() ? 14 : 34;
      particles = Array.from({ length: count }, () => ({
        x: Math.random()*w, y: Math.random()*h, r: 1 + Math.random()*1.6,
        vx: (Math.random()-0.5)*0.12, vy: (Math.random()-0.5)*0.12,
        phase: Math.random()*Math.PI*2,
      }));
    }
    function drawGrid(){
      gctx.clearRect(0,0,w,h);
      gctx.strokeStyle = 'rgba(167,139,250,0.5)';
      gctx.lineWidth = 1;
      const size = 46;
      gridOffset = (gridOffset + 0.05) % size;
      for (let x = -size + gridOffset; x < w + size; x += size) { gctx.beginPath(); gctx.moveTo(x,0); gctx.lineTo(x,h); gctx.stroke(); }
      for (let y = -size + gridOffset; y < h + size; y += size) { gctx.beginPath(); gctx.moveTo(0,y); gctx.lineTo(w,y); gctx.stroke(); }
    }
    function drawParticles(t){
      pctx.clearRect(0,0,w,h);
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = w; if (p.x > w) p.x = 0;
        if (p.y < 0) p.y = h; if (p.y > h) p.y = 0;
        const alpha = 0.25 + 0.25 * Math.sin(t/1400 + p.phase);
        pctx.beginPath();
        pctx.fillStyle = `rgba(196,181,253,${Math.max(0,alpha)})`;
        pctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
        pctx.fill();
      });
      // occasional connections between nearby particles
      for (let i=0;i<particles.length;i++){
        for (let j=i+1;j<particles.length;j++){
          const dx = particles[i].x-particles[j].x, dy = particles[i].y-particles[j].y;
          const d = Math.sqrt(dx*dx+dy*dy);
          if (d < 90) {
            pctx.strokeStyle = `rgba(139,92,246,${0.12*(1-d/90)})`;
            pctx.lineWidth = 1;
            pctx.beginPath(); pctx.moveTo(particles[i].x,particles[i].y); pctx.lineTo(particles[j].x,particles[j].y); pctx.stroke();
          }
        }
      }
    }
    function loop(t){
      if (visible) { drawGrid(); drawParticles(t || 0); }
      raf = requestAnimationFrame(loop);
    }
    const io = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; }, { threshold: 0.05 });
    io.observe(shell.closest('.brainstorm-panel'));
    let resizeTimer = null;
    window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(resize, 150); });
    resize();
    raf = requestAnimationFrame(loop);
  }

  // ---------------------------------------------------------------------
  // Master render dispatcher
  // ---------------------------------------------------------------------
  function render(){
    if (state.phase === 'empty' || state.phase === 'error') { renderEmpty(); return; }
    if (state.phase === 'generating') { renderGenerating(); return; }
    if (state.phase === 'ready') {
      if (IS_MOBILE()) renderMobile(); else renderCanvas();
      return;
    }
  }

  // ---------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------
  function init(){
    initBackground();
    render();
    let resizeTimer = null;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { if (state.phase === 'ready') render(); }, 200);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
