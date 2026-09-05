(function(){
const root=document.getElementById('grammarAcademy');if(!root)return;
let lessons=[],current=0,progress={completed:[],scores:{},attempts:{},streak:0,xp:0},token=(typeof window.authToken!=='undefined'&&window.authToken)||new URLSearchParams(window.location.search).get('token')||'';
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const phase=l=>l.level==='A1'||l.level==='A2'?'FOUNDATION':l.level==='B1'?'INTERMEDIATE':'ADVANCED';
async function api(url,opts={}){const headers=Object.assign({'Content-Type':'application/json'},opts.headers||{});if(token)headers.Authorization='Bearer '+token;return fetch(url,Object.assign({},opts,{headers}));}
async function load(){
 try{let r=await fetch('/edu/api/grammar/lessons');let j=await r.json();lessons=j.lessons||[];
   let pr=await api('/edu/api/grammar/progress');let pj=await pr.json();progress=pj.progress||progress;
   if(progress.certPassThreshold){grammarCertPassThreshold=progress.certPassThreshold;const t=$('grammarCertAnnounceThreshold');if(t)t.textContent=grammarCertPassThreshold+'%';}
 }catch(e){lessons=[]} renderShell();renderDays();renderLesson();renderExamSection();
}
function renderShell(){
 const done=progress.completedCount||progress.completed?.length||0, total=lessons.length||64, pct=Math.round(done/total*100);
 $('grammarProgressBar').style.width=pct+'%';
 const balance=$('grammarBalance');
 if(balance){
  if(!token){balance.textContent='Sign in to view';}
  else{
   balance.textContent='…';
   fetch('/api/credit/balance?token='+encodeURIComponent(token),{headers:{'Authorization':'Bearer '+token}})
    .then(r=>r.json())
    .then(j=>{if(j&&j.ok)balance.textContent=j.tsoCoins+' Credits';else balance.textContent='Sign in to view';})
    .catch(()=>{balance.textContent='Sign in to view';});
  }
 }
 const head=document.querySelector('.grammar-head'); if(head&&!document.getElementById('grammarStats')){
  const s=document.createElement('div');s.id='grammarStats';s.className='grammar-stats';s.innerHTML=`<span><b>${done}/${total}</b><small>Lessons</small></span><span><b>${progress.xp||0}</b><small>XP</small></span><span><b>${progress.streak||0}🔥</b><small>Streak</small></span>`;head.appendChild(s);
 }
}
function renderDays(){
 const done=new Set(progress.completed||[]);
 $('grammarDays').innerHTML=lessons.map((l,i)=>`<button class="grammar-day ${i===current?'active':''} ${done.has(l.id)?'completed':''}" data-i="${i}"><span class="grammar-day-num">${done.has(l.id)?'✓':String(l.day).padStart(2,'0')}</span><span class="grammar-day-copy"><b>${esc(l.title)}</b><small>${esc(l.level)} · ${phase(l)}</small></span><span class="grammar-day-arrow">${i===current?'→':''}</span></button>`).join('');
 document.querySelectorAll('.grammar-day').forEach(b=>b.onclick=()=>{current=+b.dataset.i;renderDays();renderLesson()});
}
function renderLesson(){
 const l=lessons[current];if(!l)return;const done=new Set(progress.completed||[]);const score=progress.scores?.[l.id];
 $('grammarContent').innerHTML=`
 <div class="lesson-hero"><div><span class="grammar-badge">DAY ${l.day} · ${esc(l.level)} · ${phase(l)}</span><h3>${esc(l.title)}</h3><p>${esc(l.summary)}</p></div><div class="lesson-score">${score!=null?`<b>${score}%</b><small>Best score</small>`:'<b>+25</b><small>XP on completion</small>'}</div></div>
 <div class="lesson-nav"><span>📖 Read</span><span>✍️ Practice</span><span>🤖 AI Coach</span><span>🏆 Master</span></div>
 <div class="grammar-section textbook"><div class="section-kicker">TEXTBOOK</div><h4>Understand the grammar</h4>
 ${l.plainExplanation?`<div class="plain-explainer">🔎 <b>In simple words:</b> ${esc(l.plainExplanation)}</div>`:''}
 ${l.illustration?`<div class="grammar-illustration"><pre>${esc(l.illustration)}</pre></div>`:''}
 <p>${esc(l.rule)}</p><div class="structure-card"><span>STRUCTURE</span><strong>${esc(l.structure)}</strong></div>
 ${(l.steps&&l.steps.length)?`<div class="examples-title">Step by step</div><ol class="grammar-steps">${l.steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol>`:''}
 ${(l.breakdown&&l.breakdown.length)?`<div class="examples-title">In detail</div><div class="grammar-breakdown">${l.breakdown.map(b=>`<div class="breakdown-card"><b>${esc(b.term)}</b><p>${esc(b.definition)}</p><div class="breakdown-example"><span>EXAMPLE</span>${esc(b.example)}</div></div>`).join('')}</div>`:''}
 <div class="examples-title">Real examples</div><div class="grammar-examples">${(l.examples||[]).map((x,i)=>`<div class="grammar-example"><span>${i+1}</span><p>${esc(x)}</p></div>`).join('')}</div>
 ${(l.mistakes&&l.mistakes.length)?`<div class="mistakes-box"><div class="mistakes-title">⚠️ Common mistakes</div><ul>${l.mistakes.map(m=>`<li>${esc(m)}</li>`).join('')}</ul></div>`:''}
 ${l.tip?`<div class="memory-tip textbook-tip">💡 <b>Memory tip:</b> ${esc(l.tip)}</div>`:''}
 </div>
 <div class="grammar-section practice"><div class="section-kicker">FREE PRACTICE · 0 CREDITS</div><h4>Try it yourself</h4><div id="basicQuiz"></div><button class="complete-btn" id="completeLesson" ${done.has(l.id)?'disabled':''}>${done.has(l.id)?'✓ Lesson completed':'Complete lesson +25 XP'}</button></div>
 <div class="premium-title"><div><span class="section-kicker">AI LEARNING LAB</span><h4>Go beyond the textbook</h4></div><span class="credit-note">Only AI features use Credits</span></div>
 <div class="grammar-actions"><button class="premium primary" id="aiPractice"><b>AI Practice</b><small>5 fresh questions · 3 Credits</small></button><button class="premium" id="aiExplain"><b>AI Explanation</b><small>Personal explanation · 2 Credits</small></button><button class="premium" id="advanced"><b>Advanced Challenge</b><small>IELTS-style · 5 Credits</small></button><button class="premium" id="fullTest"><b>Full Grammar Test</b><small>64-day assessment · 8 Credits</small></button><button class="premium wide" id="plan"><b>Personalized 64-Day Plan</b><small>Uses your scores · 10 Credits</small></button></div>
 <div id="grammarAI" class="grammar-section ai-result" hidden></div>`;
 renderQuiz(l.quiz||[]);
 $('aiPractice').onclick=()=>action('ai_practice');$('aiExplain').onclick=()=>action('ai_explanation');$('advanced').onclick=()=>action('advanced_challenge');$('fullTest').onclick=()=>action('full_test');$('plan').onclick=()=>action('personalized_plan');
 $('completeLesson').onclick=()=>completeLesson(l);
}
function renderQuiz(qs){
 $('basicQuiz').innerHTML=qs.map((q,qi)=>`<div class="grammar-q"><div class="q-number">${qi+1}</div><div class="q-body"><b>${esc(q.q)}</b><div class="answer-grid">${q.options.map((o,oi)=>`<button data-q="${qi}" data-o="${oi}">${esc(o)}</button>`).join('')}</div><div class="grammar-feedback" id="gf${qi}"></div></div></div>`).join('');
 document.querySelectorAll('#basicQuiz button').forEach(b=>b.onclick=()=>{const q=qs[+b.dataset.q],ok=+b.dataset.o===q.answer;b.classList.add(ok?'correct':'wrong');document.querySelectorAll(`#basicQuiz button[data-q="${b.dataset.q}"]`).forEach(x=>x.disabled=true);$('gf'+b.dataset.q).textContent=ok?'✓ Correct — keep going!':'✗ Review the textbook structure and try the rule again.';updateQuizProgress(qs);});
}
function updateQuizProgress(qs){const answered=[...document.querySelectorAll('#basicQuiz button[disabled]')].length/4;const all=answered>=qs.length;const correct=[...document.querySelectorAll('#basicQuiz button.correct')].length;window.__grammarQuizScore=all?Math.round(correct/qs.length*100):null;if(all) $('completeLesson').classList.add('ready');}
async function completeLesson(l){const score=window.__grammarQuizScore??100;const r=await api('/edu/api/grammar/progress',{method:'POST',body:JSON.stringify({token,lessonId:l.id,completed:true,score})});const j=await r.json();if(!r.ok){alert(j.error||'Please sign in to save progress.');return}progress=j.progress||progress;renderShell();renderDays();renderLesson();renderExamSection();}
async function action(name){const box=$('grammarAI');box.hidden=false;box.innerHTML='<div class="ai-loading"><span></span><span></span><span></span><b>Building your learning activity…</b></div>';try{const r=await api('/edu/api/grammar/action',{method:'POST',body:JSON.stringify({action:name,lessonId:lessons[current]?.id,token})});const j=await r.json();if(!r.ok){box.innerHTML=`<div class="ai-error">${esc(j.error||'Unable to start activity.')}</div>`;return}box.innerHTML=formatAI(j,name);if(j.tsoCoins!==undefined){const b=$('grammarBalance');if(b)b.textContent=j.tsoCoins+' Credits';}box.scrollIntoView({behavior:'smooth',block:'nearest'});}catch(e){box.innerHTML='<div class="ai-error">Network error. Please try again.</div>'}}
function formatAI(j,name){
 if(name==='ai_practice'||name==='full_test')return `<div class="section-kicker">${name==='full_test'?'FULL ASSESSMENT':'AI PRACTICE'}</div><h4>${name==='full_test'?'64-Day Grammar Test':'Fresh practice for this lesson'}</h4>`+(j.questions||[]).slice(0,200).map((q,i)=>`<div class="grammar-q"><div class="q-number">${i+1}</div><div class="q-body"><b>${esc(q.question)}</b><div class="answer-grid">${(q.options||[]).map((o,oi)=>`<button onclick="this.parentElement.querySelectorAll('button').forEach(x=>x.disabled=true);this.classList.add(${oi===q.answer?'\'correct\'':'\'wrong\''})">${esc(o)}</button>`).join('')}</div><div class="grammar-feedback">${esc(q.explanation||'')}</div></div></div>`).join('');
 if(name==='ai_explanation')return `<div class="section-kicker">AI EXPLANATION</div><h4>Let's make this rule easier</h4><p>${esc(j.explanation||'')}</p>${j.illustration?`<div class="grammar-illustration"><pre>${esc(j.illustration)}</pre></div>`:''}<div class="ai-columns"><div><b>Examples</b><ul>${(j.examples||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div><div><b>Common mistakes</b><ul>${(j.mistakes||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div></div><div class="memory-tip">💡 <b>Memory tip:</b> ${esc(j.tip||'')}</div>`;
 if(name==='advanced_challenge')return `<div class="section-kicker">ADVANCED CHALLENGE</div><h4>Can you master this?</h4><p class="challenge-question">${esc(j.question||'')}</p><div class="answer-grid">${(j.options||[]).map((x,i)=>`<button>${esc(x)}</button>`).join('')}</div><p>${esc(j.explanation||'')}</p>`;
 return `<div class="section-kicker">YOUR PERSONAL PLAN</div><h4>${esc(j.message||'')}</h4><div class="personal-plan">${(j.plan||[]).map(x=>`<div><span>DAY ${x.day}</span><b>${esc(x.title)}</b><small>${esc(x.level)} · ${esc(x.reason)}</small></div>`).join('')}</div>`;
}
// ===========================================================================
// Final Mastery Exam + Certificate of Completion
//
// Flow: once every lesson is complete, the exam section unlocks. The exam
// itself is fetched fresh from the server on every attempt (server shuffles
// question order AND each question's answer options, so retakes are never
// the same paper — see _build_final_exam_questions() in app.py). Passing
// requires >= grammarCertPassThreshold (85% by default, read from the
// server response so the UI never hardcodes a stale number). Once passed,
// the student must explicitly confirm their name before the certificate is
// generated — the server refuses to print a certificate without that
// confirmation. A student can only ever hold one certificate; the server
// returns the same one on every later visit regardless of what name is
// sent.
// ===========================================================================
let examState=null; // {examToken, questions, answers:[], passThreshold, total}
let grammarCertPassThreshold=85;

function allLessonsComplete(){
 const done=progress.completedCount||progress.completed?.length||0;
 return lessons.length>0 && done>=lessons.length;
}
function renderExamSection(){
 const box=$('grammarExamSection');if(!box)return;
 if(!allLessonsComplete()){box.hidden=true;box.innerHTML='';return;}
 box.hidden=false;
 const fe=progress.finalExam||{};
 const certificate=progress.certificate||null;
 if(certificate){renderCertificateReady(box,certificate);return;}
 if(examState){renderExamInProgress(box);return;}
 if(fe.passed){renderExamPassedAwaitingCertificate(box,fe);return;}
 renderExamIntro(box,fe);
}
function renderExamIntro(box,fe){
 const attempts=fe.attempts||0;
 const bestScore=fe.bestScore;
 box.innerHTML=`<div class="section-kicker">FINAL MASTERY EXAM</div><h4>🏆 You've completed every lesson — take the Final Mastery Exam</h4>
 <p>Pass with a minimum score of <b>${grammarCertPassThreshold}%</b> to unlock your Certificate of Completion. Each attempt uses a freshly shuffled set of questions, so no two attempts are the same.</p>
 ${attempts?`<p class="exam-meta">Previous attempts: <b>${attempts}</b> · Best score so far: <b>${bestScore!=null?bestScore+'%':'—'}</b></p>`:''}
 <button class="complete-btn ready" id="startExamBtn">${attempts?'Retake the Final Mastery Exam':'Start the Final Mastery Exam'}</button>`;
 $('startExamBtn').onclick=startExam;
}
async function startExam(){
 const box=$('grammarExamSection');
 box.innerHTML='<div class="ai-loading"><span></span><span></span><span></span><b>Preparing your exam…</b></div>';
 try{
  const r=await api('/edu/api/grammar/final_exam?token='+encodeURIComponent(token));
  const j=await r.json();
  if(!r.ok){box.innerHTML=`<div class="ai-error">${esc(j.error||'Unable to start the exam.')}</div>`;return;}
  grammarCertPassThreshold=j.passThreshold||grammarCertPassThreshold;
  const t=$('grammarCertAnnounceThreshold');if(t)t.textContent=grammarCertPassThreshold+'%';
  examState={examToken:j.examToken,questions:j.questions,answers:new Array(j.questions.length).fill(null),passThreshold:j.passThreshold,total:j.totalQuestions};
  renderExamSection();
 }catch(e){box.innerHTML='<div class="ai-error">Network error. Please try again.</div>';}
}
function renderExamInProgress(box){
 const qs=examState.questions;
 const answered=examState.answers.filter(a=>a!=null).length;
 box.innerHTML=`<div class="section-kicker">FINAL MASTERY EXAM</div><h4>Answer every question, then submit</h4>
 <p class="exam-meta">Answered ${answered} / ${qs.length}</p>
 <div id="examQuestions">${qs.map((q,qi)=>`<div class="grammar-q"><div class="q-number">${qi+1}</div><div class="q-body"><b>${esc(q.question)}</b><div class="answer-grid">${q.options.map((o,oi)=>`<button data-q="${qi}" data-o="${oi}" class="${examState.answers[qi]===oi?'selected':''}">${esc(o)}</button>`).join('')}</div></div></div>`).join('')}</div>
 <button class="complete-btn ${answered>=qs.length?'ready':''}" id="submitExamBtn" ${answered>=qs.length?'':'disabled'}>Submit exam</button>`;
 document.querySelectorAll('#examQuestions button').forEach(b=>b.onclick=()=>{
  const qi=+b.dataset.q,oi=+b.dataset.o;
  examState.answers[qi]=oi;
  document.querySelectorAll(`#examQuestions button[data-q="${qi}"]`).forEach(x=>x.classList.remove('selected'));
  b.classList.add('selected');
  const answered=examState.answers.filter(a=>a!=null).length;
  const submitBtn=$('submitExamBtn');
  document.querySelector('.exam-meta').textContent=`Answered ${answered} / ${qs.length}`;
  if(answered>=qs.length){submitBtn.disabled=false;submitBtn.classList.add('ready');}
 });
 const submitBtn=$('submitExamBtn');if(submitBtn)submitBtn.onclick=submitExam;
}
async function submitExam(){
 const box=$('grammarExamSection');
 box.innerHTML='<div class="ai-loading"><span></span><span></span><span></span><b>Grading your exam…</b></div>';
 try{
  const r=await api('/edu/api/grammar/final_exam/submit',{method:'POST',body:JSON.stringify({token,examToken:examState.examToken,answers:examState.answers})});
  const j=await r.json();
  examState=null;
  if(!r.ok){box.innerHTML=`<div class="ai-error">${esc(j.error||'Unable to submit the exam.')}</div>`;return;}
  grammarCertPassThreshold=j.passThreshold||grammarCertPassThreshold;
  progress.finalExam={bestScore:j.bestScore,lastScore:j.score,attempts:j.attempts,passed:j.passed||progress.finalExam?.passed};
  renderResultThenSection(j);
 }catch(e){box.innerHTML='<div class="ai-error">Network error. Please try again.</div>';examState=null;}
}
function renderResultThenSection(j){
 const box=$('grammarExamSection');
 const passed=j.passed;
 box.innerHTML=`<div class="section-kicker">EXAM RESULT</div><h4>${passed?'🎉 You passed the Final Mastery Exam!':'Not quite — try again'}</h4>
 <p>You scored <b>${j.score}%</b> (${j.correct}/${j.total} correct). The minimum passing score is <b>${j.passThreshold}%</b>.</p>
 ${passed?'<p>Your Certificate of Completion is now ready to claim.</p>':'<p>Review the lessons for any topics you missed, then retake the exam — you will get a freshly shuffled set of questions.</p>'}
 <button class="complete-btn ready" id="examResultNextBtn">${passed?'Continue to your certificate':'Back'}</button>`;
 $('examResultNextBtn').onclick=()=>renderExamSection();
}
function renderExamPassedAwaitingCertificate(box,fe){
 box.innerHTML=`<div class="section-kicker">FINAL MASTERY EXAM · PASSED</div><h4>🎉 You passed with ${fe.bestScore}%</h4>
 <p>You're eligible for your Certificate of Completion. Before it's generated, please confirm your name exactly as it should be printed — this cannot be changed later, and each student may only claim one certificate.</p>
 <div class="cert-name-confirm"><label for="certNameInput">Full name for certificate</label><input type="text" id="certNameInput" maxlength="120" placeholder="Enter your full name" value="${esc((window.currentDisplayName||''))}"><button class="complete-btn ready" id="confirmNameBtn">Confirm name &amp; get certificate</button></div>
 <div id="certNameError" class="ai-error" hidden></div>`;
 $('confirmNameBtn').onclick=()=>requestCertificate(false);
}
async function requestCertificate(confirmedName){
 const nameInput=$('certNameInput');
 const displayName=(nameInput?nameInput.value:window.currentDisplayName||'').trim();
 const errBox=$('certNameError');
 if(!displayName){if(errBox){errBox.hidden=false;errBox.textContent='Please enter your name.';}return;}
 if(!confirmedName){
  // First click: show an explicit confirmation prompt with the exact
  // spelling before actually printing it, per the server's
  // confirmationRequired contract.
  const ok=window.confirm(`Confirm this is the exact name to print on your certificate:\n\n"${displayName}"\n\nThis cannot be changed after the certificate is issued.`);
  if(!ok)return;
 }
 const box=$('grammarExamSection');
 const prevHTML=box.innerHTML;
 box.innerHTML='<div class="ai-loading"><span></span><span></span><span></span><b>Generating your certificate…</b></div>';
 try{
  const r=await api('/edu/api/grammar/certificate/issue',{method:'POST',body:JSON.stringify({token,displayName,confirmedName:true})});
  const j=await r.json();
  if(!r.ok){
   if(j.confirmationRequired){box.innerHTML=prevHTML;if(errBox){errBox.hidden=false;errBox.textContent='Please confirm your name to continue.';}return;}
   box.innerHTML=`<div class="ai-error">${esc(j.error||'Unable to generate certificate.')}</div>`;return;
  }
  progress.certificate={certId:j.certId,verificationCode:j.verificationCode,verifyUrl:j.verifyUrl,studentName:j.studentName||displayName};
  renderExamSection();
 }catch(e){box.innerHTML='<div class="ai-error">Network error. Please try again.</div>';}
}
function renderCertificateReady(box,cert){
 box.innerHTML=`<div class="section-kicker">CERTIFICATE OF COMPLETION</div><h4>🏆 Congratulations, ${esc(cert.studentName||'')}!</h4>
 <p>Your Certificate of Completion has been issued and is ready to download (A4, print-ready PDF).</p>
 <p class="exam-meta">Certificate ID: <b>${esc(cert.certId||'')}</b></p>
 <a class="complete-btn ready cert-download-link" href="/edu/api/grammar/certificate/download?token=${encodeURIComponent(token)}">Download certificate (PDF)</a>
 ${cert.verifyUrl?`<p class="exam-meta">Verify at: <a href="${esc(cert.verifyUrl)}" target="_blank" rel="noopener">${esc(cert.verifyUrl)}</a></p>`:''}`;
}

// Deep link: opening /edu#grammar (or #grammarAcademy) scrolls straight to
// Grammar Academy and gives it the same brief focus highlight the nav
// buttons trigger, without touching the existing #grammar-less "/edu"
// behavior for anyone who doesn't use the hash.
function openFromHash(){
 const h=(location.hash||'').replace('#','');
 if(h==='grammar'||h==='grammarAcademy'){
  root.classList.add('coach-focus');
  if(!root.hasAttribute('tabindex')) root.setAttribute('tabindex','-1');
  requestAnimationFrame(()=>root.scrollIntoView({behavior:'smooth',block:'start'}));
  setTimeout(()=>{try{root.focus({preventScroll:true})}catch(e){}},520);
  setTimeout(()=>root.classList.remove('coach-focus'),2800);
 }
}
window.addEventListener('hashchange',openFromHash);
load().then(openFromHash);
})();
