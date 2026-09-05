
// --- Edu language ---------------------------------------------------------
const EDU_INITIAL_LANGUAGE = document.documentElement.dataset.initialLanguage === 'my' ? 'my' : 'en';
let eduLanguage = EDU_INITIAL_LANGUAGE;
let eduMode = localStorage.getItem('tsoEduMode') || 'essay';
const EDU_I18N = {
  en:{
    language:'Language', mode:'Type', essayMode:'Essay', debateMode:'Debate', generate:'✨ Generate essay (3 TSO Credits)', analyze:'Analyse writing (2 TSO Credits)', debateTitle:'Debate topic', debateType:'Debate type',
    newBtn:'＋ New', clearBtn:'Clear', topicPlaceholder:'e.g. The impact of technology on education',
    editorPlaceholder:'Paste or write your paragraph here…', titleTopic:'Essay title/topic', essayType:'Essay type',
    level:'Level', length:'Length', grading:'Grading standard', currentLevel:'Current writing level',
    nextTarget:'NEXT TARGET', stretch:'Stretch toward', audit:'Multi-step audit', underlined:'Underlined feedback',
    microEdits:'Micro-edits, not rewrites', paragraphFeedback:'Paragraph feedback', ideaMap:'Idea map',
    writingStats:'Writing statistics', eyebrow:'RULE-BASED · CEFR-CALIBRATED',
    heroTitle:'Write it.<br>Measure it. <em>Level up.</em>',
    heroDesc:'Deterministic language checking against an offline reference database — automatic essay-type detection, a CEFR-style level estimate, and click-to-fix corrections. No cloud, no model download.',
    descriptive:'Descriptive Essay', process:'Process Essay', expository:'Expository Essay', argumentative:'Argumentative Essay', debateBalancedTwo:'Two-topic balanced debate', debateBalancedProCon:'One-topic pro/con balanced debate', debateOneSided:'One-topic one-sided emphasis debate', debateComparative:'One-topic comparative multi-side debate',
    primary:'Primary', middle:'Middle School', high:'High School', essayMode:'Essay', debateMode:'Debate',
    rubricGeneral:'General CEFR band', rubricApLit:'AP Literature & Composition (1–9)', rubricIelts:'IELTS Academic Writing Task 2 (Band 0–9)', rubricCustom:'Custom syllabus rubric (A–F)',
    rubricDebateGeneral:'General debate rubric (0–10)', rubricDebateComparative:'Comparative debate rubric (multi-side)',
    essayOpinion:'Opinion essay', essayDiscussion:'Discussion (both views) essay', essayAdvDisadv:'Advantages / disadvantages essay',
    essayProblemSolution:'Problem / solution essay', essayTwoPart:'Two-part question essay', essayCauseEffect:'Cause and effect essay', essayPositiveNegative:'Positive or negative development essay',
    levelA1:'CEFR A1 (Beginner)', levelA2:'CEFR A2 (Elementary)', levelB1:'CEFR B1 (Intermediate) · IELTS Band 5', levelB2:'CEFR B2 (Upper-Intermediate) · IELTS Band 6–6.5', levelC1:'CEFR C1 (Advanced) · IELTS Band 7–7.5', levelC2:'CEFR C2 (Proficient) · IELTS Band 8–9',
    navWrite:'Write', navAnalyze:'Analyze', navCoach:'Coach', navIdeas:'Ideas', navProgress:'Progress', navBrainstorm:'Brainstorm', navJobBoard:'Job Board', navRanking:'Ranking', navGrammar:'Grammar Academy', navGrammarShort:'Grammar'
  },
  my:{
    language:'ဘာသာစကား', mode:'အမျိုးအစား', essayMode:'စာစီစာကုံး', debateMode:'အဆိုအချေ', generate:'✨ စာစီစာကုံး ဖန်တီးမည် (TSO Credit ၃)', analyze:'စာစီစာကုံး ခွဲခြမ်းမည် (TSO Credit ၂)', debateTitle:'အဆိုအချေခေါင်းစဉ်', debateType:'အဆိုအချေအမျိုးအစား',
    newBtn:'＋ အသစ်', clearBtn:'ရှင်းလင်းမည်', topicPlaceholder:'ဥပမာ - ပညာရေးတွင် နည်းပညာ၏ အကျိုးသက်ရောက်မှု',
    editorPlaceholder:'သင့်စာစီစာကုံးကို ရေးပါ သို့မဟုတ် ကူးထည့်ပါ…', titleTopic:'စာစီစာကုံး ခေါင်းစဉ် / အကြောင်းအရာ',
    essayType:'စာစီစာကုံး အမျိုးအစား', level:'အဆင့်', length:'အရှည်', grading:'အကဲဖြတ်စံနှုန်း',
    currentLevel:'လက်ရှိ စာရေးအဆင့်', nextTarget:'နောက်ထပ် ရည်မှန်းချက်', stretch:'ရည်မှန်းအဆင့်',
    audit:'အဆင့်လိုက် စစ်ဆေးမှု', underlined:'အောက်မျဉ်း feedback', microEdits:'စာကြောင်းအသေးစား ပြင်ဆင်ချက်များ',
    paragraphFeedback:'စာပိုဒ် feedback', ideaMap:'အကြောင်းအရာ မြေပုံ', writingStats:'စာရေးကိန်းဂဏန်းများ',
    eyebrow:'စည်းမျဉ်းအခြေပြု · CEFR အဆင့်သတ်မှတ်မှု',
    heroTitle:'အတွေးကောင်းမှ<br><em>အရေးအသားကောင်းသို့</em>',
    heroDesc:'အင်တာနက်မလိုဘဲ စာစီစာကုံးကို စစ်ဆေး၊ အဆင့်သတ်မှတ်ပြီး ပြင်ဆင်ရန် အကြံပြုချက်များ ပေးပါသည်။',
    descriptive:'သရုပ်ဖော်စာစီစာကုံး', process:'ဖြစ်စဉ်ပြစာစီစာကုံး', expository:'ဖွင့်ဆိုရှင်းပြစာစီစာကုံး', argumentative:'ကျိုးကြောင်းပြစာစီစာကုံး', debateBalancedTwo:'အကြောင်းအရာနှစ်ခု နှစ်ဖက်မျှအဆို', debateBalancedProCon:'အကြောင်းအရာတစ်ခု ကျိုးပြစ်မျှအဆို', debateOneSided:'အကြောင်းအရာတစ်ခု တစ်ဖက်အလေးကဲအဆို', debateComparative:'အကြောင်းအရာတစ်ခု နှိုင်းယှဉ်ဘက်အများအဆို',
    primary:'မူလတန်း', middle:'အလယ်တန်း', high:'အထက်တန်း',
    rubricGeneral:'CEFR အထွေထွေအဆင့်', rubricApLit:'AP စာပေနှင့်ရေးသားမှု (၁–၉)', rubricIelts:'IELTS Academic Writing Task 2 (Band ၀–၉)', rubricCustom:'သင်ရိုးအလိုက် စံနှုန်း (A–F)',
    rubricDebateGeneral:'အဆိုအချေ အထွေထွေစံနှုန်း (၀–၁၀)', rubricDebateComparative:'အဆိုအချေ နှိုင်းယှဉ်စံနှုန်း (ဘက်များစုံ)',
    navWrite:'ရေးရန်', navAnalyze:'စစ်ဆေးရန်', navCoach:'လမ်းညွှန်', navIdeas:'အကြောင်းအရာ', navProgress:'တိုးတက်မှု', navBrainstorm:'စိတ်ကူးထုတ်', navJobBoard:'အလုပ်ရှာဖွေရေး', navRanking:'အဆင့်သတ်မှတ်', navGrammar:'သဒ္ဒါ အကယ်ဒမီ', navGrammarShort:'သဒ္ဒါ'
  }
};
const SCORE_LABELS = {
  en:{grammar_accuracy:'Grammar accuracy',grammar_complexity:'Grammar complexity',vocabulary_range:'Vocabulary range',vocabulary_precision:'Vocabulary precision',cohesion:'Cohesion',coherence:'Coherence',task_relevance:'Task relevance',sentence_variety:'Sentence variety',development:'Idea development'},
  my:{grammar_accuracy:'သဒ္ဒါမှန်ကန်မှု',grammar_complexity:'သဒ္ဒါရှုပ်ထွေးမှု',vocabulary_range:'ဝေါဟာရအကျယ်အဝန်း',vocabulary_precision:'ဝေါဟာရတိကျမှု',cohesion:'ဆက်စပ်ညီညွတ်မှု',coherence:'အဓိပ္ပာယ်ဆက်စပ်မှု',task_relevance:'ခေါင်းစဉ်နှင့် ကိုက်ညီမှု',sentence_variety:'ဝါကျအမျိုးမျိုးသုံးနိုင်မှု',development:'အကြောင်းအရာ ဖွံ့ဖြိုးမှု'}
};
function tr(key){return EDU_I18N[eduLanguage]?.[key]||EDU_I18N.en[key]||key}
function applyEduMode(mode, save=true){
  const previousMode = eduMode;
  eduMode = mode==='debate'?'debate':'essay';
  if(save)localStorage.setItem('tsoEduMode',eduMode);
  // Switching between အဆိုအချေ and စာစီစာကုံး starts a clean workspace.
  // Do not carry text from one writing mode into the other.
  if(save && previousMode !== eduMode){
    const mainEditor=document.getElementById('editor');
    const generatedEditor=document.getElementById('generatedEditor');
    if(mainEditor) mainEditor.value='';
    if(generatedEditor) generatedEditor.value='';
    const notice=document.getElementById('originalityNotice'); if(notice) notice.hidden=true;
    if(typeof lastAnalysis !== 'undefined') lastAnalysis=null;
    const hl=document.getElementById('highlightLayer'); if(hl) hl.innerHTML='';
    if(typeof updateLive === 'function') updateLive();
    if(typeof resetUI === 'function') resetUI();
    const gh=document.getElementById('generateHint'); if(gh) gh.textContent=eduMode==='debate'?'အဆိုအချေ စာသားဖန်တီးရန် ခေါင်းစဉ်ထည့်ပါ။':(eduLanguage==='en'?'Enter a title/topic — the essay type (opinion, discussion, problem/solution, etc.) is detected automatically from it.':'Enter a title/topic to generate an essay.');
  }
  const label=document.getElementById('modeLabel'); if(label) label.textContent=tr('mode');
  const eb=document.getElementById('modeEssay'), db=document.getElementById('modeDebate');
  if(eb){eb.textContent=tr('essayMode');eb.classList.toggle('active',eduMode==='essay');eb.setAttribute('aria-pressed',String(eduMode==='essay'))}
  if(db){db.textContent=tr('debateMode');db.classList.toggle('active',eduMode==='debate');db.setAttribute('aria-pressed',String(eduMode==='debate'))}
  const modeSwitchEl=document.getElementById('eduPageModeSwitch');
  if(modeSwitchEl){modeSwitchEl.classList.toggle('mode-essay',eduMode==='essay');modeSwitchEl.classList.toggle('mode-debate',eduMode==='debate')}

  const titleLabel=document.querySelector('[data-i18n-label="titleTopic"]');
  if(titleLabel) titleLabel.firstChild.nodeValue=(eduMode==='debate' ? tr('debateTitle') : tr('titleTopic'))+'\n        ';
  const typeLabel=document.querySelector('[data-i18n-label="essayType"]');
  if(typeLabel) typeLabel.firstChild.nodeValue=(eduMode==='debate' ? tr('debateType') : tr('essayType'))+'\n        ';
  // Essay type (descriptive/process/expository/argumentative for Myanmar,
  // opinion/discussion/etc for English) is decided by the system from the
  // topic, not chosen by the user — hide the picker entirely for Essay
  // mode in both languages and let the topic field speak for itself.
  // Debate (အဆိုအချေ) still shows its own type picker, since the student
  // deliberately chooses the debate format there.
  const autoTypeEssay = eduMode==='essay';
  if(typeLabel) typeLabel.style.display = autoTypeEssay ? 'none' : '';

  const genType=document.getElementById('genEssayType');
  if(genType){
    if(eduMode==='debate'){
      genType.innerHTML=[
        ['balanced_two_sided','debateBalancedTwo'],
        ['balanced_pro_con','debateBalancedProCon'],
        ['one_sided','debateOneSided'],
        ['comparative_many','debateComparative']
      ].map(([v,k])=>`<option value="${v}">${esc(tr(k))}</option>`).join('');
    }else if(eduLanguage==='my'){
      genType.innerHTML=[
        ['descriptive','descriptive'],['process','process'],
        ['expository','expository'],['argumentative','argumentative']
      ].map(([v,k])=>`<option value="${v}" data-i18n="${k}">${esc(tr(k))}</option>`).join('');
    }else{
      // Not shown to the user in English essay mode (handled server-side via
      // topic detection), but keep an option list so any direct payload use
      // of this element still has a valid value.
      genType.innerHTML=[
        ['opinion','essayOpinion'],
        ['discussion','essayDiscussion'],
        ['advantages_disadvantages','essayAdvDisadv'],
        ['problem_solution','essayProblemSolution'],
        ['two_part','essayTwoPart'],
        ['cause_effect','essayCauseEffect'],
        ['positive_negative','essayPositiveNegative']
      ].map(([v,k])=>`<option value="${v}">${esc(tr(k))}</option>`).join('');
    }
  }

  const rubricSelect=document.getElementById('rubricSelect');
  if(rubricSelect){
    const prevRubric=rubricSelect.value;
    if(eduMode==='debate'){
      rubricSelect.innerHTML=[
        ['general','rubricDebateGeneral'],
        ['custom','rubricDebateComparative']
      ].map(([v,k])=>`<option value="${v}">${esc(tr(k))}</option>`).join('');
    }else{
      rubricSelect.innerHTML=[
        ['general','rubricGeneral'],
        ['ap_lit','rubricApLit'],
        ['ielts_academic','rubricIelts'],
        ['custom','rubricCustom']
      ].map(([v,k])=>`<option value="${v}">${esc(tr(k))}</option>`).join('');
    }
    const stillValid=Array.from(rubricSelect.options).some(o=>o.value===prevRubric);
    rubricSelect.value=stillValid?prevRubric:'general';
  }

  const level=document.getElementById('genLevel');
  if(level){
    const prevLevel=level.value;
    if(eduLanguage==='my'){
      level.innerHTML=[
        ['high','high'],['middle','middle'],['primary','primary']
      ].map(([v,k])=>`<option value="${v}" data-i18n="${k}">${esc(tr(k))}</option>`).join('');
    }else{
      level.innerHTML=[
        ['a1','levelA1'],['a2','levelA2'],['b1','levelB1'],
        ['b2','levelB2'],['c1','levelC1'],['c2','levelC2']
      ].map(([v,k])=>`<option value="${v}">${esc(tr(k))}</option>`).join('');
    }
    const stillValidLevel=Array.from(level.options).some(o=>o.value===prevLevel);
    level.value=stillValidLevel?prevLevel:(eduLanguage==='my'?'high':'b2');
  }
  const stanceWrap=document.getElementById('debateStanceWrap'); if(stanceWrap) stanceWrap.style.display='none';
  // Topic bank picker (100 curated စာစီစာကုံး titles): only meaningful for
  // Myanmar Essay mode — hidden for Debate (အဆိုအချေ) and for English,
  // since the bank is Myanmar-only content.
  const showTopicBank = eduMode==='essay' && eduLanguage==='my';
  const tbCat=document.getElementById('topicBankCategoryWrap'), tbDiff=document.getElementById('topicBankDifficultyWrap'), tbPick=document.getElementById('topicBankPick');
  if(tbCat) tbCat.style.display = showTopicBank ? '' : 'none';
  if(tbDiff) tbDiff.style.display = showTopicBank ? '' : 'none';
  if(tbPick) tbPick.style.display = showTopicBank ? '' : 'none';
  if(showTopicBank) loadTopicBankCategories();
  const genBtn=document.getElementById('generateEssayBtn');
  if(genBtn) genBtn.textContent=eduMode==='debate' && eduLanguage==='my'?'အဆိုအချေ ရေးသားဖန်တီးမည် (TSO Credit ၃)':tr('generate');
  const analyzeBtn=document.getElementById('analyzeBtn');
  if(analyzeBtn) analyzeBtn.textContent=eduMode==='debate' && eduLanguage==='my'?'အဆိုအချေစစ်ဆေးမည် (TSO Credit ၂)':tr('analyze');
  const hint=document.getElementById('detectedTypeHint');
  if(hint) hint.textContent=eduMode==='debate'
    ? (eduLanguage==='my'?'အဆိုအချေ အမျိုးအစားအလိုက် ရေးသားဖန်တီးပြီး စစ်ဆေးပါမည်။':'Generate and check according to the selected debate type.')
    : (eduLanguage==='my'?'စာစီစာကုံး မုဒ်ဖြင့် Generate နှင့် Analyse လုပ်ပါမည်။':'Generate and analyse in Essay mode.');
}
function applyEduLanguage(lang, save=true){
  eduLanguage = lang==='my'?'my':'en';
  if(save)localStorage.setItem('tsoEduLanguage',eduLanguage);
  // Debate mode is a Myanmar-only feature. English never generates a
  // debate — switching to English always resets to essay mode, even if
  // debate mode was left active (e.g. from a stale localStorage value).
  if(eduLanguage==='en' && eduMode==='debate'){
    eduMode='essay';
    if(save)localStorage.setItem('tsoEduMode',eduMode);
  }
  // Arriving in Myanmar always starts on Essay mode — the user picks
  // အဆိုအချေ explicitly via the switch, it's never pre-selected for them.
  if(eduLanguage==='my' && eduMode==='debate'){
    eduMode='essay';
    if(save)localStorage.setItem('tsoEduMode',eduMode);
  }
  document.documentElement.lang=eduLanguage==='my'?'my':'en';
  document.querySelectorAll('[data-i18n]').forEach(el=>{const key=el.dataset.i18n;if(tr(key)!=null)el.innerHTML=tr(key)});
  document.querySelectorAll('[data-i18n-label]').forEach(el=>{const key=el.dataset.i18nLabel;if(tr(key))el.childNodes[0].nodeValue=tr(key)+'\n        '});
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el=>el.placeholder=tr(el.dataset.i18nPlaceholder));
  const languageLabel=document.getElementById('languageLabel'); if(languageLabel) languageLabel.textContent=tr('language');
  const modeSwitch=document.getElementById('eduPageModeSwitch');
  if(modeSwitch) modeSwitch.hidden = eduLanguage!=='my';
  applyEduMode(eduMode,false);
  const gen=document.getElementById('generateEssayBtn'), ana=document.getElementById('analyzeBtn');
  if(gen)gen.textContent=eduMode==='debate'&&eduLanguage==='my'?'အဆိုအချေ ရေးသားဖန်တီးမည် (TSO Credit ၃)':tr('generate');
  if(ana)ana.textContent=eduMode==='debate'&&eduLanguage==='my'?'အဆိုအချေစစ်ဆေးမည် (TSO Credit ၂)':tr('analyze');
  document.querySelectorAll('.language-btn').forEach(btn=>{
    const active=btn.dataset.lang===eduLanguage; btn.classList.toggle('active',active); btn.setAttribute('aria-pressed',String(active));
  });
}
// --- စာစီစာကုံး topic bank (100 curated titles, independent from the
// generation_topic_knowledge that powers အဆိုအချေ/debate) ------------------
let topicBankCategoriesLoaded=false;
async function loadTopicBankCategories(){
  if(topicBankCategoriesLoaded) return;
  const sel=document.getElementById('topicBankCategory');
  if(!sel) return;
  try{
    const res=await fetch('/edu/api/topics?limit=1');
    const data=await res.json();
    if(data.ok && Array.isArray(data.categories)){
      sel.innerHTML='<option value="">အားလုံး</option>'+data.categories.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');
      topicBankCategoriesLoaded=true;
    }
  }catch(err){/* topic bank is a convenience feature; fail silently */}
}
document.getElementById('topicBankPick')?.addEventListener('click',async()=>{
  const btn=document.getElementById('topicBankPick');
  const category=document.getElementById('topicBankCategory')?.value||'';
  const difficulty=document.getElementById('topicBankDifficulty')?.value||'';
  const titleInput=document.getElementById('genTitle');
  if(!titleInput) return;
  const params=new URLSearchParams({random:'true'});
  if(category) params.set('category',category);
  if(difficulty) params.set('difficulty',difficulty);
  const original=btn.textContent;
  btn.disabled=true; btn.textContent='...';
  try{
    const res=await fetch(`/edu/api/topics?${params.toString()}`);
    const data=await res.json();
    if(data.ok && data.topic){
      titleInput.value=data.topic.title;
      titleInput.dispatchEvent(new Event('input'));
    }
  }catch(err){/* leave the title field untouched on failure */}
  finally{ btn.disabled=false; btn.textContent=original; }
});
// Language switching intentionally opens a separate tab/window.
// English remains at /edu; Myanmar uses the requested /edu/lang=my URL.
// The signed-in token must be carried into that new tab's URL — this page
// reads auth exclusively from ?token= in its own URL (no cookie/storage
// fallback), so without this the new tab always looks "not signed in"
// even though the user is signed in on the exact same account, since
// authToken there would just be empty.
function openEduLanguageTab(lang){
  const target = lang === 'my' ? '/edu/lang=my' : '/edu/';
  const withToken = authToken ? `${target}${target.includes('?') ? '&' : '?'}token=${encodeURIComponent(authToken)}` : target;
  window.open(withToken, '_blank', 'noopener,noreferrer');
}
document.getElementById('langEnglish')?.addEventListener('click',()=>{
  if(eduLanguage !== 'en') openEduLanguageTab('en');
  else applyEduLanguage('en');
});
document.getElementById('langMyanmar')?.addEventListener('click',()=>{
  if(eduLanguage !== 'my') openEduLanguageTab('my');
  else applyEduLanguage('my');
});
document.getElementById('modeEssay')?.addEventListener('click',()=>applyEduMode('essay'));
document.getElementById('modeDebate')?.addEventListener('click',()=>applyEduMode('debate'));
applyEduLanguage(eduLanguage,false);
// URL-selected language is authoritative for this tab.
if (EDU_INITIAL_LANGUAGE === 'my') localStorage.setItem('tsoEduLanguage','my');
else localStorage.setItem('tsoEduLanguage','en');
const e=document.getElementById('editor'),layer=document.getElementById('highlightLayer'),status=document.getElementById('status');
const authToken=new URLSearchParams(window.location.search).get('token')||'';
const coinBalanceHint=document.getElementById('coinBalanceHint');
const creditCta=document.getElementById('creditCta');
function updateCreditCta(balance, required){
  if(!creditCta) return;
  if(typeof balance==='number'){ creditCta.textContent = balance <= 5 ? `💳 Get Credit · ${balance} left` : '💳 Credit Wallet'; }
  if(typeof required==='number' && typeof balance==='number' && balance < required){ creditCta.textContent = `💳 Get ${required-balance} more Credit`; creditCta.classList.add('urgent'); }
}
if(!authToken){status.classList.add('bad');status.innerHTML='<span class="dot"></span> Not signed in — open TSO Edu from the Edu button on Talentshowoff after signing in.'}
const labels=SCORE_LABELS[eduLanguage];
let lastAnalysis=null;
function esc(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function updateLive(){let t=e.value,w=eduLanguage==='my'?(t.match(/[\u1000-\u109F]+/g)||[]):(t.match(/\b[A-Za-z]+(?:'[A-Za-z]+)?\b/g)||[]),s=t.trim()?t.trim().split(/(?<=[.!?။?])\s+/).filter(Boolean):[];document.getElementById('liveStats').textContent=`${w.length} words · ${s.length} sentences · ${t.length} characters`;syncScroll()}
function syncScroll(){layer.scrollTop=e.scrollTop;layer.scrollLeft=e.scrollLeft}
e.addEventListener('input',()=>{updateLive();if(lastAnalysis){layer.innerHTML='';lastAnalysis=null}});e.addEventListener('scroll',syncScroll);applyEduLanguage(eduLanguage,false);updateLive();
loadCoachProfile();
document.getElementById('clearBtn').onclick=()=>{e.value='';lastAnalysis=null;layer.innerHTML='';updateLive();resetUI()};
document.getElementById('newBtn').onclick=()=>{if(e.value.trim()&&!confirm('Start a new document?'))return;e.value='';lastAnalysis=null;layer.innerHTML='';updateLive();resetUI()};

function renderCoachLayers(d){
  const coach=d?.coach||{};
  const profile=d?.profile||{};
  const comparison=d?.comparison||{};
  const score=Number(profile.tsoScore ?? d?.scores?.overall ?? 0);
  const scoreEl=document.getElementById('coachScore'); if(scoreEl) scoreEl.textContent=String(Math.round(score));
  const headline=document.getElementById('coachHeadline'); if(headline) headline.textContent=coach.headline||'Your personal writing coach is ready.';
  const action=document.getElementById('coachAction'); if(action) action.textContent=coach.action||coach.tip||'Focus on your priority skills.';
  const tags=document.getElementById('coachPriorities');
  if(tags){
    const pri=Array.isArray(coach.priority)?coach.priority:[];
    const strengths=Array.isArray(coach.strengths)?coach.strengths:[];
    tags.innerHTML=[...pri.map(x=>`<span class="coach-tag low">${esc(x.skill)} · ${esc(x.score)}</span>`),...strengths.map(x=>`<span class="coach-tag good">✓ ${esc(x.skill)} · ${esc(x.score)}</span>`)].join('')||'<span class="coach-tag">Analyze again to identify priorities.</span>';
  }
  const ps=document.getElementById('profileSummary');
  if(ps){
    const dims=Array.isArray(profile.dimensions)?profile.dimensions:[];
    const weakest=Array.isArray(profile.prioritySkills)?profile.prioritySkills[0]:null;
    ps.innerHTML=`<div class="profile-stat"><b>${esc(profile.level||d?.level||'A1')}</b><small>Current level</small></div><div class="profile-stat"><b>${esc(profile.targetLevel||d?.target_level||'B2')}</b><small>Next target</small></div><div class="profile-stat"><b>${esc(profile.essayCount||0)}</b><small>Saved analyses</small></div><div class="profile-stat"><b>${esc(weakest?.skill||'—')}</b><small>Priority skill</small></div>`;
  }
  const plan=document.getElementById('improvementPlan');
  if(plan){
    const rows=Array.isArray(profile.improvementPlan)?profile.improvementPlan:[];
    const key='tsoEdu30DayPlan';
    let completed={}; try{completed=JSON.parse(localStorage.getItem(key)||'{}')||{}}catch(_){}
    const doneCount=rows.filter(x=>completed[String(x.day)]).length;
    const pct=rows.length?Math.round(doneCount/rows.length*100):0;
    const dayEl=document.getElementById('coachDayCount'); if(dayEl) dayEl.textContent=String(doneCount);
    const pctEl=document.getElementById('coachPlanProgress'); if(pctEl) pctEl.textContent=pct+'%';
    const bar=document.getElementById('planProgressBar'); if(bar) bar.style.width=pct+'%';
    plan.innerHTML=rows.length?rows.map(x=>{
      const done=!!completed[String(x.day)];
      return `<button type="button" class="plan-item ${done?'done':''}" data-plan-day="${esc(x.day)}"><span class="day-badge">${esc(x.day)}</span><span class="plan-copy"><b>Day ${esc(x.day)} · ${esc(x.phase||'Growth')}</b><strong>${esc(x.skill)}</strong><small>${esc(x.focus)} · ${esc(x.task)}</small></span><span class="day-check">${done?'✓':'○'}</span></button>`;
    }).join(''):'Analyze an essay to generate your 30-day journey.';
    plan.querySelectorAll('[data-plan-day]').forEach(btn=>btn.addEventListener('click',()=>{
      const d=btn.dataset.planDay; completed[d]=!completed[d]; try{localStorage.setItem(key,JSON.stringify(completed))}catch(_){} renderCoachLayers({profile,coach,comparison});
    }));
  }
  const ba=document.getElementById('beforeAfter');
  if(ba){
    if(comparison.available){ const delta=Number(comparison.delta||0); ba.innerHTML=`<div class="delta">${delta>0?'+':''}${esc(delta)} points</div><small>${esc(comparison.previousLevel||'A1')} → <b>${esc(comparison.currentLevel||profile.level||'A1')}</b><br>${esc(comparison.message||'Compared with your previous saved analysis.')}</small>`; }
    else ba.innerHTML='<small>Your next saved analysis will create a before/after comparison automatically.</small>';
  }
  const mm=document.getElementById('mistakeMemory');
  if(mm){
    const ms=Array.isArray(profile.mistakes)?profile.mistakes:[];
    mm.innerHTML=ms.length?ms.slice(0,5).map(x=>`<div class="mistake-item"><b>${esc(x.category||'writing')} · ${esc(x.count||1)}×</b><span>${esc(x.text||'')}</span>${x.replacement?`<br><span>Try: ${esc(x.replacement)}</span>`:''}</div>`).join(''):'No recurring mistakes saved yet.';
  }
  const hist=document.getElementById('coachHistory');
  if(hist){
    const hs=Array.isArray(profile.history)?profile.history.slice().reverse().slice(0,6):[];
    hist.innerHTML=hs.length?hs.map(x=>`<div class="history-item"><b>${esc(x.tsoScore)}/100 · ${esc(x.level||'A1')}</b><span>${esc(x.title||'Untitled essay')} · ${new Date(x.at).toLocaleDateString()}</span></div>`).join(''):'Your saved essay scores will appear here.';
  }
}
async function loadCoachProfile(){
  if(!authToken) return;
  try{
    const r=await fetch('/edu/api/coach-profile?token='+encodeURIComponent(authToken),{headers:{'Authorization':'Bearer '+authToken},credentials:'same-origin'});
    const d=await r.json();
    if(r.ok&&d.ok) renderCoachLayers(d);
  }catch(_){/* Coach UI is optional and must never block writing analysis. */}
}

document.getElementById('analyzeBtn').onclick=async()=>{
  const text=(e.value||'').trim();
  if(!text){status.classList.add('bad');status.innerHTML='<span class="dot"></span> Write some text before analyzing.';return}
  if(!authToken){status.classList.add('bad');status.innerHTML='<span class="dot"></span> Please open TSO Edu from the Edu button after signing in.';return}
  const btn=document.getElementById('analyzeBtn');
  const oldText=btn.textContent;
  btn.disabled=true;
  status.classList.remove('bad');
  status.innerHTML='<span class="dot"></span> Analyzing…';
  // The idea map is optional. It must NEVER be allowed to interrupt the main analysis.
  try { Promise.resolve(generateIdeaMap({silent:true,autoScroll:true})).catch(()=>{}); } catch (_) {}
  try{
    const payload={text,essay_title:document.getElementById('essayTitle')?.value||'',rubric:document.getElementById('rubricSelect')?.value||'general',language:eduLanguage,mode:eduMode,token:authToken};
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),45000);
    let r;
    try{
      r=await fetch('/edu/api/analyze?token='+encodeURIComponent(authToken),{
        method:'POST',
        headers:{'Content-Type':'application/json','Accept':'application/json','Authorization':'Bearer '+authToken},
        body:JSON.stringify(payload),signal:controller.signal,credentials:'same-origin'
      });
    }finally{clearTimeout(timeout)}
    const raw=await r.text();
    let d={};
    try{d=raw?JSON.parse(raw):{}}catch(_){d={error:raw?raw.slice(0,300):'The server returned an invalid response.'}}
    if(!r.ok||d.ok===false){
      status.classList.add('bad');
      if(r.status===401){status.innerHTML='<span class="dot"></span> Session expired. Sign in again and reopen TSO Edu.'}
      else if(r.status===402){status.innerHTML='<span class="dot"></span> '+esc(d.error||'Not enough TSO Credits.');coinBalanceHint.textContent=typeof d.tsoCoins==='number'?`Balance: ${d.tsoCoins} TSO Credit`:'';updateCreditCta(d.tsoCoins,d.requiredCoins||2)}
      else if(r.status===413){status.innerHTML='<span class="dot"></span> '+esc(d.error||'Text is too large.')}
      else{status.innerHTML='<span class="dot"></span> '+esc(d.error||`Analysis failed (HTTP ${r.status}).`)}
      return;
    }
    // Debate analysis intentionally does not return a CEFR/level field.
    // Validate it with its own 10-mark payload instead of the essay payload.
    if(eduMode==='debate') {
      if(typeof d.marks!=='number' || typeof d.max_marks!=='number' || !d.rubric_marks || !Array.isArray(d.issues) || !Array.isArray(d.recommended_structure)){
        status.classList.add('bad');
        status.innerHTML='<span class="dot"></span> The server completed the request but returned incomplete အဆိုအချေ analysis data.';
        return;
      }
    } else if(!d.scores||typeof d.scores.overall!=='number'||!d.level){
      status.classList.add('bad');
      status.innerHTML='<span class="dot"></span> The server completed the request but returned incomplete analysis data.';
      return;
    }
    lastAnalysis=d;
    render(d);
    renderHighlights(d.highlights||[]);
    renderCoachLayers(d);
    status.classList.remove('bad');
    status.innerHTML='<span class="dot"></span> Analysis complete';
    if(typeof d.tsoCoins==='number'){coinBalanceHint.textContent=`Balance: ${d.tsoCoins} TSO`;updateCreditCta(d.tsoCoins,3)}
  }catch(err){
    status.classList.add('bad');
    const reason = err?.name==='AbortError' ? 'Analysis timed out.' : (err?.message ? esc(err.message) : 'Analysis request failed.');
    status.innerHTML='<span class="dot"></span> '+reason+' Please try again.';
    console.error('TSO Edu analyze error:',err);
  }finally{btn.disabled=false;btn.textContent=oldText}
};

// --- Generate Essay -----------------------------------------------------
function renderOriginalityNotice(p){
  const notice=document.getElementById('originalityNotice');
  if(!notice) return;
  if(!p || !p.checked){ notice.hidden=true; return; }
  const status=p.status==='high'?'high':p.status==='review'?'review':'clear';
  notice.hidden=false;
  notice.className='originality-notice status-'+status;
  const badge=document.getElementById('originalityBadge');
  if(badge) badge.textContent = status==='high' ? '⚠️ High similarity' : status==='review' ? '⚠️ Review similarity' : '✓ Clear';
  const scoreEl=document.getElementById('originalityScore');
  const pct=Number(p.score||0);
  if(scoreEl) scoreEl.textContent = `${pct.toFixed(1)}% phrase overlap`;
  const msgEl=document.getElementById('originalityMessage');
  if(msgEl) msgEl.textContent = p.message || '';
  const matchesEl=document.getElementById('originalityMatches');
  if(matchesEl){
    const matches=Array.isArray(p.matches)?p.matches:[];
    matchesEl.innerHTML = matches.length
      ? matches.map(m=>`<li><b>${esc(m.source||'TSO Edu reference')} — ${Number(m.similarity||0).toFixed(1)}% match</b>${esc(m.matchedPhrase||'')}</li>`).join('')
      : '';
  }
}

const generateHint=document.getElementById('generateHint');
document.getElementById('generateEssayBtn').onclick=async()=>{
  const title=(document.getElementById('genTitle')?.value||'').trim();
  if(!title){generateHint.classList.add('bad');generateHint.textContent='Enter an essay title/topic first.';return}
  if(!authToken){generateHint.classList.add('bad');generateHint.textContent='Please open TSO Edu from the Edu button after signing in.';return}
  const btn=document.getElementById('generateEssayBtn');
  const oldText=btn.textContent;
  btn.disabled=true;btn.textContent='Generating…';
  generateHint.classList.remove('bad');
  generateHint.textContent='Writing your essay…';
  try{
    const payload={
      title,
      mode:eduMode,
      level:document.getElementById('genLevel')?.value||'high',
      target_words:Number(document.getElementById('genWords')?.value||250),
      stance:document.getElementById('debateStance')?.value||'support',
      language:eduLanguage,
      token:authToken
    };
    // Essay type is auto-detected server-side from the title for both
    // languages in Essay mode (the picker is hidden — see applyEduMode).
    // Only send an explicit essay_type for Debate mode, where the student
    // deliberately picks the အဆိုအချေ format themselves.
    if(eduMode==='debate'){
      payload.essay_type=document.getElementById('genEssayType')?.value||'balanced_two_sided';
    }
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),60000);
    let r;
    try{
      r=await fetch('/edu/api/generate-essay?token='+encodeURIComponent(authToken),{
        method:'POST',
        headers:{'Content-Type':'application/json','Accept':'application/json','Authorization':'Bearer '+authToken},
        body:JSON.stringify(payload),signal:controller.signal,credentials:'same-origin'
      });
    }finally{clearTimeout(timeout)}
    const raw=await r.text();
    let d={};
    try{d=raw?JSON.parse(raw):{}}catch(_){d={error:raw?raw.slice(0,300):'The server returned an invalid response.'}}
    if(!r.ok||d.ok===false){
      generateHint.classList.add('bad');
      if(r.status===401){generateHint.textContent='Session expired. Sign in again and reopen TSO Edu.'}
      else if(r.status===402){generateHint.textContent=esc(d.error||'Not enough TSO Credits.');if(typeof d.tsoCoins==='number')coinBalanceHint.textContent=`Balance: ${d.tsoCoins} TSO Credit`;updateCreditCta(d.tsoCoins,d.requiredCoins||3)}
      else if(r.status===503){generateHint.textContent=esc(d.error||'Essay generation is not available right now.')}
      else{generateHint.textContent=esc(d.error||`Essay generation failed (HTTP ${r.status}).`)}
      return;
    }
    if(!d.essay){generateHint.classList.add('bad');generateHint.textContent='The server did not return an essay.';return}
    // Keep generated text in its own workspace. It must not overwrite the
    // analysis editor until the student explicitly chooses "Use in writing editor".
    const generatedEditor=document.getElementById('generatedEditor');
    if(generatedEditor) generatedEditor.value=d.essay;
    const generatedCard=document.getElementById('generatedEditorCard');
    if(generatedCard) generatedCard.scrollIntoView({behavior:'smooth',block:'center'});
    const essayTitleField=document.getElementById('essayTitle');
    if(essayTitleField)essayTitleField.value=d.title||title;
    generateHint.classList.remove('bad');
    renderOriginalityNotice(d.plagiarism);
    if(!(d.plagiarism && d.plagiarism.checked)){
      generateHint.textContent='Essay generated and loaded into the editor below — click Analyze to get feedback on it.';
    }else{
      generateHint.textContent='Essay generated and loaded into the editor below — see the originality check above it.';
    }
    if(typeof d.tsoCoins==='number')coinBalanceHint.textContent=`Balance: ${d.tsoCoins} TSO`;
    // Auto-build the idea map from the freshly generated essay too, same as Analyze does.
    // It scrolls itself into view once rendered, so no need to scroll to the editor first.
    try{ await Promise.resolve(generateIdeaMap({silent:true,autoScroll:true})); }catch(_){}
  }catch(err){
    generateHint.classList.add('bad');
    const reason = err?.name==='AbortError' ? 'Essay generation timed out.' : (err?.message ? esc(err.message) : 'Essay generation request failed.');
    generateHint.textContent=reason+' Please try again.';
    console.error('TSO Edu generate-essay error:',err);
  }finally{btn.disabled=false;btn.textContent=oldText}
};

// Dedicated generated-text workspace controls.
document.getElementById('loadGeneratedBtn')?.addEventListener('click',()=>{
  const generated=document.getElementById('generatedEditor')?.value||'';
  if(!generated.trim()) return;
  e.value=generated;
  lastAnalysis=null; layer.innerHTML=''; updateLive();
  document.getElementById('editor')?.scrollIntoView({behavior:'smooth',block:'center'});
});
document.getElementById('clearGeneratedBtn')?.addEventListener('click',()=>{
  const generated=document.getElementById('generatedEditor'); if(generated) generated.value='';
  const notice=document.getElementById('originalityNotice'); if(notice) notice.hidden=true;
});
document.getElementById('copyGeneratedBtn')?.addEventListener('click',async()=>{
  const generated=document.getElementById('generatedEditor')?.value||'';
  if(!generated.trim()) return;
  try{
    await navigator.clipboard.writeText(generated);
    const b=document.getElementById('copyGeneratedBtn'); if(b){const old=b.textContent;b.textContent='Copied';setTimeout(()=>b.textContent=old,1200)}
  }catch(_){}
});

const CEFR_ORDER=['A1','A2','B1','B2','C1','C2'];
function updateRuler(level){
  const idx=CEFR_ORDER.indexOf(level);
  const pct=idx<0?0:(idx/(CEFR_ORDER.length-1))*100;
  const marker=document.getElementById('heroMarker'),label=document.getElementById('heroMarkerLabel');
  if(marker){marker.style.left=pct+'%'}
  if(label){label.textContent=level||'—'}
}
function render(d){
const setText=(id,val)=>{const el=document.getElementById(id); if(el) el.textContent=val; else console.warn('TSO Edu: missing element #'+id);};
const criteriaStyleId='tsoDebateCriteriaStyle';
if(!document.getElementById(criteriaStyleId)){
 const st=document.createElement('style');st.id=criteriaStyleId;st.textContent=`.debate-criteria-list{display:grid;gap:10px;margin-top:8px}.debate-criteria-list>div{padding:10px 12px;border:1px solid rgba(127,127,127,.2);border-radius:10px;background:rgba(127,127,127,.05)}.debate-criteria-list b{display:block;margin-bottom:4px}.debate-criteria-list span{font-size:.93em;line-height:1.55}.debate-marking-note{font-size:.88em;line-height:1.55;color:#64748b}`;document.head.appendChild(st)
}
const debateOld=document.getElementById('debateAnalysisPanel'); if(debateOld) debateOld.remove();
if(d.mode==='debate' && d.strengths){
  ['levelChip','levelText','targetLevel','targetText','heroMarker','heroMarkerLabel','scores','rubricScore'].forEach(id=>{const el=document.getElementById(id); if(el) el.closest('.editor-card,.score-panel,.level-panel')?.classList.add('hidden')});
  const panel=document.createElement('section'); panel.id='debateAnalysisPanel'; panel.className='editor-card';
  const rm=d.rubric_marks||{};
  const mark2=rm.position||0;
  const mark3a=rm.opposing_weakness ?? rm.body_one ?? 0;
  const mark3b=rm.own_strength ?? rm.body_two ?? 0;
  const mark2c=rm.conclusion||0;
  const total=Number(d.marks||0);
  const issues=Array.isArray(d.issues)?d.issues:[];
  const proofIssues=issues.filter(x=>x && (x.type==='grammar'||x.type==='spelling'||x.category==='grammar'||x.category==='spelling'));
  const feedbackHtml=proofIssues.length ? `<div><b>စာလုံးပေါင်း၊ သတ်ပုံနှင့် သဒ္ဒါ Feedback</b><ul>${proofIssues.map(x=>`<li>${esc(x.message||'ပြန်စစ်ရန်လိုသည်။')}${x.text?` — <span style="color:#dc2626;text-decoration:underline wavy">${esc(x.text)}</span>`:''}${x.replacement?` → <b>${esc(x.replacement)}</b>`:''}</li>`).join('')}</ul></div>` : '';
  const criteria=`
    <div><b>၁။ စာလုံးပေါင်းနှင့် သတ်ပုံ စစ်ဆေးခြင်း</b><span>မြန်မာစာအဖွဲ့မှ ထုတ်ဝေသော “မြန်မာစာလုံးပေါင်းသတ်ပုံကျမ်း” ကို အဓိကအကိုးအကားအဖြစ်ထားပြီး ဝိဝါဒကွဲပြားမှုများ၊ အသံတူစာလုံးလွဲများ၊ ယပင့်/ရရစ်၊ ဝဆွဲ/ဟထိုးနှင့် စာကြောင်းအလိုက် အဓိပ္ပာယ်မှန်/မမှန်ကို စစ်ဆေးသည်။</span></div>
    <div><b>၂။ ဝါကျဖွဲ့စည်းပုံနှင့် ဝါစင်္ဂ စစ်ဆေးခြင်း</b><span>ကတ္တား + ကမ္မ + ကိရိယာ မဏ္ဍိုင်၊ ဝိဘတ်အသုံးအနှုန်းနှင့် ဝါကျအတွင်း အစိတ်အပိုင်းများ အချိတ်အဆက်မိမှုကို စစ်ဆေးသည်။</span></div>
    <div><b>၃။ အရေးအသား စတိုင်လ် ညီညွတ်မှု</b><span>စကားပြောနှင့် အရေးအသား မရောနှောခြင်း၊ “သည်/တယ်”၊ “မှ/က”၊ “သို့/ကို” စသည့် အသုံးအနှုန်းများနှင့် ဝါကျအဆုံးသတ်ပုံ တစ်ပြေးညီမှုကို စစ်ဆေးသည်။</span></div>
    <div><b>၄။ ပုဒ်ဖြတ်ပုဒ်ရပ်နှင့် သင်္ကေတများ</b><span>ပုဒ်ဖြတ် (၊) နှင့် ပုဒ်မ (။) ကို အဓိပ္ပာယ်နှင့် ရပ်နားရာနေရာအလိုက် မှန်ကန်စွာ အသုံးပြုထားခြင်းရှိမရှိ စစ်ဆေးသည်။</span></div>`;
  panel.innerHTML=`<div style="display:grid;gap:14px">
    <div><b>အဆိုအချေ ခွဲခြမ်းစိတ်ဖြာမှု</b><p style="margin:6px 0">အဆိုအမျိုးအစား — ${esc(d.proposition_type_label||'')} · ရပ်တည်ချက် — ${esc(d.stance_label||'')}</p></div>
    <div class="debate-rubric-box"><div><div>အဆိုအချေ ရမှတ်</div><div class="debate-rubric-total">${total} out of 10</div></div>
      <div class="debate-rubric-grid">
        <div class="debate-mark"><b>မိမိရပ်တည်ချက် အစပြုခြင်း</b><span>${mark2}/2</span></div>
        <div class="debate-mark"><b>${d.proposition_type==='balanced_two_sided'?'မရပ်တည်သောဘက်၏ အားနည်းချက်':'စာကိုယ် (၃) — သတ်မှတ်ချက်'}</b><span>${mark3a}/3</span></div>
        <div class="debate-mark"><b>${d.proposition_type==='balanced_two_sided'?'ရပ်တည်သောဘက်၏ အားသာချက်':'စာကိုယ် (၄) — သတ်မှတ်ချက်'}</b><span>${mark3b}/3</span></div>
        <div class="debate-mark"><b>နိဂုံး / ရပ်တည်ချက် အတည်ပြုခြင်း</b><span>${mark2c}/2</span></div>
      </div>
    </div>
    <div><b>သင်ပေးထားသော အဆိုအချေ အမှတ်ပေးစံနှုန်း</b><div class="debate-criteria-list">${criteria}</div></div>
    <div><b>အမှတ်၏ အဓိပ္ပာယ်ဖော်ပြချက်</b><p class="debate-marking-note">${total>=9?'9–10: အလွန်ကောင်းမွန်သော တုံ့ပြန်မှု။':total>=7?'7–8: ကောင်းမွန်သော တုံ့ပြန်မှု။':total>=5?'5–6: သင့်တင့်သော တုံ့ပြန်မှု။':total>=3?'3–4: အားနည်းသော တုံ့ပြန်မှု။':'0–2: တိုးတက်ရန် အဓိကလိုအပ်သော တုံ့ပြန်မှု။'} ဤ band interpretation သည် online essay marking references များတွင် တွေ့ရသော 9–10 / 7–8 / 5–6 / 3–4 / 0–2 score bands ကို reference အဖြစ်သာ အသုံးပြုပြီး၊ အမှတ်တွက်ခြင်းကို သင်ပေးထားသော 2+3+3+2 အဆိုအချေ criteria အတိုင်းပဲ ပြုလုပ်ထားသည်။</p></div>
    <div><b>အားသာချက်များ</b><ul>${d.strengths.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>
    <div><b>အားနည်းချက်များ / ပြင်ဆင်ရန်</b><ul>${d.weaknesses.length?d.weaknesses.map(x=>`<li>${esc(x)}</li>`).join(''):'<li>အဓိကအားနည်းချက် မတွေ့ပါ။</li>'}</ul></div>
    ${feedbackHtml}
    <div><b>${esc(d.rubric_marks?.pattern||'ပုံစံ')} အကြံပြု ၄ ပိုဒ်ဖွဲ့စည်းပုံ</b><ol>${d.recommended_structure.map(x=>`<li>${esc(x)}</li>`).join('')}</ol></div>
  </div>`;
  document.querySelector('main')?.appendChild(panel);
  // Debate has its own 10-mark result and intentionally has no CEFR level.
  // Stop here so the essay-only renderer below cannot access d.level/d.target_label.
  return;
}
document.getElementById('overall').textContent=d.scores.overall;setText('levelChip',d.level);setText('targetLevel',d.target_label);
const CIRC=326.7,off=CIRC-(Math.max(0,Math.min(100,d.scores.overall))/100)*CIRC;
const dialFill=document.getElementById('dialFill');if(dialFill)dialFill.style.strokeDashoffset=off;
updateRuler(d.level);
setText('levelText',`Estimated ${d.level} writing. Weighted score: ${d.scores.overall}/100. Raw profile: ${d.raw_level}; core-skill ceiling: ${d.weakest_core_level}. Next target: ${d.target_level}.`);setText('targetText',`Suggestions are calibrated above ${d.level}: aim for ${d.target_label} precision, linking and vocabulary.`);const scoresBox=document.getElementById('scores');if(scoresBox)scoresBox.innerHTML=Object.entries(SCORE_LABELS[eduLanguage]).map(([k,v])=>`<div class="score"><div class="score-head"><label>${v}</label><strong>${d.scores[k]}</strong></div><div class="bar"><i style="width:${d.scores[k]}%"></i></div></div>`).join('');
const typeHint=document.getElementById('detectedTypeHint');if(typeHint)typeHint.textContent=d.detected_essay_type?`Detected essay type: ${d.detected_essay_type}`:'Essay type is detected automatically from your writing.';
const rb=d.rubric;const rubricBox=document.getElementById('rubricScore');
if(rubricBox){
  if(rb&&rb.predicted_score){
    const crit=rb.criteria?Object.entries(rb.criteria).map(([k,v])=>`<span class="rubric-crit"><b>${esc(String(v))}</b>${esc(k)}</span>`).join(''):'';
    rubricBox.className='rubric-score';
    rubricBox.innerHTML=`<div class="rubric-head"><span class="rubric-label">${esc(rb.label)}</span><span class="rubric-predicted">${esc(rb.predicted_score)}</span></div>${crit?`<div class="rubric-crits">${crit}</div>`:''}<p class="rubric-note">${esc(rb.note||'')}</p>`;
  }else{
    rubricBox.className='rubric-score empty';
    rubricBox.textContent=rb?.note||'Choose a grading standard above and analyze to see a calibrated score prediction.';
  }
}
const statusIcon={strong:'✅',developing:'🟡',weak:'🔴','n/a':'⚪'};
const auditBox=document.getElementById('auditPipeline');
if(auditBox){
  const steps=d.audit_pipeline||[];
  auditBox.className='audit-pipeline';
  auditBox.innerHTML=steps.length?steps.map(s=>`<div class="audit-step ${esc(s.status)}"><div class="audit-step-head"><b>${statusIcon[s.status]||'•'} ${esc(s.name)}</b>${s.score!=null?`<span class="audit-score">${s.score}/100</span>`:''}</div><p>${esc(s.detail||'')}</p></div>`).join(''):'<div class="empty">Enter an essay title/topic and analyze your writing.</div>';
}
const issueClass=x=>x.type==='spelling'?'spelling':x.type==='grammar'?'grammar':x.type==='vocabulary'?'vocabulary':x.type==='accuracy'?'accuracy':'coherence';
const issuesBox=document.getElementById('issues');
if(issuesBox){
  issuesBox.className='list';
  issuesBox.innerHTML=d.issues.length?d.issues.map((x,i)=>{
    const hasFix=x.replacement!=null && x.replacement!==x.text && x.start!=null && x.end!=null;
    const original=x.text?`<span class="orig">“${esc(x.text)}”</span>`:'';
    const arrow=hasFix?` <span class="fix-arrow">→</span> <span class="fix">“${esc(x.replacement)}”</span>`:'';
    const tag=hasFix?'button':'div';
    const extraAttrs=hasFix?`data-issue-index="${i}" type="button"`:'';
    return `<${tag} class="issue ${issueClass(x)} ${hasFix?'clickable':''}" ${extraAttrs}><div><b>${esc(x.type==='spelling'?'SPELLING':x.type)}</b>${original||arrow?`<small>${original}${arrow}</small>`:''}</div><p>${esc(x.message)}${x.detail?`<br><span class="detail">${esc(x.detail)}</span>`:''}${hasFix?' <em>Click to apply this correction.</em>':''}</p></${tag}>`;
  }).join(''):'<div class="empty">✓ No obvious rule-based issues found.</div>';
}
document.querySelectorAll('#issues .clickable').forEach(btn=>btn.addEventListener('click',()=>applyIssueFix(Number(btn.dataset.issueIndex))));
const suggestionsBox=document.getElementById('suggestions');
if(suggestionsBox){
  suggestionsBox.className='list';
  suggestionsBox.innerHTML=d.suggestions.length?d.suggestions.map((x,i)=>{
    const alts=Array.isArray(x.alternatives)?x.alternatives:[];
    const choices=alts.length?`<div class="alt-row">${alts.map((a,j)=>`<button class="alt-btn" type="button" data-suggestion-index="${i}" data-alt-index="${j}" title="${esc(a.why)}">${esc(a.word)}</button>`).join('')}</div>`:'';
    const clickClass=!alts.length&&x.replacement!=null?'clickable':'';
    return `<div class="suggestion ${esc(x.kind)} ${clickClass}" ${clickClass?`data-suggestion-index="${i}"`:''}><span class="emoji">${esc(x.emoji)}</span><div><b>${esc(x.category==='repetition'?'REPEATED WORD · WAYS TO VARY':x.kind.toUpperCase())}</b><p>${esc(x.text)}</p>${x.detail?`<small class="suggestion-detail">${esc(x.detail)}</small>`:''}${choices}</div></div>`;
  }).join(''):'<div class="empty">No additional suggestions.</div>';
}
document.querySelectorAll('#suggestions .alt-btn').forEach(btn=>btn.addEventListener('click',(ev)=>{ev.stopPropagation();applySuggestion(Number(btn.dataset.suggestionIndex),Number(btn.dataset.altIndex))}));
document.querySelectorAll('#suggestions .clickable').forEach(btn=>btn.addEventListener('click',()=>applySuggestion(Number(btn.dataset.suggestionIndex))));
const paraBox=document.getElementById('paragraphFeedback');
if(paraBox){paraBox.className='feedback';paraBox.innerHTML=`<span class="feedback-icon">✦</span><p>${esc(d.paragraph_feedback)}</p>`;}
setText('linkLevel',`${d.target_level} examples`);
const linkingBox=document.getElementById('linkingWords');
if(linkingBox){linkingBox.className='links';linkingBox.innerHTML=d.linking_words.map(x=>`<span>${esc(x)}</span>`).join('');}
const statsBox=document.getElementById('stats');
if(statsBox){statsBox.innerHTML=Object.entries({'Words':d.stats.words,'Sentences':d.stats.sentences,'Characters':d.stats.characters,'Unique words':d.stats.unique_words,'Type-token ratio':d.stats.type_token_ratio,'Academic word ratio':d.stats.academic_word_ratio,'Avg. sentence words':d.stats.avg_sentence_words}).map(([k,v])=>`<div class="stat"><b>${v}</b><small>${k}</small></div>`).join('');}
}
function applyIssueFix(index){
  const x=lastAnalysis?.issues?.[index];
  if(!x || x.start==null || x.end==null || x.replacement==null) return;
  const before=e.value.slice(0,x.start), after=e.value.slice(x.end);
  e.focus();
  e.value=before+x.replacement+after;
  const cursor=x.start+x.replacement.length;
  e.setSelectionRange(cursor,cursor);
  lastAnalysis=null; layer.innerHTML=''; updateLive();
  status.innerHTML='<span class="dot"></span> Correction applied — analyze again to refresh feedback';
}
function applySuggestion(index, altIndex=null){
  const x=lastAnalysis?.suggestions?.[index];
  const chosen=(altIndex!=null && Array.isArray(x?.alternatives))?x.alternatives[altIndex]?.word:x?.replacement;
  if(!x || x.start==null || x.end==null || chosen==null) return;
  const before=e.value.slice(0,x.start), after=e.value.slice(x.end);
  e.focus();
  e.value=before+chosen+after;
  const cursor=x.start+chosen.length;
  e.setSelectionRange(cursor,cursor);
  lastAnalysis=null; layer.innerHTML=''; updateLive();
  status.innerHTML='<span class="dot"></span> Suggestion applied — analyze again to refresh feedback';
}
function openRepeatPopover(item, anchor){
  const pop=document.getElementById('repeatPopover'), info=document.getElementById('repeatWordInfo'), choices=document.getElementById('repeatChoices');
  if(!pop||!choices)return;
  info.innerHTML=`<b>“${esc(item.word||e.value.slice(item.start,item.end))}”</b> is repeated ${item.count||2} times.`;
  choices.innerHTML='';
  (item.alternatives||[]).forEach((a,idx)=>{
    const b=document.createElement('button'); b.className='repeat-choice'; b.type='button'; b.textContent=a.word; b.title=a.why||'';
    b.onclick=()=>{applySuggestionItem(item,a.word); pop.classList.add('hidden')}; choices.appendChild(b);
  });
  const r=anchor.getBoundingClientRect();
  pop.classList.remove('hidden');
  const maxLeft=window.innerWidth-pop.offsetWidth-12;
  pop.style.left=Math.max(12,Math.min(r.left,maxLeft))+'px';
  pop.style.top=Math.min(window.innerHeight-pop.offsetHeight-12,r.bottom+8)+'px';
}
function applySuggestionItem(item, chosen){
  if(!item || item.start==null || item.end==null || !chosen)return;
  e.focus();
  e.value=e.value.slice(0,item.start)+chosen+e.value.slice(item.end);
  const cursor=item.start+chosen.length; e.setSelectionRange(cursor,cursor);
  lastAnalysis=null; layer.innerHTML=''; updateLive();
  status.innerHTML='<span class="dot"></span> Repeated word replaced — analyze again to refresh feedback';
}
document.getElementById('repeatClose')?.addEventListener('click',()=>document.getElementById('repeatPopover')?.classList.add('hidden'));
document.addEventListener('click',ev=>{
  const pop=document.getElementById('repeatPopover');
  if(pop && !pop.contains(ev.target) && !ev.target.closest('.repeat-word')) pop.classList.add('hidden');
});
function renderHighlights(items){
  if(!items.length){layer.innerHTML=esc(e.value).replace(/\n/g,'<br>');syncScroll();return}
  let sorted=[...items].sort((a,b)=>a.start-b.start||a.end-b.end),html='',pos=0;
  for(const x of sorted){
    if(x.start<pos)continue;
    html+=esc(e.value.slice(pos,x.start));
    const hasFix=x.replacement!=null&&x.replacement!==x.text;
    const isRepeat=x.category==='repetition'&&Array.isArray(x.alternatives)&&x.alternatives.length;
    const tip=isRepeat?`${x.message} Click for alternatives`:hasFix?`${x.message} → Correct: "${x.replacement}"`:x.message;
    const cls=`hl ${x.type==='spelling'?'spelling':x.type==='grammar'?'grammar':x.type==='vocabulary'?'vocabulary':x.type==='accuracy'?'accuracy':'coherence'} ${isRepeat?'repeat-word':''}`;
    html+=`<span class="${cls}" data-highlight-index="${items.indexOf(x)}" title="${esc(tip)}">${esc(e.value.slice(x.start,x.end))}</span>`;
    pos=x.end
  }
  html+=esc(e.value.slice(pos)); layer.innerHTML=html.replace(/\n/g,'<br>'); syncScroll();
  layer.querySelectorAll('.repeat-word').forEach(node=>{
    node.addEventListener('click',ev=>{ev.preventDefault();ev.stopPropagation();const item=items[Number(node.dataset.highlightIndex)];if(item)openRepeatPopover(item,node)});
  });
}
function resetUI(){document.getElementById('overall').textContent='0';document.getElementById('levelChip').textContent='A1';document.getElementById('targetLevel').textContent='B2';const df=document.getElementById('dialFill');if(df)df.style.strokeDashoffset='326.7';updateRuler('A1');document.getElementById('levelText').textContent='Analyze your writing to estimate your CEFR-style level.';const rb=document.getElementById('rubricScore');if(rb){rb.className='rubric-score empty';rb.textContent='Choose a grading standard above and analyze to see a calibrated score prediction.'}const ap=document.getElementById('auditPipeline');if(ap){ap.className='audit-pipeline empty';ap.textContent='Enter an essay title/topic and analyze your writing.'}document.getElementById('issues').className='list empty';document.getElementById('issues').textContent='No analysis yet.';document.getElementById('suggestions').className='list empty';document.getElementById('suggestions').textContent='Suggestions will appear here.';document.getElementById('paragraphFeedback').className='feedback empty';document.getElementById('paragraphFeedback').textContent='Write a paragraph and analyze it to receive feedback.';document.getElementById('linkingWords').className='links empty';document.getElementById('linkingWords').textContent='Examples will appear here.';document.getElementById('stats').innerHTML='';const th=document.getElementById('detectedTypeHint');if(th)th.textContent='Essay type is detected automatically from your writing.';resetIdeaMap()}

// --- Idea Map / Architecture Sketch ------------------------------------
let lastIdeaMapSvg=null;
const ideaMapCanvas=document.getElementById('ideaMapCanvas'),ideaMapBtn=document.getElementById('ideaMapBtn'),ideaMapDownloadSvg=document.getElementById('ideaMapDownloadSvg'),ideaMapDownloadJpg=document.getElementById('ideaMapDownloadJpg'),ideaMapHint=document.getElementById('ideaMapHint'),sketchToggle=document.getElementById('sketchToggle');
function resetIdeaMap(){lastIdeaMapSvg=null;if(ideaMapCanvas){ideaMapCanvas.className='idea-map-canvas empty';ideaMapCanvas.textContent="Write an essay, then analyze or generate an essay to see its structure visually."}if(ideaMapDownloadSvg)ideaMapDownloadSvg.disabled=true;if(ideaMapDownloadJpg)ideaMapDownloadJpg.disabled=true;if(ideaMapHint)ideaMapHint.textContent="Builds a thesis → main points → supporting ideas diagram directly from your text. No AI call, no coins. Generated automatically when you analyze or generate an essay."}
async function generateIdeaMap(opts={}){
  const silent=!!opts.silent;
  const autoScroll=opts.autoScroll!==false; // default true: auto-show the panel once the map renders
  if(!e.value.trim()){if(!silent)ideaMapHint.textContent='Write a paragraph first.';return}
  if(ideaMapBtn)ideaMapBtn.disabled=true;
  ideaMapHint.textContent='Generating idea map…';
  try{
    const r=await fetch('/edu/api/idea-map',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:e.value,title:document.getElementById('essayTitle')?.value||'',include_sketch:sketchToggle?sketchToggle.checked:true})});
    const d=await r.json();
    if(!r.ok||d.ok===false){ideaMapHint.textContent=esc(d.error||'Could not generate idea map.');return}
    lastIdeaMapSvg=d.combined_svg||d.diagram_svg;
    ideaMapCanvas.className='idea-map-canvas';
    ideaMapCanvas.innerHTML=lastIdeaMapSvg;
    ideaMapDownloadSvg.disabled=false;ideaMapDownloadJpg.disabled=false;
    const branchCount=(d.structure?.branches||[]).length;
    ideaMapHint.textContent=`Mapped ${branchCount} main point${branchCount===1?'':'s'} from your essay.`;
    if(autoScroll)showIdeaMapPanel();
  }catch(err){ideaMapHint.textContent='Idea map generation failed.'}
  finally{if(ideaMapBtn)ideaMapBtn.disabled=false}
}
function showIdeaMapPanel(){
  const panel=document.querySelector('.idea-map-panel');
  if(panel)panel.scrollIntoView({behavior:'smooth',block:'start'});
}
if(ideaMapBtn){ideaMapBtn.onclick=()=>generateIdeaMap()}
if(ideaMapDownloadSvg){
  ideaMapDownloadSvg.onclick=()=>{
    if(!lastIdeaMapSvg)return;
    const blob=new Blob([lastIdeaMapSvg],{type:'image/svg+xml'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='idea-map.svg';document.body.appendChild(a);a.click();document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };
}
function svgViewBoxSize(svgText){
  const m=svgText.match(/viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"/);
  return m?{w:parseFloat(m[1]),h:parseFloat(m[2])}:{w:1100,h:700};
}

// Crop-resistant watermark for downloaded idea-map JPEGs.
//
// A single mark in one corner (the old approach) can simply be cropped
// out of the image. To make the watermark survive cropping, this stamps
// the TSO Edu mark in two independent, redundant ways:
//   1. A diagonal, low-opacity pattern of the wordmark tiled across the
//      *entire* canvas — any crop still large enough to be a usable idea
//      map (more than one tile spacing in either dimension) keeps at
//      least one repeat of the mark.
//   2. A solid, high-contrast brand banner (logo + text) fixed to the
//      bottom edge of the full image, for a clean, always-legible credit
//      on the untouched export.
// Neither layer is a removable overlay the user can toggle off — both are
// flattened directly into the JPEG's pixels before it's ever encoded.
function drawTsoWatermark(canvas,ctx,logoImg){
  const W=canvas.width,H=canvas.height;

  // --- 1) Tiled diagonal pattern across the whole image ---------------
  const tileFontPx=Math.max(16,Math.round(W*0.028));
  ctx.save();
  ctx.font=`700 ${tileFontPx}px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif`;
  ctx.fillStyle='rgba(120,90,220,0.10)';
  ctx.textAlign='center';
  ctx.textBaseline='middle';
  const tileText='TSO EDU';
  const stepX=Math.max(160,tileFontPx*9);
  const stepY=Math.max(120,tileFontPx*6.5);
  ctx.translate(W/2,H/2);
  ctx.rotate(-Math.PI/8);
  const span=Math.sqrt(W*W+H*H);
  for(let y=-span;y<span;y+=stepY){
    for(let x=-span;x<span;x+=stepX){
      ctx.fillText(tileText,x,y);
    }
  }
  ctx.restore();

  // --- 2) Solid brand banner along the bottom edge ---------------------
  const bannerH=Math.max(40,Math.round(H*0.055));
  ctx.save();
  ctx.fillStyle='rgba(20,16,40,0.82)';
  ctx.fillRect(0,H-bannerH,W,bannerH);

  const pad=Math.round(bannerH*0.2);
  let textStartX=pad;
  if(logoImg){
    const logoH=bannerH-pad*2;
    const logoW=logoH*(logoImg.width/logoImg.height);
    ctx.drawImage(logoImg,pad,H-bannerH+pad,logoW,logoH);
    textStartX=pad+logoW+pad*0.8;
  }
  const bannerFontPx=Math.round(bannerH*0.4);
  ctx.font=`600 ${bannerFontPx}px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif`;
  ctx.fillStyle='rgba(255,255,255,0.95)';
  ctx.textAlign='left';
  ctx.textBaseline='middle';
  ctx.fillText('created with TSO Edu',textStartX,H-bannerH/2);
  ctx.restore();
}

function finishJpegExport(canvas){
  canvas.toBlob(blob=>{
    if(!blob){ideaMapHint.textContent='JPEG export failed.';ideaMapDownloadJpg.disabled=false;return}
    const jurl=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=jurl;a.download='idea-map.jpg';document.body.appendChild(a);a.click();document.body.removeChild(a);
    URL.revokeObjectURL(jurl);
    ideaMapHint.textContent='Idea map saved as JPEG.';ideaMapDownloadJpg.disabled=false;
  },'image/jpeg',0.95);
}

if(ideaMapDownloadJpg){
  ideaMapDownloadJpg.onclick=()=>{
    if(!lastIdeaMapSvg)return;
    ideaMapDownloadJpg.disabled=true;ideaMapHint.textContent='Preparing JPEG…';
    const{w,h}=svgViewBoxSize(lastIdeaMapSvg);
    const scale=2; // render at 2x for a crisp, print-quality JPEG
    const svgBlob=new Blob([lastIdeaMapSvg],{type:'image/svg+xml;charset=utf-8'});
    const url=URL.createObjectURL(svgBlob);
    const img=new Image();
    img.onload=()=>{
      const canvas=document.createElement('canvas');
      canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale);
      const ctx=canvas.getContext('2d');
      // JPEG has no transparency — paint a white backing so it isn't black
      ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.drawImage(img,0,0,canvas.width,canvas.height);
      URL.revokeObjectURL(url);
      // Load the TSO Edu logo, then stamp the crop-resistant watermark
      // (see drawTsoWatermark) before the JPEG is finalized.
      const logo=new Image();
      logo.onload=()=>{ drawTsoWatermark(canvas,ctx,logo); finishJpegExport(canvas); };
      logo.onerror=()=>{ drawTsoWatermark(canvas,ctx,null); finishJpegExport(canvas); };
      logo.src='/edu/edu-logo.png';
    };
    img.onerror=()=>{ideaMapHint.textContent='JPEG export failed — try Download SVG instead.';ideaMapDownloadJpg.disabled=false;URL.revokeObjectURL(url)};
    img.src=url;
  };
}
if(sketchToggle){sketchToggle.addEventListener('change',()=>{if(lastIdeaMapSvg&&ideaMapBtn)ideaMapHint.textContent='Sketch layer setting changed — click Generate idea map to refresh.'})}

// --- Ranking tab: most used Analyze / Generate tools -----------------------
(function(){
  const rankingTabBtn=document.getElementById('rankingTabBtn');
  const rankingSection=document.getElementById('rankingSection');
  const eduMainContent=document.getElementById('eduMainContent');
  const rankingTabsWrap=document.getElementById('rankingTabs');
  const rankingList=document.getElementById('rankingList');
  if(!rankingTabBtn||!rankingSection||!eduMainContent||!rankingTabsWrap||!rankingList)return;

  let leaderboardData=null;
  let activeFeature='overall';
  let leaderboardLoaded=false;
  let resetTargetMs=null;
  let countdownTimer=null;

  function medalRankClass(i){
    if(i===0)return 'top-1';
    if(i===1)return 'top-2';
    if(i===2)return 'top-3';
    return '';
  }

  function renderFeature(feature){
    activeFeature=feature;
    rankingTabsWrap.querySelectorAll('.ranking-tab').forEach(btn=>{
      btn.classList.toggle('active',btn.dataset.feature===feature);
    });
    if(!leaderboardData){
      rankingList.className='ranking-list empty';
      rankingList.textContent='Loading ranking…';
      return;
    }
    const entries=feature==='overall'
      ? (leaderboardData.overall||[])
      : ((leaderboardData.features&&leaderboardData.features[feature]&&leaderboardData.features[feature].entries)||[]);
    if(!entries.length){
      rankingList.className='ranking-list empty';
      rankingList.textContent='No usage recorded yet for this tool.';
      return;
    }
    rankingList.className='ranking-list';
    rankingList.innerHTML=entries.map((e,i)=>`
      <div class="ranking-row ${medalRankClass(i)}">
        <div class="ranking-rank">${i+1}</div>
        ${renderAvatar(e)}
        <div class="ranking-name">${escapeHtml(e.displayName||e.username||'Unknown')}</div>
        <div class="ranking-count">${e.uses}<small>use${e.uses===1?'':'s'}</small></div>
      </div>`).join('');
  }

  function renderAvatar(e){
    const initial=escapeHtml((e.displayName||e.username||'?').charAt(0).toUpperCase());
    if(e.avatar){
      return `<img class="ranking-avatar" src="${escapeHtml(e.avatar)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'ranking-avatar ranking-avatar-fallback',textContent:'${initial}'}))">`;
    }
    return `<div class="ranking-avatar ranking-avatar-fallback">${initial}</div>`;
  }

  function escapeHtml(str){
    return String(str).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  function pad2(n){return String(n).padStart(2,'0');}

  function formatCountdown(seconds){
    seconds=Math.max(0,seconds|0);
    const d=Math.floor(seconds/86400);
    const h=Math.floor((seconds%86400)/3600);
    const m=Math.floor((seconds%3600)/60);
    const s=seconds%60;
    if(d>0)return `${d}d ${pad2(h)}h ${pad2(m)}m ${pad2(s)}s`;
    return `${pad2(h)}h ${pad2(m)}m ${pad2(s)}s`;
  }

  async function loadLeaderboard(){
    rankingList.className='ranking-list empty';
    rankingList.textContent='Loading ranking…';
    try{
      const res=await fetch('/edu/api/leaderboard?limit=10');
      const data=await res.json();
      if(!data.ok){
        rankingList.textContent=data.error||'Could not load the ranking right now.';
        return;
      }
      leaderboardData=data;
      leaderboardLoaded=true;
      renderFeature(activeFeature);
      renderResetNotice(data.period);
      renderRewardsWhy(data.rewards,data.costs);
    }catch(err){
      rankingList.textContent='Could not load the ranking right now.';
    }
  }

  function renderRewardsWhy(rewards,costs){
    const el=document.getElementById('rankingRewardsWhy');
    if(!el||!rewards)return;
    const ranks=Object.keys(rewards).map(Number).sort((a,b)=>a-b);
    if(!ranks.length){el.innerHTML='';return;}
    const rankClass=r=>r<=3?` rank-${r}`:'';
    const chips=ranks.map(r=>`<span class="ranking-rewards-why-chip${rankClass(r)}"><span class="rank-num">#${r}</span> +${rewards[r]} Credits</span>`).join('');
    // Turn the top reward into a concrete "≈N free uses" figure using the
    // real per-use costs from the API, so the pitch is honest and stays in
    // sync automatically if costs or reward amounts ever change.
    let usesLine='';
    if(costs&&costs.text_analysis&&costs.essay_generation){
      const topReward=rewards[ranks[0]];
      const freeAnalyses=Math.floor(topReward/costs.text_analysis);
      const freeGenerations=Math.floor(topReward/costs.essay_generation);
      usesLine=`Rank #${ranks[0]}'s reward alone covers about ${freeAnalyses} free essay analyses or ${freeGenerations} free essay generations — on top of whatever you already used to earn it.`;
    }
    el.innerHTML=`
      <p class="ranking-rewards-why-title">🎁 Why aim for the top 5?</p>
      <div class="ranking-rewards-why-list">${chips}</div>
      <p class="ranking-rewards-why-note">Every 7 days, the top 5 most active users in <strong>Analyze essay</strong> and <strong>Generate essay</strong> (combined, under Overall) can claim a one-time Credit bonus from <strong>Tasks &amp; Rewards</strong> once the week ends — free Credits just for using the tools you were already using. ${usesLine} Rewards are claimed manually and don't carry over, so if you're close to a top-5 spot, a few more analyses or generations before the reset can be the difference.</p>`;
  }

  function renderResetNotice(period){
    const el=document.getElementById('rankingResetNotice');
    if(!el||!period)return;
    // Anchor to a fixed clock time (now + resetsInSeconds) rather than
    // just counting down a stale number, so the displayed H:M:S stays
    // accurate to the second even if this tab stays open a long time.
    resetTargetMs=Date.now()+Math.max(0,period.resetsInSeconds|0)*1000;
    tickResetNotice();
    if(countdownTimer)clearInterval(countdownTimer);
    countdownTimer=setInterval(tickResetNotice,1000);
  }

  function tickResetNotice(){
    const el=document.getElementById('rankingResetNotice');
    if(!el||resetTargetMs===null)return;
    const remainingSeconds=Math.max(0,Math.round((resetTargetMs-Date.now())/1000));
    el.textContent=`This board resets in ${formatCountdown(remainingSeconds)}. Top 5 when it resets can claim Credits under Tasks & Rewards.`;
    if(remainingSeconds<=0){
      clearInterval(countdownTimer);
      countdownTimer=null;
      // The period just rolled over — refresh from the server to pick up
      // the new (empty) week and its fresh reset target.
      loadLeaderboard();
    }
  }

  rankingTabsWrap.querySelectorAll('.ranking-tab').forEach(btn=>{
    btn.addEventListener('click',()=>renderFeature(btn.dataset.feature));
  });

  rankingTabBtn.addEventListener('click',()=>{
    const showingRanking=!rankingSection.hidden;
    if(showingRanking){
      rankingSection.hidden=true;
      eduMainContent.style.display='';
      rankingTabBtn.setAttribute('aria-pressed','false');
      if(countdownTimer){clearInterval(countdownTimer);countdownTimer=null;}
    }else{
      rankingSection.hidden=false;
      eduMainContent.style.display='none';
      rankingTabBtn.setAttribute('aria-pressed','true');
      if(!leaderboardLoaded)loadLeaderboard();
    }
  });

  // Phones hide the ☰ header menu (see style.css, max-width:760px), which
  // is where rankingTabBtn normally lives once it collapses into that
  // menu's sheet — so on phones it's not reachable at all without this.
  // The bottom quick-nav bar's Ranking button re-triggers the exact same
  // toggle by clicking the real button, reusing all the logic above
  // instead of duplicating the show/hide + leaderboard-loading behaviour.
  const mobileNavRankingBtn=document.getElementById('mobileNavRankingBtn');
  if(mobileNavRankingBtn){
    mobileNavRankingBtn.addEventListener('click',()=>{
      rankingTabBtn.click();
      mobileNavRankingBtn.classList.toggle('active', !rankingSection.hidden);
    });
  }
})();


// Button ripple styling is injected once so it works with the existing single-file app.
if(!document.getElementById('eduRippleStyle')){
  const eduRippleStyle=document.createElement('style');
  eduRippleStyle.id='eduRippleStyle';
  eduRippleStyle.textContent='.edu-tool-button,.coach-launch-button{position:relative;overflow:hidden}.edu-ripple{position:absolute;width:12px;height:12px;border-radius:50%;background:rgba(124,58,237,.22);transform:translate(-50%,-50%) scale(0);pointer-events:none;animation:eduRipple .5s ease-out forwards}@keyframes eduRipple{to{transform:translate(-50%,-50%) scale(24);opacity:0}}';
  document.head.appendChild(eduRippleStyle);
}

// TSO Edu tool navigation: scroll to the requested workspace panel.
// (Superseded by the "Premium Studio navigation" handler below, which
// includes this same getElementById behavior plus the idea-map-panel
// resolution and focus-highlight effect. Keeping both bound the same
// buttons twice — competing scrollIntoView/focus calls on every click,
// and a visible double-scroll for the Ideas button specifically, since
// the two handlers resolved it to two different elements.)

// TSO Edu Natural Writing Coach: intentionally separate from Analyze and Generate.
(function(){
  const btn=document.getElementById('naturalWritingBtn');
  if(!btn) return;
  const hint=document.getElementById('naturalWritingHint');
  const result=document.getElementById('naturalWritingResult');
  const before=document.getElementById('naturalBefore');
  const after=document.getElementById('naturalAfter');
  const count=document.getElementById('naturalChangeCount');
  const list=document.getElementById('naturalChangeList');
  const draftEditor=document.getElementById('editor');
  btn.addEventListener('click', async()=>{
    const text=(draftEditor?.value||'').trim();
    if(!text){hint.textContent='Please write or paste your own draft in the Writing Editor first.';hint.classList.add('bad');draftEditor?.focus();return;}
    if(!authToken){hint.textContent='Please open TSO Edu after signing in.';hint.classList.add('bad');return;}
    btn.disabled=true; hint.classList.remove('bad'); hint.textContent='Improving your draft locally… No external AI API is used.'; result.hidden=true;
    try{
      const r=await fetch('/edu/api/natural-writing?token='+encodeURIComponent(authToken),{
        method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json','Authorization':'Bearer '+authToken},credentials:'same-origin',
        body:JSON.stringify({text,level:document.getElementById('naturalLevel')?.value||'B2',style:document.getElementById('naturalStyle')?.value||'student',language:typeof eduLanguage!=='undefined'?eduLanguage:'en',token:authToken})
      });
      const d=await r.json();
      if(!r.ok||d.ok===false){
        if(r.status===402 && typeof d.tsoCoins==='number') hint.textContent=(d.error||'Not enough TSO Credits.')+' Balance: '+d.tsoCoins+' TSO Credits.';
        else hint.textContent=d.error||'Natural Writing Coach is unavailable.';
        hint.classList.add('bad'); return;
      }
      before.textContent=d.original||text; after.textContent=d.improved||text;
      const changes=Array.isArray(d.changes)?d.changes:[];
      count.textContent=`${changes.length} suggested change${changes.length===1?'':'s'}`;
      list.innerHTML=changes.map(c=>`<li><b>${esc(c.from||'')}</b> → <b>${esc(c.to||'')}</b> — ${esc(c.reason||'')}</li>`).join('') || '<li>No formulaic patterns needed changing. Your draft was preserved.</li>';
      result.hidden=false;
      if(!result.dataset.view) result.dataset.view='compare';
      hint.textContent='Review the suggestions and keep only changes that sound like you. This tool improves a draft; it does not create a new essay or prove that text is human-written.';
      if(typeof d.tsoCoins==='number') document.getElementById('coinBalanceHint')?.replaceChildren(document.createTextNode(`Balance: ${d.tsoCoins} TSO`));
    }catch(err){hint.textContent='Could not connect to the local Natural Writing Engine.';hint.classList.add('bad');}
    finally{btn.disabled=false;}
  });

  // Small-mobile Original | Improved | Compare toggle. Only meaningful
  // under the 480px breakpoint where the CSS switches to single-pane
  // view — at wider widths the toggle is hidden and both panes always
  // show side-by-side, so this just tracks which pane to reveal.
  const compareToggle=document.getElementById('naturalCompareToggle');
  if(compareToggle){
    result.dataset.view='compare';
    compareToggle.addEventListener('click',e=>{
      const b=e.target.closest('button[data-view]');
      if(!b) return;
      compareToggle.querySelectorAll('button').forEach(x=>x.classList.remove('active'));
      b.classList.add('active');
      result.dataset.view=b.dataset.view;
    });
  }
})();


// Premium Studio navigation: always reveal the actual requested tool and give it a brief focus state.
(function(){
  function resolveTarget(id){
    if(id==='ideaMapCanvas') return document.querySelector('.idea-map-panel') || document.getElementById(id);
    return document.getElementById(id);
  }
  document.querySelectorAll('[data-scroll-target]').forEach(btn=>{
    if(btn.dataset.studioNavBound==='1') return;
    btn.dataset.studioNavBound='1';
    btn.addEventListener('click',()=>{
      const target=resolveTarget(btn.getAttribute('data-scroll-target'));
      if(!target) return;
      document.querySelectorAll('.coach-focus').forEach(el=>el.classList.remove('coach-focus'));
      target.classList.add('coach-focus');
      if(!target.hasAttribute('tabindex')) target.setAttribute('tabindex','-1');
      requestAnimationFrame(()=>target.scrollIntoView({behavior:'smooth',block:'start'}));
      setTimeout(()=>{try{target.focus({preventScroll:true})}catch(e){}},520);
      setTimeout(()=>target.classList.remove('coach-focus'),2800);
    });
  });
})();

// --- Header: mobile menu sheet ---------------------------------------------
// Below 900px the header's section-nav links and secondary controls
// (ranking, status, back-to-job-board) move into a slide-out sheet
// instead of being crammed into the header row. The language switch is
// deliberately excluded from this cluster — it stays fixed in the header
// row at every width (see #eduLanguageSwitch in the template) so it is
// never hidden behind an extra tap on phones. Secondary controls are the
// same elements moved in place (same ids, so every existing event
// listener bound to them keeps working); the nav links are separate
// buttons sharing the generic data-scroll-target mechanism.
// 900px matches the breakpoint where .edu-primary-nav is hidden by CSS —
// keeping these two in sync means there's never a width where navigation
// is not reachable through either the pill nav or this menu.
(function(){
  const menuBtn=document.getElementById('eduHeaderMenuBtn');
  const sheet=document.getElementById('eduHeaderSheet');
  const backdrop=document.getElementById('eduHeaderSheetBackdrop');
  const closeBtn=document.getElementById('eduHeaderSheetClose');
  const sheetBody=document.getElementById('eduHeaderSheetBody');
  const secondary=document.getElementById('eduHeaderSecondary');
  if(!menuBtn||!sheet||!backdrop||!closeBtn||!sheetBody||!secondary) return;

  const homeParent=secondary.parentElement;
  const mq=window.matchMedia('(max-width:900px)');
  let placedInSheet=false;

  function placeControls(inSheet){
    if(inSheet===placedInSheet) return;
    if(inSheet) sheetBody.appendChild(secondary);
    else homeParent.insertBefore(secondary, document.getElementById('eduHeaderMenuBtn'));
    placedInSheet=inSheet;
  }
  function syncPlacement(){ placeControls(mq.matches); }
  syncPlacement();
  mq.addEventListener ? mq.addEventListener('change',syncPlacement) : mq.addListener(syncPlacement);

  function openSheet(){
    secondary.hidden=false;
    sheet.hidden=false; backdrop.hidden=false;
    requestAnimationFrame(()=>{sheet.classList.add('open');backdrop.classList.add('open')});
    menuBtn.setAttribute('aria-expanded','true');
  }
  function closeSheet(){
    sheet.classList.remove('open'); backdrop.classList.remove('open');
    menuBtn.setAttribute('aria-expanded','false');
    setTimeout(()=>{ if(!sheet.classList.contains('open')){ sheet.hidden=true; backdrop.hidden=true; } },260);
  }
  menuBtn.addEventListener('click',openSheet);
  closeBtn.addEventListener('click',closeSheet);
  backdrop.addEventListener('click',closeSheet);
  // Close the sheet once a section-jump link inside it is used, so the
  // sheet doesn't stay open covering the section the user just scrolled to.
  sheet.querySelector('.edu-header-sheet-nav')?.addEventListener('click', e=>{
    if(e.target.closest('button[data-scroll-target]')) closeSheet();
  });
  document.addEventListener('keydown',e=>{ if(e.key==='Escape' && sheet.classList.contains('open')) closeSheet(); });
})();

// --- Mobile bottom quick-nav: sliding indicator + active icon scale --------
// Bar scrolls horizontally now (variable-width flex items) rather than a
// fixed equal-width grid, so the indicator is positioned from each
// button's real pixel geometry (offsetLeft/offsetWidth) instead of a
// column-index percentage — that math only worked when every column had
// the same fixed width.
(function(){
  const nav=document.getElementById('eduMobileNav');
  const indicator=document.getElementById('eduMobileNavIndicator');
  if(!nav||!indicator) return;
  const navBtns=[...nav.querySelectorAll('button[data-scroll-target]')];
  if(!navBtns.length) return;

  function moveIndicatorTo(btn){
    // btn.offsetLeft/offsetWidth are relative to nav (the offsetParent,
    // since nav is position:fixed and btn has no positioned ancestor in
    // between), and unaffected by nav's current scroll position — so the
    // indicator stays correctly placed under btn whether or not btn is
    // presently scrolled into view.
    indicator.style.left = btn.offsetLeft + 'px';
    indicator.style.width = btn.offsetWidth + 'px';
  }
  function setActive(btn, scrollIntoView){
    navBtns.forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    moveIndicatorTo(btn);
    if(scrollIntoView) btn.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});
  }
  navBtns.forEach(b=>b.addEventListener('click',()=>setActive(b,false)));
  // Keep the indicator aligned on resize/orientation-change, since button
  // widths can change (e.g. label truncation threshold) even though the
  // active button doesn't.
  window.addEventListener('resize',()=>{
    const active=navBtns.find(b=>b.classList.contains('active'));
    if(active) moveIndicatorTo(active);
  });
  setActive(navBtns[0], false);

  // Keep the indicator in sync with whichever section the desktop nav
  // observer (below) determines is current, since both bars point at
  // the same section ids/targets. Auto-scroll the bar so the newly-active
  // item is visible, since not all 9 items fit on screen at once.
  const targets=navBtns.map(btn=>{
    const id=btn.getAttribute('data-scroll-target');
    const el = id==='ideaMapCanvas' ? (document.querySelector('.idea-map-panel')||document.getElementById(id)) : document.getElementById(id);
    return {btn, el};
  }).filter(t=>t.el);
  if(targets.length){
    const io=new IntersectionObserver(entries=>{
      const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];
      if(visible){ const match=targets.find(t=>t.el===visible.target); if(match) setActive(match.btn,true); }
    },{rootMargin:'-40% 0px -40% 0px',threshold:[0,.1,.25,.5]});
    targets.forEach(t=>io.observe(t.el));
  }
})();

// --- Header: desktop primary nav — highlight the section currently in view -
(function(){
  const navBtns=[...document.querySelectorAll('.edu-primary-nav button[data-scroll-target]')];
  if(!navBtns.length) return;
  const targets=navBtns.map(btn=>{
    const id=btn.getAttribute('data-scroll-target');
    const el = id==='ideaMapCanvas' ? (document.querySelector('.idea-map-panel')||document.getElementById(id)) : document.getElementById(id);
    return {btn, el};
  }).filter(t=>t.el);
  if(!targets.length) return;
  function setActive(el){
    navBtns.forEach(b=>b.classList.remove('active'));
    const match=targets.find(t=>t.el===el);
    if(match) match.btn.classList.add('active');
  }
  setActive(targets[0].el);
  const io=new IntersectionObserver(entries=>{
    const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];
    if(visible) setActive(visible.target);
  },{rootMargin:'-96px 0px -60% 0px',threshold:[0,.1,.25,.5]});
  targets.forEach(t=>io.observe(t.el));
})();
