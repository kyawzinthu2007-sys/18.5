"""Offline, non-AI essay generator ("humanize essay" mode).

Generates a full model essay for a given title/topic, essay type and CEFR
level entirely locally — no external AI call, no API key, no network
request. It works by:

  1. Extracting topic words from the title and expanding them into a
     related "topic family" (reusing the same family map the writing coach
     uses to check relevance), so the essay is actually about what the
     student typed rather than generic filler.
  2. Selecting a pool of essay-type-appropriate sentence templates (one set
     per task type: opinion, discussion, advantages/disadvantages, etc.)
     and filling them in with topic words and level-appropriate connectors.
  3. Randomly varying sentence openers, connectors, hedging phrases and
     synonym choices on every call, so two essays on the same title do not
     come out identical — this is the "humanize" pass that keeps the
     output from reading like a single fixed template.
  4. Trimming/padding paragraphs to land close to the requested word count.

This intentionally does not try to reproduce Gemini-quality prose. It
produces a structurally correct, on-topic, level-appropriate model essay
using the same linguistic resources (transitions, vocabulary bands) that
the rest of TSO Edu already uses for analysis, so the "Analyze" and
"Generate Essay" features stay internally consistent.
"""
import random
import re
import sqlite3
from pathlib import Path

from .writing_coach import TRANSITIONS, CONCLUSION_LINKS, normalize_topic, DB_PATH

# Same topic-family expansion used by topic_relevance() in writing_coach.py,
# duplicated here (rather than imported) so this module has its own small,
# self-contained vocabulary bank per family for essay content generation.
#
# Each family now also carries a 'vocabulary' list: topic-specific
# collocations and academic phrases (not full sentences) that
# _build_body_paragraph can drop into a sentence for lexical variety,
# instead of every essay in a domain reusing the same handful of nouns.
# All entries are original phrasing, not copied from any external source.
TOPIC_FAMILIES = {
    'education': {
        'keywords': {'education', 'school', 'student', 'learning', 'teacher', 'university', 'study', 'exam', 'curriculum', 'classroom', 'schooling', 'homeschooling', 'homework', 'college', 'lecture', 'tutor', 'tuition', 'grading', 'grade', 'degree', 'graduate', 'graduation'},
        'nouns': ['students', 'teachers', 'schools', 'universities', 'school leaders', 'exam boards', 'young learners'],
        'benefits': ['improve academic performance', 'give students more confidence', 'prepare young people for future careers', 'make learning more accessible', 'help teachers identify individual needs', 'strengthen critical thinking skills', 'encourage independent study habits', 'broaden access to specialised subjects', 'encourage collaborative problem-solving among students'],
        'drawbacks': ['increase pressure on students', 'widen the gap between well-resourced and under-resourced schools', 'reduce time for practical or social skills', 'place extra strain on teachers', 'be difficult for some families to access', 'narrow the curriculum toward tested subjects', 'add to the administrative workload of schools', 'disadvantage students without reliable support at home', 'leave some students without adequate one-on-one attention'],
        'examples': ['a school introducing smaller class sizes and seeing exam results improve within a year', 'a university offering flexible online modules so working students can still graduate', 'a teacher using regular feedback sessions to catch struggling students early', 'a district piloting peer-tutoring and reporting stronger engagement among lower-performing students', 'a college redesigning its assessment format after student feedback highlighted excessive exam pressure', 'a district introducing after-school tutoring that narrowed the gap between top and struggling students', 'a university piloting competency-based grading and reporting clearer skill progression among graduates'],
        'contexts': ['many countries have already reformed national curricula in response to this exact issue', 'education ministries continue to publish new guidance as classroom needs evolve', 'schools in different regions often adopt very different approaches depending on their resources', 'international comparisons of student outcomes continue to shape domestic education debates', 'teacher shortages in many areas complicate efforts to implement reforms consistently', 'funding disparities between wealthier and poorer districts continue to shape what schools can realistically offer', 'employers increasingly report a mismatch between what graduates learn and the skills workplaces actually need'],
        'vocabulary': ['academic achievement', 'curriculum design', 'formative assessment', 'educational equity', 'lifelong learning', 'student engagement', 'learning outcomes', 'pedagogical approach', 'differentiated instruction'],
    },
    'technology': {
        'keywords': {'technology', 'digital', 'internet', 'online', 'computer', 'ai', 'artificial', 'smartphone', 'app'},
        'nouns': ['technology companies', 'internet users', 'smartphones', 'social media platforms', 'digital tools', 'online services', 'software developers'],
        'benefits': ['save people significant amounts of time', 'connect people across long distances', 'make information far easier to access', 'automate repetitive and time-consuming tasks', 'open up new opportunities for small businesses', 'improve the speed and accuracy of everyday tasks', 'give people access to services once limited to major cities', 'allow smaller organisations to compete with larger ones', 'streamline access to essential public services'],
        'drawbacks': ['reduce face-to-face interaction', 'raise serious concerns about privacy', 'make people overly dependent on devices', 'spread misinformation quickly', 'widen the gap between those with and without access', 'create new avenues for fraud and exploitation', 'demand constant updates and technical maintenance', 'shorten attention spans through constant notifications', 'expose users to increasingly sophisticated online scams'],
        'examples': ['a small business reaching new customers entirely through a social media page', 'a family using a shared app to coordinate schedules across different time zones', 'a user disabling notifications for a week and noticing a clear improvement in focus', 'a start-up automating its customer support and freeing staff for higher-value work', 'a city rolling out free public wifi and seeing increased use of online services', 'a hospital adopting an appointment-reminder app and cutting missed appointments significantly', 'an elderly resident learning to use video calls and staying in closer contact with distant family'],
        'contexts': ['technology companies regularly update their policies as new risks and benefits emerge', 'regulators in several countries are still debating how closely this area should be monitored', 'the pace of change here makes it difficult to predict exactly how things will look in a decade', 'public trust in large technology firms has fluctuated considerably in recent years', 'adoption rates vary widely between generations and between urban and rural areas', 'smaller developers often struggle to compete with the resources of dominant technology firms', 'rural areas frequently lag behind cities in the speed and reliability of new technology rollout'],
        'vocabulary': ['digital transformation', 'data privacy', 'technological dependency', 'user experience', 'online connectivity', 'digital literacy', 'automation', 'cybersecurity risk', 'digital divide'],
    },
    'environment': {
        'keywords': {'environment', 'climate', 'pollution', 'green', 'carbon', 'energy', 'nature', 'sustainability', 'recycling', 'wildlife', 'deforestation', 'forest', 'ecosystem', 'emissions', 'biodiversity', 'plastic waste', 'plastic pollution', 'plastic bag', 'single-use plastic', 'microplastic', 'microplastics'},
        'nouns': ['governments', 'local communities', 'industries', 'future generations', 'environmental agencies', 'residents'],
        'benefits': ['reduce harmful emissions', 'protect natural habitats for future generations', 'encourage more sustainable consumption habits', 'lower long-term energy costs', 'improve public health in urban areas', 'preserve biodiversity in vulnerable ecosystems', 'reduce dependence on imported fossil fuels', 'strengthen resilience to extreme weather', 'support the recovery of damaged ecosystems'],
        'drawbacks': ['require significant upfront investment', 'be difficult to enforce consistently', 'place a heavier burden on lower-income households', 'take years to produce measurable results', 'meet resistance from established industries', 'shift costs onto consumers in the short term', 'be undermined by inconsistent international cooperation', 'compete with other urgent public spending priorities', 'be politically unpopular in regions reliant on affected industries'],
        'examples': ['a city that introduced a low-emission zone and measured a real drop in air pollution', 'a community solar project that lowered electricity bills for local households', 'a company switching to recyclable packaging after customer pressure grew', 'a coastal town investing in flood defences after repeated severe storms', 'a farming cooperative adopting drip irrigation and reducing water use significantly', 'a national park expanding a rewilding project and seeing a measurable return of native species', 'a household switching to a heat pump and cutting its winter energy bill significantly'],
        'contexts': ['international agreements continue to shape how governments approach this issue', 'the scientific evidence on this subject has become considerably stronger in recent years', 'different countries face very different practical constraints when tackling this problem', 'public awareness of environmental issues has grown noticeably over the past decade', 'the balance between economic growth and environmental protection remains politically contested', 'insurance costs in flood- and fire-prone regions have risen sharply as climate risk has become clearer', 'younger generations report significantly higher levels of concern about long-term environmental damage than older ones'],
        'vocabulary': ['carbon footprint', 'renewable resources', 'environmental degradation', 'sustainable development', 'climate resilience', 'conservation efforts', 'greenhouse gas emissions', 'ecological balance', 'biodiversity loss'],
    },
    'health': {
        'keywords': {'health', 'exercise', 'diet', 'medical', 'doctor', 'disease', 'fitness', 'hospital', 'wellbeing', 'nutrition'},
        'nouns': ['patients', 'healthcare workers', 'hospitals', 'public health systems', 'individuals', 'families'],
        'benefits': ['improve long-term physical wellbeing', 'reduce pressure on hospitals and clinics', 'help people manage stress more effectively', 'catch health problems earlier', 'encourage healthier daily habits', 'extend average life expectancy', 'lower the long-term cost of treating chronic illness', 'improve mental as well as physical wellbeing', 'support earlier diagnosis through routine screening'],
        'drawbacks': ['be expensive for many families to maintain', 'require lifestyle changes that are hard to sustain', 'not be equally accessible in every region', 'take time before any real benefit is felt', 'depend heavily on individual motivation', 'place additional strain on already stretched healthcare staff', 'be undermined by inconsistent public health messaging', 'vary considerably in quality between providers', 'widen health gaps between well-resourced and under-resourced regions'],
        'examples': ['a workplace introducing short exercise breaks and reporting fewer sick days', 'a patient catching a condition early because of a routine screening programme', 'a community health clinic offering free check-ups to under-served neighbourhoods', 'a hospital introducing telemedicine consultations and reducing waiting times', 'a school adding a daily activity period and noting improved student concentration', 'a rural clinic introducing mobile screening vans and reaching patients who previously went untested', 'an employer subsidising gym memberships and reporting improved staff morale alongside fewer sick days'],
        'contexts': ['public health systems in many countries are under growing pressure to adapt to this issue', 'medical guidance on this subject is regularly reviewed as new research becomes available', 'access to this kind of support still varies considerably between wealthier and poorer areas', 'an ageing population in many countries is placing additional demands on healthcare services', 'preventive care is increasingly emphasised as a way to reduce long-term costs', 'waiting times for specialist care vary enormously between well-funded and under-resourced health systems', 'an ageing population is placing sustained long-term pressure on health budgets in many countries'],
        'vocabulary': ['preventive care', 'public health outcomes', 'healthcare accessibility', 'chronic illness', 'mental wellbeing', 'healthy lifestyle', 'medical intervention', 'quality of life', 'health disparity'],
    },
    'transport': {
        'keywords': {'transport', 'traffic', 'bus', 'car', 'road', 'travel', 'commute', 'cycling', 'train'},
        'nouns': ['commuters', 'city planners', 'public transport networks', 'drivers', 'local authorities'],
        'benefits': ['reduce traffic congestion in busy cities', 'cut travel time for daily commuters', 'lower overall transport emissions', 'make city centres safer for pedestrians', 'give people more affordable travel options', 'improve air quality in densely populated areas', 'connect outlying communities to city centres', 'reduce the number of road traffic accidents', 'make daily commuting more predictable and less stressful'],
        'drawbacks': ['require substantial public investment', 'be inconvenient for people living outside major cities', 'take considerable time to plan and build', 'face opposition from existing car users', 'need ongoing maintenance to remain reliable', 'disrupt existing traffic patterns during construction', 'be difficult to coordinate across different local authorities', 'struggle to serve areas with low population density', 'be poorly suited to sparsely populated rural areas'],
        'examples': ['a city that expanded its cycle lane network and saw fewer cars in the centre', 'a commuter town that added an express bus route and cut average journey times', 'a rail operator introducing off-peak discounts to spread out passenger demand', 'a city banning cars from its historic centre and reporting increased foot traffic to local shops', 'a region investing in electric bus fleets and lowering local air pollution', 'a city introducing a bike-share scheme that noticeably reduced short car journeys in the centre', 'a rural region losing its only bus route and leaving residents with far fewer transport options'],
        'contexts': ['city planners in different regions have taken noticeably different approaches to this issue', 'public investment in this area tends to depend heavily on local budgets and priorities', 'the balance between cost and convenience remains a central part of this debate', 'rising fuel prices have renewed public interest in alternative transport options', 'urban populations continue to grow, adding further pressure on existing infrastructure', 'fuel and vehicle costs continue to shape household decisions about whether to rely on a car', 'investment in transport infrastructure often lags behind the pace of urban population growth'],
        'vocabulary': ['traffic congestion', 'public transport network', 'urban mobility', 'carbon emissions', 'infrastructure investment', 'commuting patterns', 'road safety', 'sustainable transport', 'first/last-mile connectivity'],
    },
    'work': {
        'keywords': {'work', 'job', 'employee', 'employment', 'career', 'office', 'salary', 'workplace', 'remote', 'employer', 'home'},
        'nouns': ['employees', 'employers', 'companies', 'job seekers', 'the workforce', 'managers'],
        'benefits': ['give employees greater flexibility', 'improve overall productivity', 'reduce unnecessary commuting time', 'help companies attract wider talent', 'improve work-life balance', 'lower overhead costs for businesses', 'allow companies to hire across a wider geographic area', 'increase employee satisfaction and retention', 'help workers develop transferable, future-proof skills'],
        'drawbacks': ['make teamwork more difficult to coordinate', 'blur the boundary between work and personal life', 'disadvantage employees without a suitable home setup', 'weaken informal workplace communication', 'be harder for managers to monitor fairly', 'reduce opportunities for mentorship and informal learning', 'create unequal experiences between office-based and remote staff', 'complicate efforts to build a shared company culture', 'increase job insecurity in industries facing rapid automation'],
        'examples': ['a company that adopted a hybrid schedule and reported higher staff retention', 'an employee negotiating flexible hours to balance work with family responsibilities', 'a manager introducing regular check-ins to keep a remote team connected', 'a firm redesigning its office around collaborative spaces after switching to a hybrid model', 'a small business hiring its first fully remote employee and expanding its talent pool', 'a small firm introducing a four-day week and reporting no measurable drop in output', 'a graduate struggling to find stable full-time work despite holding a relevant qualification'],
        'contexts': ['employers across different industries have responded to this issue in very different ways', 'workplace policies on this subject continue to evolve as expectations shift', 'the right balance often depends on the specific nature of the job and the team involved', 'younger employees in particular have shown a strong preference for greater flexibility', 'competition for skilled staff has pushed many companies to reconsider traditional arrangements', 'automation continues to reshape which skills employers value most in a competitive job market', 'job security has become a growing concern as more work shifts toward short-term contracts'],
        'vocabulary': ['work-life balance', 'workplace flexibility', 'employee productivity', 'career progression', 'remote collaboration', 'job satisfaction', 'organisational culture', 'talent retention', 'skills mismatch'],
    },
    'government': {
        'keywords': {'government', 'policy', 'public', 'state', 'law', 'tax', 'citizen', 'politics', 'regulation'},
        'nouns': ['governments', 'policymakers', 'taxpayers', 'local authorities', 'citizens', 'public institutions'],
        'benefits': ['create clearer standards for everyone to follow', 'protect vulnerable groups more effectively', 'improve accountability in public spending', 'provide more consistent public services', 'build greater public trust in institutions', 'reduce loopholes that allow unfair advantage', 'improve coordination between different public agencies', 'give citizens clearer channels to raise concerns', 'improve responsiveness to citizens\' everyday concerns'],
        'drawbacks': ['be slow and costly to implement', 'face resistance from affected groups', 'be applied inconsistently across regions', 'require careful long-term monitoring', 'place additional strain on public budgets', 'create unintended loopholes if poorly designed', 'be difficult to adapt quickly to changing circumstances', 'generate disagreement over how costs should be shared', 'be vulnerable to short-term political pressure over long-term planning'],
        'examples': ['a local authority piloting a new policy in one district before rolling it out nationally', 'a government department publishing clearer guidelines after public consultation', 'a city council reversing an unpopular rule after reviewing community feedback', 'a national government introducing a phased rollout to limit disruption', 'a regulator working with industry groups to draft more workable rules', 'a city council piloting participatory budgeting and reporting greater public trust in local spending decisions', 'a national audit exposing wasteful spending that later triggered a reform of procurement rules'],
        'contexts': ['governments in different countries have taken markedly different positions on this issue', 'public opinion on this subject often shifts as new information becomes available', 'the practical impact of any policy here tends to depend heavily on how well it is enforced', 'budget constraints often shape which policy options are considered realistic', 'public consultations have become a more common part of the policymaking process', 'trust in public institutions has declined in many countries over the past decade', 'the transparency of government decision-making is increasingly scrutinised by independent watchdogs and journalists'],
        'vocabulary': ['public policy', 'regulatory framework', 'government accountability', 'public spending', 'civic trust', 'policy implementation', 'legislative reform', 'public consultation', 'institutional trust'],
    },
    'crime': {
        'keywords': {'crime', 'criminal', 'police', 'prison', 'punishment', 'illegal', 'safety', 'offence', 'offender', 'theft', 'burglary', 'arrest', 'law', 'justice', 'sentence', 'victim', 'reoffending'},
        'nouns': ['the police', 'local communities', 'the justice system', 'offenders', 'victims'],
        'benefits': ['deter potential offenders', 'make communities feel safer', 'reduce repeat offending over time', 'improve public confidence in law enforcement', 'address the root causes of criminal behaviour', 'strengthen cooperation between police and local communities', 'provide victims with more effective support', 'free up police resources for serious cases', 'reduce the burden on an overstretched court system'],
        'drawbacks': ['be expensive to fund adequately', 'take years to show measurable results', 'risk unfairly affecting certain groups', 'not address the underlying social causes', 'require close, ongoing oversight', 'strain an already overburdened justice system', 'be difficult to evaluate objectively', 'meet scepticism from communities with low trust in institutions', 'disproportionately affect communities with limited access to legal support'],
        'examples': ['a neighbourhood watch scheme that helped reduce local burglaries', 'a rehabilitation programme that lowered reoffending rates among participants', 'a police force introducing community outreach and seeing improved public trust', 'a city investing in street lighting and reporting a drop in night-time crime', 'a court piloting a diversion scheme for young first-time offenders', 'a city expanding CCTV coverage in a high-crime area and recording a measurable drop in incidents', 'a youth diversion programme keeping first-time offenders out of the formal justice system altogether'],
        'contexts': ['approaches to this issue vary considerably between different justice systems', 'the evidence on what actually works here remains a subject of ongoing debate', 'long-term outcomes are often harder to measure than short-term statistics suggest', 'public perceptions of safety do not always match official crime statistics', 'funding pressures often force difficult choices between prevention and enforcement', 'public perceptions of crime do not always align with official statistics on actual crime rates', 'prison overcrowding in many countries has renewed debate over alternatives to custodial sentencing'],
        'vocabulary': ['public safety', 'law enforcement', 'rehabilitation programme', 'criminal justice system', 'community policing', 'reoffending rate', 'deterrent effect', 'restorative justice', 'sentencing disparity'],
    },
    'media': {
        'keywords': {'media', 'news', 'television', 'advertising', 'journalism', 'newspaper', 'broadcasting'},
        'nouns': ['news organisations', 'the public', 'advertisers', 'journalists', 'media companies'],
        'benefits': ['keep the public better informed', 'give a wider range of voices a platform', 'hold powerful institutions accountable', 'make information more immediately accessible', 'encourage open public debate', 'expose issues that might otherwise go unreported', 'allow independent voices to reach large audiences', 'improve transparency around public institutions', 'give underrepresented communities a stronger public voice'],
        'drawbacks': ['spread unverified information quickly', 'be driven more by attention than accuracy', 'reduce trust in mainstream reporting', 'expose audiences to biased content', 'blur the line between fact and opinion', 'reward sensational content over careful reporting', 'make fact-checking increasingly difficult to keep up with', 'concentrate influence in the hands of a few large platforms', 'concentrate influence in the hands of a small number of owners'],
        'examples': ['a local newsroom launching a fact-checking column to rebuild reader trust', 'an independent journalist using social media to reach an audience a newspaper could not', 'a broadcaster facing criticism after a story turned out to rely on unverified sources', 'a news outlet introducing clearer labelling for opinion versus reported content', 'a platform adjusting its algorithm after concerns about the spread of misinformation', 'a newsroom losing significant advertising revenue as readers migrated to free online sources', 'an independent fact-checking organisation gaining wider public trust after several high-profile corrections'],
        'contexts': ['news organisations face growing pressure to adapt as audience habits keep changing', 'trust in different types of media varies considerably from one country to another', 'the speed of modern reporting makes accuracy an ongoing and difficult challenge', 'advertising revenue models continue to reshape how news organisations operate', 'media literacy is increasingly seen as an essential modern skill', 'the collapse of local newspaper advertising has left many communities with far less local reporting', 'algorithm-driven content feeds increasingly determine what news most people actually encounter each day'],
        'vocabulary': ['media literacy', 'press freedom', 'public accountability', 'misinformation', 'editorial independence', 'audience trust', 'news coverage', 'digital journalism', 'media concentration'],
    },
    'family': {
        'keywords': {'family', 'families', 'parent', 'parents', 'parenting', 'child', 'children', 'kid', 'kids',
                     'sibling', 'siblings', 'marriage', 'married', 'spouse', 'household', 'upbringing',
                     'grandparent', 'grandparents', 'relative', 'relatives', 'divorce', 'stepfamily',
                     'guardian', 'caregiver', 'elderly', 'discipline', 'chores', 'nuclear', 'extended',
                     'single-parent'},
        'nouns': ['parents', 'children', 'families', 'households', 'young people', 'grandparents', 'siblings', 'caregivers'],
        'benefits': ['strengthen family relationships', 'give children a greater sense of stability', 'allow parents more time with their children', 'support healthier emotional development', 'ease pressure on busy households', 'improve communication between family members', 'help children build stronger social skills', 'reduce long-term stress within the household', 'give grandparents a more active role in raising children', 'help siblings build closer, more supportive relationships', 'help children develop secure, lasting attachments'],
        'drawbacks': ['add financial pressure on families', 'be difficult to balance with work commitments', 'vary widely depending on individual circumstances', 'require consistent effort to maintain', 'not suit every family situation equally', 'create tension when expectations differ between generations', 'be harder to sustain in single-parent households', 'depend heavily on the availability of outside support', 'be complicated by disagreements over discipline between parents and grandparents', 'place uneven caregiving responsibilities on one family member', 'be strained further during major life transitions such as relocation'],
        'examples': ['a family setting aside a fixed weekly time together despite busy schedules', 'a parent adjusting working hours to spend more time with young children', 'a household establishing clear routines that reduced day-to-day stress', 'a family using shared chores to teach children responsibility from an early age', 'a community centre offering parenting workshops for first-time parents', 'a grandparent taking on regular childcare while both parents work full time', 'a single parent relying on a nearby relative for after-school support'],
        'contexts': ['family circumstances differ enormously, so no single approach suits every household', 'attitudes toward this issue often depend on cultural background and personal experience', 'support available to families varies considerably depending on where they live', 'changing work patterns have reshaped how many families organise their time', 'extended family support plays a different role in different cultural contexts', 'the balance of caregiving duties within a household continues to shift across generations', 'rising living costs have made multigenerational households more common in many regions'],
        'vocabulary': ['family dynamics', 'child development', 'household responsibilities', 'work-family balance', 'parental involvement', 'emotional support', 'intergenerational relationships', 'family stability', 'single-parent household', 'extended family network', 'child-rearing practices', 'family cohesion', 'secure attachment'],
    },
    'tourism': {
        'keywords': {'tourism', 'travel', 'holiday', 'visitor', 'hotel', 'destination', 'tourist', 'vacation'},
        'nouns': ['tourists', 'local businesses', 'residents', 'tour operators', 'destination communities'],
        'benefits': ['create jobs in local communities', 'support small businesses and local trade', 'encourage cultural exchange between visitors and residents', 'fund the upkeep of heritage sites', 'bring valuable foreign income into the local economy', 'raise international awareness of local culture', 'encourage investment in local infrastructure', 'fund the preservation of cultural and historic sites'],
        'drawbacks': ['lead to overcrowding at popular sites', 'put pressure on local infrastructure and housing', 'damage fragile natural or historic environments', 'push up living costs for local residents', 'depend heavily on unpredictable seasonal demand', 'create low-paid and insecure seasonal employment', 'strain water and energy resources in popular destinations', 'push up housing costs for long-term local residents'],
        'examples': ['a coastal town introducing a visitor cap to protect a fragile ecosystem', 'a historic city investing tourist revenue directly into heritage conservation', 'a rural region developing eco-tourism to diversify its local economy', 'a national park limiting daily visitor numbers after erosion concerns grew', 'a city taxing short-term rentals to fund affordable local housing', 'a historic city introducing visitor caps after residents complained about overcrowding', 'a small coastal town building its entire economy around a single annual tourist season'],
        'contexts': ['destinations around the world are increasingly rethinking how to manage visitor numbers', 'the balance between economic benefit and environmental protection varies by region', 'local attitudes toward tourism often shift as visitor numbers grow', 'recovery patterns after major disruptions differ considerably between destinations', 'sustainable tourism has become a central theme in destination management', 'overtourism has become a growing concern in several of the world\'s most popular destinations', 'the seasonal nature of tourism leaves many local economies vulnerable during the off-season'],
        'vocabulary': ['sustainable tourism', 'cultural exchange', 'local economy', 'heritage conservation', 'visitor management', 'seasonal employment', 'overtourism', 'destination infrastructure', 'carrying capacity'],
    },
    'economy': {
        'keywords': {'economy', 'inflation', 'prices', 'income', 'poverty', 'business', 'finance', 'cost', 'wages'},
        'nouns': ['households', 'businesses', 'workers', 'consumers', 'policymakers'],
        'benefits': ['increase household purchasing power', 'create new employment opportunities', 'support small business growth', 'improve overall living standards', 'encourage greater investment in local industry', 'strengthen long-term economic stability', 'reduce dependence on a narrow range of industries', 'encourage entrepreneurship and new business formation'],
        'drawbacks': ['increase the cost of living for many households', 'widen the gap between higher and lower earners', 'create uncertainty for small businesses', 'be vulnerable to external economic shocks', 'take time to translate into real wage growth', 'strain public finances if not carefully managed', 'disproportionately affect households on fixed incomes', 'leave workers exposed during periods of economic downturn'],
        'examples': ['a small business adjusting its pricing strategy to cope with rising costs', 'a region diversifying its economy after relying too heavily on one industry', 'a household cutting discretionary spending during a period of high inflation', 'a government introducing targeted support for low-income households during a downturn', 'a local economy recovering faster than expected after a period of investment', 'a small business closing after a sharp rise in commercial rent it could no longer absorb', 'a central bank raising interest rates and slowing consumer spending noticeably within months'],
        'contexts': ['economic conditions differ considerably between regions and income groups', 'global events increasingly influence local economic outcomes', 'policymakers face difficult trade-offs between short-term relief and long-term stability', 'consumer confidence tends to shift quickly in response to economic news', 'wage growth has not always kept pace with rising living costs', 'wage growth in many countries has failed to keep pace with the rising cost of living', 'small businesses are often disproportionately affected by economic shocks compared with larger companies'],
        'vocabulary': ['cost of living', 'economic stability', 'purchasing power', 'income inequality', 'consumer spending', 'economic growth', 'financial security', 'market volatility', 'economic resilience'],
    },
    'science': {
        'keywords': {'science', 'research', 'experiment', 'discovery', 'evidence', 'laboratory', 'innovation', 'scientist'},
        'nouns': ['researchers', 'scientists', 'research institutions', 'the public', 'funding bodies'],
        'benefits': ['expand human understanding of important problems', 'lead to practical improvements in daily life', 'inform better public policy decisions', 'solve long-standing technical challenges', 'create new industries and areas of employment', 'improve the accuracy of future predictions', 'strengthen a country\'s long-term competitiveness', 'accelerate progress through international collaboration'],
        'drawbacks': ['require significant and sustained funding', 'raise difficult ethical questions', 'produce uncertain or inconclusive results', 'take years or decades to show practical benefit', 'be difficult to communicate clearly to the public', 'risk being misused if inadequately regulated', 'create unequal access to the resulting benefits', 'face growing public scepticism when findings are politicised'],
        'examples': ['a research team securing long-term funding after years of incremental progress', 'a laboratory collaborating internationally to accelerate a promising line of research', 'a public health agency translating new research into updated guidance quickly', 'a university spinning out a start-up based on a decade of prior research', 'a research programme adjusting its methods after early results proved inconclusive', 'a research team securing new funding after publishing an unexpected but well-verified result', 'a university lab losing several years of work when a promising funding stream was cut'],
        'contexts': ['scientific consensus often takes considerable time to form around new evidence', 'public trust in scientific institutions varies across different countries and topics', 'funding priorities heavily influence which research questions receive attention', 'international collaboration has become increasingly important in major research fields', 'the gap between discovery and practical application can be substantial', 'public trust in scientific findings can be shaken by high-profile cases of poor research practice', 'funding for long-term research often struggles to compete against projects promising faster results'],
        'vocabulary': ['scientific evidence', 'research funding', 'peer review', 'technological innovation', 'ethical considerations', 'empirical findings', 'scientific consensus', 'practical application', 'reproducibility'],
    },
    'culture': {
        'keywords': {'culture', 'tradition', 'heritage', 'art', 'museum', 'identity', 'community', 'festival'},
        'nouns': ['communities', 'artists', 'museums', 'heritage organisations', 'younger generations'],
        'benefits': ['strengthen a sense of shared identity', 'preserve knowledge and traditions for future generations', 'encourage artistic and creative expression', 'attract cultural tourism to local areas', 'support intergenerational understanding', 'foster greater appreciation of diversity', 'provide communities with a sense of continuity', 'give younger generations a stronger sense of shared identity'],
        'drawbacks': ['struggle to secure adequate long-term funding', 'be at risk of excessive commercialisation', 'exclude groups without easy access to cultural institutions', 'change or dilute traditions over time', 'require ongoing investment in conservation', 'depend heavily on the interest of younger generations', 'face competition from more accessible forms of entertainment', 'be diluted when commercial interests reshape traditional practices'],
        'examples': ['a museum digitising its collection to widen public access', 'a community reviving a traditional festival that had almost disappeared', 'a local government funding a heritage centre after residents raised concerns about its future', 'an arts organisation offering free entry to widen participation', 'a city using cultural festivals to attract visitors during quieter tourist seasons', 'a small town reviving a near-forgotten local festival that drew visitors back to the area', 'a historic craft nearly disappearing until a community workshop began training a new generation'],
        'contexts': ['attitudes toward preserving tradition often differ between generations', 'funding for cultural institutions is frequently among the first areas cut during austerity', 'globalisation has both threatened and helped spread local cultural practices', 'digital technology has changed how cultural heritage is shared and experienced', 'communities differ considerably in how they balance tradition with modern change', 'globalisation has made it easier for local traditions to reach wider audiences, for better or worse', 'younger generations in many places show less familiarity with traditional customs than their grandparents did'],
        'vocabulary': ['cultural heritage', 'artistic expression', 'community identity', 'cultural preservation', 'intergenerational knowledge', 'creative industries', 'cultural diversity', 'heritage conservation', 'cultural expression'],
    },
    'sports': {
        'keywords': {'sport', 'sports', 'football', 'athletics', 'competition', 'team', 'athlete', 'exercise'},
        'nouns': ['athletes', 'young people', 'local clubs', 'schools', 'spectators'],
        'benefits': ['improve physical health and fitness', 'develop teamwork and discipline', 'build a stronger sense of community', 'provide constructive activities for young people', 'create pathways to professional opportunities', 'improve mental wellbeing through regular activity', 'teach valuable skills such as resilience and cooperation', 'provide a valuable outlet for stress and everyday pressure'],
        'drawbacks': ['carry a real risk of injury', 'require costly facilities and equipment', 'create excessive pressure to win at a young age', 'not be equally accessible to every community', 'demand a significant time commitment', 'expose participants to intense competitive stress', 'favour naturally talented individuals over inclusive participation', 'place excessive pressure on young athletes to specialise too early'],
        'examples': ['a school introducing a lunchtime sports programme and reporting improved concentration in class', 'a local club securing funding to renovate ageing facilities', 'a community centre offering free coaching sessions for underprivileged children', 'a national federation launching an initiative to encourage participation among girls', 'a youth league adjusting its rules to reduce the risk of injury', 'a local sports club losing young members after nearby facilities were closed due to funding cuts', 'a school introducing a mixed-ability sports programme and reporting wider student participation'],
        'contexts': ['access to sporting facilities differs considerably between wealthier and poorer areas', 'attitudes toward competitive sport for children vary between cultures', 'funding for grassroots sport often competes with other local priorities', 'professional sport increasingly shapes public interest in physical activity generally', 'the balance between competition and participation remains an ongoing debate', 'access to organised sport remains uneven between wealthier and lower-income neighbourhoods', 'concerns about injury and burnout have grown alongside the increasing intensity of youth competition'],
        'vocabulary': ['physical fitness', 'team cohesion', 'competitive pressure', 'grassroots participation', 'sporting facilities', 'athletic performance', 'youth development', 'community engagement', 'athlete wellbeing'],
    },
    'housing': {
        'keywords': {'housing', 'home', 'rent', 'apartment', 'city', 'urban', 'property', 'homelessness'},
        'nouns': ['residents', 'renters', 'homeowners', 'local authorities', 'property developers'],
        'benefits': ['provide more stable and secure living conditions', 'reduce the financial burden on lower-income households', 'support workers moving to areas with more job opportunities', 'improve the overall quality of neighbourhoods', 'reduce rates of homelessness', 'increase the supply of affordable accommodation', 'encourage more balanced urban development', 'support more stable, settled local communities'],
        'drawbacks': ['face strong resistance from existing residents', 'require substantial long-term public investment', 'take years to noticeably affect housing supply', 'be difficult to implement fairly across different areas', 'place additional pressure on local infrastructure', 'be undermined by rising land and construction costs', 'struggle to keep pace with population growth', 'be slowed by lengthy planning and permitting processes'],
        'examples': ['a city introducing rent controls and monitoring their effect on housing supply', 'a local authority converting unused buildings into affordable housing units', 'a developer partnering with the city to include affordable units in a new project', 'a region investing in public transport to make outlying areas more attractive for housing', 'a housing charity providing temporary accommodation while long-term solutions are developed', 'a city relaxing zoning rules and seeing a modest but real increase in new housing supply', 'a young family being priced out of the neighbourhood they grew up in'],
        'contexts': ['housing pressures differ considerably between major cities and smaller towns', 'construction costs and planning regulations vary widely between regions', 'public opinion on new housing developments is often shaped by local concerns', 'demand for housing in major cities continues to outpace new supply in many places', 'housing affordability has become an increasingly prominent political issue', 'housing affordability has become a defining economic concern in many major cities', 'construction of new affordable housing frequently fails to keep pace with population growth'],
        'vocabulary': ['housing affordability', 'urban development', 'rental market', 'housing supply', 'homelessness prevention', 'property investment', 'neighbourhood regeneration', 'living conditions', 'housing security'],
    },
    'food': {
        'keywords': {'food', 'farming', 'agriculture', 'diet', 'waste', 'farmers', 'crops', 'production', 'nutrition'},
        'nouns': ['farmers', 'consumers', 'food producers', 'rural communities', 'policymakers'],
        'benefits': ['improve food security for local communities', 'create stable employment in rural areas', 'improve overall nutrition and public health', 'reduce reliance on imported produce', 'support more sustainable farming practices', 'reduce the environmental impact of food production', 'give consumers greater confidence in food quality', 'strengthen local food security during supply disruptions'],
        'drawbacks': ['require significant investment in infrastructure', 'be vulnerable to unpredictable weather patterns', 'increase costs for consumers in the short term', 'be difficult to scale beyond small pilot projects', 'place additional pressure on limited land and water resources', 'depend heavily on unpredictable global commodity prices', 'create tension between efficiency and environmental sustainability', 'be undermined by volatile global commodity prices'],
        'examples': ['a farming cooperative adopting more efficient irrigation and reducing water waste', 'a school introducing healthier meal options and reporting improved student concentration', 'a region investing in local food networks to reduce reliance on imports', 'a supermarket chain committing to reduce food waste across its supply chain', 'a government subsidy programme helping smallholder farmers adopt sustainable techniques', 'a supermarket chain redesigning its ordering system and cutting unsold food waste substantially', 'a smallholder farmer struggling to compete with the lower prices offered by large agribusiness'],
        'contexts': ['food security concerns have grown as populations and demand continue to rise', 'attitudes toward sustainable farming vary considerably between regions and generations', 'global supply chains mean local food systems are affected by distant events', 'rising costs have made food affordability an increasingly pressing public concern', 'consumer preferences are shifting toward more sustainably produced food', 'climate change is increasingly disrupting crop yields in regions that were previously reliable producers', 'supply-chain disruptions have repeatedly exposed how fragile some food systems really are'],
        'vocabulary': ['food security', 'sustainable agriculture', 'nutritional value', 'supply chain', 'rural livelihoods', 'food waste reduction', 'crop yield', 'local production', 'supply chain resilience'],
    },
    'globalisation': {
        'keywords': {'globalisation', 'globalization', 'trade', 'international', 'global', 'multinational', 'export', 'import'},
        'nouns': ['businesses', 'workers', 'consumers', 'governments', 'developing economies'],
        'benefits': ['expand access to international markets', 'lower prices through increased competition', 'spread knowledge and technology more widely', 'create new opportunities for developing economies', 'increase cultural exchange between countries', 'improve efficiency through specialisation', 'encourage international cooperation on shared challenges', 'accelerate the spread of new technology and ideas'],
        'drawbacks': ['expose local industries to intense foreign competition', 'contribute to job losses in certain sectors', 'increase dependence on complex international supply chains', 'widen inequality between and within countries', 'make economies more vulnerable to distant disruptions', 'place pressure on local cultural identity', 'complicate efforts to enforce consistent labour standards', 'increase economic vulnerability to distant, unrelated shocks'],
        'examples': ['a local manufacturer adapting its products to compete with cheaper imports', 'a developing economy attracting foreign investment after improving its infrastructure', 'a company diversifying its suppliers after a disruption exposed its reliance on one region', 'a country negotiating new trade agreements to open up additional export markets', 'a small business successfully reaching international customers through online platforms', 'a manufacturer relocating production overseas and eliminating hundreds of local jobs in the process', 'a small artisan business finding new customers abroad through an international online marketplace'],
        'contexts': ['the benefits and costs of global integration are distributed unevenly between countries', 'recent global disruptions have prompted many businesses to reconsider long supply chains', 'attitudes toward international trade vary considerably depending on economic circumstances', 'developing and developed economies often experience globalisation very differently', 'international cooperation remains essential but increasingly difficult to coordinate', 'global supply chains have proven more fragile than many assumed before recent disruptions', 'the benefits of global trade are not always distributed evenly within a single country'],
        'vocabulary': ['global supply chain', 'international trade', 'economic interdependence', 'foreign investment', 'market competition', 'cultural exchange', 'trade liberalisation', 'economic integration', 'cross-border trade'],
    },
    'social_media': {
        'keywords': {'social', 'media', 'facebook', 'tiktok', 'instagram', 'platform', 'influencer', 'online'},
        'nouns': ['users', 'young people', 'platforms', 'content creators', 'advertisers'],
        'benefits': ['help people stay connected across distances', 'give small creators and businesses a wider audience', 'allow information to spread quickly during emergencies', 'provide a platform for underrepresented voices', 'support communities built around shared interests', 'make it easier to organise events and causes', 'offer new opportunities for creative expression', 'help small creators reach audiences once out of their reach'],
        'drawbacks': ['contribute to unhealthy social comparison', 'spread misinformation faster than it can be corrected', 'expose users, especially young people, to online harassment', 'encourage compulsive and excessive use', 'compromise personal privacy through data collection', 'create echo chambers that reinforce existing views', 'reward sensational content over accuracy', 'amplify polarising or extreme content through engagement-driven algorithms'],
        'examples': ['a small creator building a sustainable business entirely through an online following', 'a platform introducing screen-time reminders after concerns about excessive use', 'a local charity using social media to organise a rapid community response', 'a school running workshops to help students evaluate online information critically', 'a user taking a deliberate break and reporting improved sleep and focus', 'a teenager reporting improved mood after deliberately limiting daily social media use', 'a small creator building a sustainable income entirely through an online following'],
        'contexts': ['platforms differ considerably in how they moderate content and protect users', 'regulatory scrutiny of major platforms has increased significantly in recent years', 'young people in particular have shown mixed attitudes toward heavy platform use', 'the commercial incentives behind these platforms shape what content gets promoted', 'public debate continues over where responsibility for online harm should sit', 'platform algorithms increasingly shape what content most users actually see each day', 'concern about the effect of social media on young people\'s mental health has grown substantially'],
        'vocabulary': ['online engagement', 'digital wellbeing', 'content moderation', 'algorithmic influence', 'social comparison', 'user privacy', 'viral content', 'online community', 'algorithmic amplification'],
    },
    'ai': {
        'keywords': {'artificial', 'intelligence', 'machine', 'learning', 'automation', 'chatbot', 'robot', 'algorithm'},
        'nouns': ['users', 'employees', 'developers', 'organisations', 'regulators'],
        'benefits': ['automate repetitive and time-consuming tasks', 'improve the accuracy of complex analysis', 'personalise services to individual needs', 'assist with early diagnosis and problem detection', 'free up human workers for higher-value tasks', 'process large amounts of information quickly', 'support decision-making with data-driven insights', 'help identify patterns that would take humans far longer to find'],
        'drawbacks': ['risk displacing certain categories of employment', 'reflect and reinforce biases present in training data', 'raise significant questions about accountability when errors occur', 'be difficult for non-experts to fully understand or audit', 'raise privacy concerns around large-scale data use', 'be misused to spread convincing misinformation', 'outpace the regulatory frameworks meant to govern it', 'produce confidently incorrect results that are hard to detect'],
        'examples': ['a hospital using an assistive tool to help flag potential diagnoses for review', 'a company automating routine customer queries and reassigning staff to complex cases', 'a school piloting an AI tutor and monitoring its effect on student outcomes', 'a regulator introducing new transparency requirements for automated decision systems', 'a research team auditing a system for bias before wider deployment', 'a customer service team using an AI assistant to handle routine queries, freeing staff for complex cases', 'a radiologist using an AI tool to flag possible anomalies that a first review had missed'],
        'contexts': ['the pace of development in this field continues to outstrip public understanding', 'attitudes toward these tools vary considerably depending on the specific application', 'regulatory approaches differ significantly between countries and regions', 'public trust depends heavily on transparency about how such systems are used', 'the balance between innovation and appropriate oversight remains widely debated', 'public understanding of how AI systems actually work still lags behind their rapid adoption', 'questions about who is accountable for AI-driven decisions remain largely unresolved in many industries'],
        'vocabulary': ['machine learning', 'algorithmic bias', 'automated decision-making', 'human oversight', 'data privacy', 'artificial intelligence ethics', 'workforce displacement', 'technological innovation', 'model reliability'],
    },
    'libraries': {
        'keywords': {'library', 'libraries', 'book', 'books', 'reading', 'archive', 'librarian', 'borrowing', 'literacy', 'shelves', 'study space', 'e-book', 'catalogue'},
        'nouns': ['readers', 'library staff', 'local communities', 'students', 'researchers'],
        'benefits': ['provide free access to books and information', 'support literacy and lifelong learning', 'offer a quiet, welcoming space for study', 'reduce inequality in access to knowledge', 'provide community programmes and events', 'give people without home internet a reliable way to get online', 'preserve historical and local records for public use', 'offer free, quiet study space in communities that lack it'],
        'drawbacks': ['face persistent pressure on public funding', 'struggle to compete with digital alternatives', 'need continual investment to keep collections current', 'have limited opening hours in smaller communities', 'require ongoing maintenance of ageing buildings', 'see declining footfall as reading habits shift online', 'find it difficult to justify costs to budget-conscious authorities', 'struggle to compete with the convenience of digital alternatives'],
        'examples': ['a library introducing a maker space and attracting a new generation of visitors', 'a rural community successfully campaigning to keep its local branch open', 'a library partnering with schools to run reading programmes for young children', 'a city library digitising its archive to widen public access', 'a branch offering free digital skills workshops for older residents', 'a rural library adding a maker-space and attracting a noticeably younger membership', 'a city closing several branch libraries during a budget crisis, leaving some areas without easy access'],
        'contexts': ['public library funding has come under increasing pressure in many countries', 'digital alternatives have changed how people access information and reading material', 'attitudes toward libraries differ between generations and between urban and rural areas', 'libraries increasingly serve as broader community hubs beyond simply lending books', 'literacy rates and library usage remain closely linked in most studies', 'digital resources have changed what people expect from a modern library visit', 'public library funding is often among the first services cut during budget shortfalls'],
        'vocabulary': ['public access', 'literacy programme', 'community resource', 'digital inclusion', 'lifelong learning', 'information access', 'library funding', 'reading engagement', 'archival preservation'],
    },
    'advertising': {
        'keywords': {'advertising', 'marketing', 'consumer', 'product', 'brand', 'commercial', 'advert', 'advertisement', 'campaign', 'promotion', 'sponsor', 'sponsorship', 'influencer', 'billboard', 'jingle', 'endorsement'},
        'nouns': ['consumers', 'advertisers', 'businesses', 'regulators', 'children'],
        'benefits': ['help consumers discover new products and services', 'support competition between businesses', 'fund free access to media and online content', 'help small businesses reach new customers', 'inform consumers about available choices', 'encourage innovation as businesses compete for attention', 'provide employment across a wide creative industry', 'help ethical or sustainable brands reach receptive audiences'],
        'drawbacks': ['use manipulative techniques to influence behaviour', 'encourage unnecessary or excessive consumption', 'target vulnerable groups such as children', 'blur the line between genuine content and promotion', 'contribute to unrealistic social comparisons', 'be difficult for regulators to monitor consistently', 'erode trust when claims turn out to be misleading', 'exploit psychological triggers to encourage impulsive spending'],
        'examples': ['a regulator introducing stricter rules on advertising aimed at children', 'a brand facing criticism after an advertisement was found to be misleading', 'a platform requiring clearer labelling for sponsored content', 'a small business growing rapidly after a modest but well-targeted advertising campaign', 'a consumer group launching a campaign to improve advertising transparency', 'a platform banning a category of ads after repeated complaints about misleading claims', 'a small brand building recognition entirely through low-cost social media advertising'],
        'contexts': ['advertising regulation varies considerably between countries and media types', 'digital advertising has changed dramatically as platforms collect more consumer data', 'public trust in advertising claims differs across industries and demographics', 'children and young people are considered particularly vulnerable to advertising influence', 'the shift to online advertising has raised new questions about privacy and consent', 'targeted advertising has raised growing questions about how much personal data companies collect', 'advertising spend has shifted dramatically from traditional media toward online platforms in recent years'],
        'vocabulary': ['consumer behaviour', 'brand awareness', 'advertising regulation', 'targeted marketing', 'commercial influence', 'consumer protection', 'sponsored content', 'market competition', 'programmatic advertising'],
    },
    'energy': {
        'keywords': {'energy', 'electricity', 'renewable', 'solar', 'wind', 'coal', 'oil', 'gas', 'power'},
        'nouns': ['households', 'energy companies', 'governments', 'industries', 'consumers'],
        'benefits': ['increase long-term energy security', 'reduce harmful greenhouse gas emissions', 'lower household energy costs over time', 'create new jobs in emerging industries', 'reduce dependence on volatile international fuel markets', 'improve reliability of the wider electricity grid', 'support broader environmental and climate goals', 'reduce a country\'s exposure to volatile global fuel markets'],
        'drawbacks': ['require substantial upfront infrastructure investment', 'depend on weather conditions for consistent supply', 'need significant upgrades to existing electricity grids', 'face resistance from established energy industries', 'take considerable time to scale to full capacity', 'raise concerns about the availability of specialised materials', 'create short-term price volatility during the transition', 'require costly upgrades to already outdated infrastructure'],
        'examples': ['a region investing heavily in wind power and reducing its reliance on imported fuel', 'a household installing solar panels and reporting a noticeable drop in electricity bills', 'a utility company upgrading its grid to better handle variable renewable supply', 'a government introducing subsidies to make renewable installation more affordable', 'an industrial site switching to a hybrid energy system to improve reliability', 'a household cutting its energy bill significantly after switching to a smart thermostat', 'a country facing blackouts after an unusually cold winter strained an ageing power grid'],
        'contexts': ['energy policy varies considerably depending on a country\'s available natural resources', 'the pace of the transition to renewable energy differs widely across regions', 'energy security concerns have grown following recent global supply disruptions', 'public support for renewable investment often depends on its visible cost to consumers', 'technological improvements continue to lower the cost of renewable generation', 'energy prices have become a politically sensitive issue in many countries in recent years', 'the reliability of ageing energy infrastructure is a growing concern as demand continues to rise'],
        'vocabulary': ['renewable energy', 'energy security', 'grid infrastructure', 'carbon emissions', 'energy efficiency', 'fossil fuel dependence', 'sustainable power generation', 'energy transition', 'grid modernisation'],
    },
    'internet': {
        'keywords': {'internet', 'online', 'web', 'website', 'digital', 'connectivity', 'broadband', 'wifi', 'browsing', 'network', 'connection', 'access', 'offline', 'bandwidth'},
        'nouns': ['internet users', 'internet service providers', 'businesses', 'regulators', 'rural communities'],
        'benefits': ['increase access to information and services', 'support remote work and online learning', 'enable small businesses to reach global customers', 'improve communication across long distances', 'expand access to online banking and public services', 'support innovation across many industries', 'reduce the cost of accessing certain services', 'allow small, remote businesses to reach a global market'],
        'drawbacks': ['leave some communities without reliable access', 'create new opportunities for cybercrime and fraud', 'raise ongoing concerns about personal privacy', 'demand continual infrastructure investment and maintenance', 'widen the digital divide between connected and unconnected areas', 'expose users to unmoderated harmful content', 'depend on infrastructure vulnerable to outages and attacks', 'be exploited by scams that specifically target inexperienced users'],
        'examples': ['a rural region gaining broadband access and seeing local businesses expand online', 'a bank shifting most services online and reducing the need for physical branches', 'a school providing devices and connectivity to students without home internet', 'a government investing in national broadband infrastructure to close the digital divide', 'a small online retailer scaling rapidly after improved local internet access', 'a rural community gaining reliable broadband for the first time and seeing new local businesses emerge', 'a student struggling to complete online coursework because of an unreliable home connection'],
        'contexts': ['internet access remains highly uneven between wealthier and poorer regions', 'the reliability of connectivity varies considerably between urban and rural areas', 'cybersecurity threats have grown alongside the expansion of online services', 'closing the digital divide has become a stated priority in many countries', 'dependence on internet-based services continues to grow across most sectors', 'internet access remains far from universal, even in relatively wealthy countries', 'the digital divide between connected and unconnected communities continues to shape educational and economic opportunity'],
        'vocabulary': ['digital divide', 'broadband access', 'online connectivity', 'cybersecurity', 'internet infrastructure', 'digital services', 'remote access', 'data security', 'digital literacy'],
    },
    'youth': {
        'keywords': {'youth', 'teenager', 'teenagers', 'young', 'children', 'generation', 'adolescent', 'adolescents', 'teen', 'peer pressure', 'young adult', 'upbringing'},
        'nouns': ['young people', 'teenagers', 'schools', 'employers', 'families'],
        'benefits': ['prepare young people for future employment', 'build valuable practical and social skills', 'increase opportunities for civic participation', 'strengthen confidence and independence', 'provide constructive alternatives to unstructured time', 'support healthier long-term habits', 'widen access to mentoring and guidance', 'give young people practical experience before entering the workforce'],
        'drawbacks': ['add to academic and social pressure', 'be unevenly accessible depending on family circumstances', 'compete for limited time with schoolwork', 'not suit every young person\'s interests or needs', 'depend heavily on adequate adult supervision and support', 'expose young people to harmful online content', 'be undermined by rising rates of youth unemployment', 'leave many feeling unprepared for the pressures of adult responsibility'],
        'examples': ['a school introducing mentoring and reporting improved student confidence', 'a youth programme partnering with local employers to offer work experience', 'a community centre providing a safe space for young people after school', 'a charity running a mentoring scheme that led several participants into training', 'a local authority funding youth clubs in areas with limited existing provision', 'a youth centre reopening after years of closure and quickly becoming a hub for local teenagers', 'a young person reporting greater confidence after joining a structured mentoring programme'],
        'contexts': ['opportunities available to young people vary considerably depending on where they live', 'youth unemployment remains a persistent concern in many economies', 'attitudes toward how young people should spend their time differ between generations', 'schools increasingly play a role in preparing students for skills beyond academic subjects', 'access to mentoring and guidance is often uneven between wealthier and poorer areas', 'young people today face a notably different job market than previous generations did', 'concerns about youth mental health and wellbeing have become a prominent part of public debate'],
        'vocabulary': ['youth development', 'civic participation', 'skills training', 'social mobility', 'mentoring programme', 'youth unemployment', 'personal development', 'future opportunities', 'youth engagement'],
    },
    'language': {
        'keywords': {'language', 'languages', 'bilingual', 'fluent', 'communication', 'dialect', 'translation', 'vocabulary', 'accent', 'mother tongue', 'multilingual', 'linguistic', 'native speaker'},
        'nouns': ['learners', 'teachers', 'employers', 'multilingual communities', 'young people'],
        'benefits': ['improve communication across cultures', 'expand access to international education and employment', 'strengthen cognitive and problem-solving skills', 'support cultural understanding and exchange', 'improve career prospects in a global economy', 'help preserve minority languages and traditions', 'ease integration for migrant communities', 'open access to a wider range of educational and career opportunities'],
        'drawbacks': ['require sustained effort and consistent practice', 'be difficult to access without adequate resources', 'take years to reach genuine fluency', 'not be equally prioritised across education systems', 'place pressure on minority languages as dominant ones spread', 'be under-resourced in schools with limited funding', 'depend heavily on opportunities for real-world practice', 'be threatened by the dominance of a small number of global languages'],
        'examples': ['a school introducing immersive language classes and reporting stronger long-term retention', 'a business expanding into new markets after hiring multilingual staff', 'a community programme helping migrants improve their language skills and confidence', 'a university offering exchange programmes that significantly improved student fluency', 'a region launching an initiative to preserve a declining minority language', 'a minority-language school reporting a sharp rise in enrolment after years of decline', 'a bilingual employee finding new career opportunities specifically because of their language skills'],
        'contexts': ['access to quality language education varies considerably between regions', 'globalisation has increased demand for multilingual skills in many industries', 'minority languages face growing pressure as dominant languages spread further', 'attitudes toward bilingual education differ significantly between countries', 'digital tools have changed how people practise and maintain language skills', 'many minority languages face a real risk of disappearing within a generation without active support', 'multilingualism is increasingly valued in globalised workplaces and international institutions'],
        'vocabulary': ['language proficiency', 'cultural exchange', 'multilingual education', 'communication skills', 'language preservation', 'fluency development', 'cross-cultural understanding', 'linguistic diversity', 'language revitalisation'],
    },
    'democracy': {
        'keywords': {'democracy', 'democratic', 'election', 'vote', 'voting', 'representation', 'ballot', 'candidate', 'parliament', 'referendum', 'electorate', 'constituency', 'suffrage', 'accountability', 'governance'},
        'nouns': ['citizens', 'voters', 'policymakers', 'local communities', 'civil society groups'],
        'benefits': ['increase public participation in decision-making', 'improve accountability of elected representatives', 'give a wider range of voices political representation', 'strengthen public trust in institutions over time', 'encourage more informed public debate', 'provide a peaceful mechanism for resolving disagreement', 'improve responsiveness of government to public concerns', 'give citizens a peaceful mechanism for changing unpopular policies'],
        'drawbacks': ['be vulnerable to the spread of misinformation', 'suffer from declining public engagement in some areas', 'be undermined by unequal access to political participation', 'produce slow decision-making on urgent issues', 'be exploited by narrow or short-term interests', 'be affected by growing political polarisation', 'require sustained public trust to function effectively', 'be undermined by misinformation during election campaigns'],
        'examples': ['a city introducing participatory budgeting and increasing resident involvement', 'an election authority improving transparency after concerns about public trust', 'a civic organisation running workshops to increase youth voter turnout', 'a local council holding public consultations before major infrastructure decisions', 'a government introducing stronger safeguards against electoral misinformation', 'a country lowering its voting age and reporting a modest rise in youth political engagement', 'an independent election observer group flagging irregularities that led to a rerun of a local vote'],
        'contexts': ['levels of civic participation vary considerably between countries and communities', 'trust in democratic institutions has fluctuated significantly in recent years', 'younger generations often engage with civic participation differently than older ones', 'the influence of digital media on public debate continues to evolve rapidly', 'strengthening democratic participation remains a priority in many policy discussions', 'voter turnout has declined in many established democracies over the past few decades', 'public trust in electoral institutions varies considerably depending on recent political history'],
        'vocabulary': ['civic participation', 'political accountability', 'public trust', 'electoral integrity', 'informed debate', 'representative democracy', 'voter engagement', 'transparent governance', 'civic representation'],
    },
    'sustainability': {
        'keywords': {'sustainability', 'sustainable', 'green', 'resources', 'circular', 'recycling', 'conservation', 'eco-friendly', 'footprint', 'longevity', 'stewardship'},
        'nouns': ['businesses', 'governments', 'communities', 'future generations', 'consumers'],
        'benefits': ['protect natural resources for future generations', 'reduce long-term environmental and economic risk', 'encourage more responsible consumption habits', 'support more resilient local economies', 'reduce waste through more efficient resource use', 'strengthen long-term energy and resource security', 'align economic growth with environmental limits', 'future-proof businesses against tightening environmental regulation'],
        'drawbacks': ['require higher upfront investment than conventional approaches', 'be difficult to coordinate across competing priorities', 'take time to deliver measurable long-term benefits', 'raise short-term costs for businesses and consumers', 'depend on sustained political and public commitment', 'be undermined by inconsistent international standards', 'compete with more immediate economic pressures', 'be dismissed as performative when not backed by measurable action'],
        'examples': ['a company redesigning its packaging to reduce long-term waste', 'a city adopting circular-economy principles in its municipal waste programme', 'a business switching to renewable energy sources and reporting lower long-term costs', 'a region setting binding sustainability targets and tracking progress publicly', 'a manufacturer redesigning products to be more easily repaired and reused', 'a manufacturer redesigning a product line to use significantly less packaging material', 'a city committing to a long-term sustainability target and publishing annual progress reports'],
        'contexts': ['sustainability priorities differ considerably depending on a country\'s stage of development', 'the balance between short-term cost and long-term benefit remains widely debated', 'consumer demand for more sustainable products has grown steadily in recent years', 'international cooperation is often needed to make meaningful long-term progress', 'businesses increasingly treat sustainability as a core strategic priority rather than an afterthought', 'sustainability commitments are sometimes criticised as vague marketing rather than measurable action', 'consumers increasingly say they want more sustainable products, even when they do not always buy them'],
        'vocabulary': ['sustainable development', 'circular economy', 'resource efficiency', 'long-term resilience', 'responsible consumption', 'environmental stewardship', 'sustainability targets', 'future generations', 'greenwashing'],
    },
    'immigration': {
        'keywords': {'immigration', 'immigrants', 'migrant', 'migrants', 'migration', 'immigrant', 'refugee', 'refugees', 'emigrate', 'diaspora', 'foreigners'},
        'nouns': ['immigrants', 'host countries', 'local communities', 'governments', 'employers', 'immigration officials'],
        'benefits': ['fill important skills gaps in the labour market', 'bring valuable cultural diversity to local communities', 'help offset the effects of an ageing population', 'contribute significantly to the local and national economy', 'introduce new perspectives and entrepreneurial energy', 'strengthen international ties between countries', 'support sectors that struggle to recruit locally', 'help address labour shortages in critical industries'],
        'drawbacks': ['place additional pressure on public services in the short term', 'create integration challenges without adequate support', 'lead to competition for lower-skilled jobs and housing', 'strain community relations if poorly managed', 'be difficult to coordinate across different government departments', 'expose newcomers to exploitation without proper safeguards', 'meet resistance from parts of the host community', 'strain public services in areas without adequate additional investment'],
        'examples': ['a city establishing language classes that helped new arrivals integrate faster', 'a hospital recruiting overseas-trained doctors to address staff shortages', 'a small town revitalised economically after welcoming a wave of new residents', 'a company sponsoring skilled workers and reporting stronger innovation as a result', 'a community organisation running mentorship schemes that eased newcomers into local life', 'a country easing visa rules for skilled workers and reporting a rise in filled vacancies', 'a local community adapting quickly after a sudden increase in newly arrived families'],
        'contexts': ['immigration policy remains one of the most politically contested issues in many countries', 'public attitudes toward immigration often shift depending on economic conditions', 'the long-term fiscal impact of immigration is debated extensively among economists', 'different countries take markedly different approaches to managing immigration', 'labour shortages in specific sectors have renewed political interest in this issue', 'public attitudes toward immigration vary considerably depending on local economic conditions', 'integration outcomes often depend heavily on the quality of language and employment support available'],
        'vocabulary': ['labour market', 'cultural integration', 'host community', 'skilled migration', 'social cohesion', 'public services', 'demographic change', 'asylum process', 'integration policy'],
    },
    'gender_equality': {
        'keywords': {'gender', 'equality', 'feminism', 'discrimination', 'sexism', 'equal', 'pay', 'workplace', 'stereotype', 'stereotypes', 'representation', 'parity', 'harassment', 'glass ceiling'},
        'nouns': ['women', 'employers', 'policymakers', 'organisations', 'families', 'young people'],
        'benefits': ['give everyone a fairer chance to succeed based on merit', 'improve overall organisational performance through diverse perspectives', 'reduce the persistent gender pay gap over time', 'encourage more balanced representation in leadership roles', 'challenge harmful stereotypes from an early age', 'strengthen trust in institutions seen as fair', 'widen the talent pool available to employers', 'expand the pool of talent available to employers'],
        'drawbacks': ['face resistance from those who benefit from the current system', 'be difficult to enforce consistently across different sectors', 'require long-term cultural change that outlasts any single policy', 'risk becoming a symbolic gesture without real structural change', 'need careful monitoring to avoid unintended side effects', 'be undermined without genuine commitment from leadership', 'take longer to show results than short political cycles allow', 'face resistance rooted in long-standing cultural expectations'],
        'examples': ['a company publishing pay-gap data and setting targets to close it', 'a school introducing mentorship schemes to encourage girls into STEM subjects', 'a government mandating parental leave for both parents to share caregiving', 'an organisation revising its hiring process to reduce unconscious bias', 'a country reserving a minimum share of board seats for women', 'a company introducing transparent salary bands and narrowing its previously unexplained pay gap', 'a school revising its careers guidance after noticing persistent gender patterns in subject choices'],
        'contexts': ['progress toward gender equality varies considerably between countries and industries', 'public debate on this issue often reflects deeper disagreements about social roles', 'measurable indicators such as pay and representation are widely used to track progress', 'attitudes among younger generations have shifted noticeably in recent decades', 'legal protections alone are not always sufficient to change everyday practice', 'progress on gender equality has varied considerably across different industries and countries', 'representation in senior leadership roles remains uneven despite decades of formal equality policies'],
        'vocabulary': ['gender pay gap', 'workplace equality', 'unconscious bias', 'equal opportunity', 'gender representation', 'structural discrimination', 'work-life balance', 'social attitudes', 'workplace parity'],
    },
    'animal_welfare': {
        'keywords': {'animal', 'animals', 'wildlife', 'zoo', 'zoos', 'endangered', 'extinction', 'poaching'},
        'nouns': ['conservationists', 'governments', 'zoos', 'farmers', 'researchers', 'local communities'],
        'benefits': ['help protect endangered species from extinction', 'preserve biodiversity for future generations', 'raise public awareness of conservation issues', 'support ecosystems that humans also depend on', 'improve standards of care for animals in captivity', 'strengthen international cooperation on conservation', 'provide valuable data for scientific research', 'encourage more humane practices across entire supply chains'],
        'drawbacks': ['be expensive to fund and sustain over the long term', 'conflict with the economic interests of local communities', 'be difficult to enforce in remote or under-resourced areas', 'raise ethical questions about keeping animals in captivity', 'require ongoing international coordination to be effective', 'produce results that take years or decades to measure', 'face resistance from industries reliant on animal products', 'raise production costs that are often passed on to consumers'],
        'examples': ['a national park reintroducing a locally extinct species and monitoring its recovery', 'a zoo redesigning enclosures to better reflect animals\' natural habitats', 'a country banning a harmful farming practice after public campaigning', 'a research team using tracking technology to protect a migratory species', 'a community-led patrol programme that reduced poaching in a protected area', 'a supermarket chain switching entirely to higher-welfare eggs after sustained customer pressure', 'a shelter reporting a sharp rise in adoptions after a local awareness campaign'],
        'contexts': ['approaches to animal welfare vary considerably between cultures and legal systems', 'conservation efforts increasingly rely on international funding and cooperation', 'the balance between economic development and habitat protection remains contested', 'public interest in animal welfare has grown alongside greater media coverage', 'scientific understanding of animal cognition continues to shape ethical debate', 'consumer demand for higher welfare standards has grown steadily in recent years', 'enforcement of animal welfare regulations varies considerably between countries and industries'],
        'vocabulary': ['biodiversity loss', 'endangered species', 'habitat protection', 'animal sentience', 'conservation programme', 'wildlife trafficking', 'captive breeding', 'ecosystem balance', 'welfare standards'],
    },
    'space_exploration': {
        'keywords': {'astronaut', 'astronauts', 'rocket', 'rockets', 'nasa', 'satellite', 'satellites', 'spacecraft', 'spaceflight', 'exploration', 'exploring', 'interstellar'},
        'nouns': ['space agencies', 'scientists', 'private companies', 'governments', 'astronauts', 'researchers'],
        'benefits': ['drive major advances in science and technology', 'inspire greater public interest in science education', 'improve satellite technology used in everyday life', 'expand human understanding of the universe', 'open new possibilities for long-term resource use', 'strengthen international scientific cooperation', 'create highly skilled jobs in engineering and research', 'drive innovation with applications well beyond space itself'],
        'drawbacks': ['require enormous public or private investment', 'carry significant risk to human life', 'divert funding from more immediate priorities on Earth', 'raise unresolved questions about space resource ownership', 'produce benefits that are difficult to measure in the short term', 'increase the amount of debris orbiting the planet', 'depend on political will that can change with each administration', 'raise difficult questions about the value of cost relative to benefit'],
        'examples': ['a space agency landing a rover that revealed new evidence about a planet\'s history', 'a private company reducing launch costs through reusable rocket technology', 'a satellite programme improving weather forecasting accuracy worldwide', 'an international mission combining resources from several countries', 'a research station testing technology needed for long-term space habitation', 'a private company cutting launch costs and making satellite deployment newly affordable for small countries', 'a national space agency inspiring a noticeable rise in student interest in engineering courses'],
        'contexts': ['space exploration increasingly involves private companies alongside national agencies', 'public support for space spending often depends on visible scientific or economic returns', 'international cooperation and competition both shape the pace of progress', 'advances in this field frequently produce unexpected benefits in other industries', 'the long-term goal of settling other planets remains a subject of active debate', 'private companies now play a far larger role in space exploration than they did a generation ago', 'the cost and risk of crewed missions remain central to debates over how ambitious space programmes should be'],
        'vocabulary': ['space exploration', 'scientific discovery', 'orbital technology', 'space agency', 'launch costs', 'planetary research', 'international cooperation', 'technological spin-off', 'technological spillover'],
    },
    'arts_culture_funding': {
        'keywords': {'museum', 'museums', 'theatre', 'theatres', 'theater', 'theaters', 'gallery', 'galleries', 'artist', 'artists', 'orchestra'},
        'nouns': ['artists', 'governments', 'museums', 'local communities', 'cultural institutions', 'audiences'],
        'benefits': ['enrich community life and civic identity', 'preserve important cultural heritage for future generations', 'provide meaningful career opportunities for creative professionals', 'boost local economies through tourism and events', 'improve public wellbeing and mental health', 'encourage creative thinking from an early age', 'strengthen a sense of shared cultural identity', 'give emerging artists a viable path into a competitive industry'],
        'drawbacks': ['compete for limited public funding with other priorities', 'be difficult to justify in narrowly economic terms', 'benefit some communities more than others', 'depend heavily on inconsistent public or private funding', 'struggle to remain financially sustainable without support', 'be vulnerable to shifts in government spending priorities', 'face criticism over how funding decisions are made', 'favour established institutions over smaller, independent organisations'],
        'examples': ['a city investing in a cultural quarter and reporting a rise in local tourism', 'a museum introducing free entry and seeing a sharp increase in visitor numbers', 'a small theatre securing public funding and expanding its education programmes', 'a local government supporting street art projects that revitalised a neglected area', 'an arts charity partnering with schools to widen access to music education', 'a regional theatre closing after losing its public funding grant', 'a museum introducing free admission and reporting a significant rise in first-time visitors'],
        'contexts': ['public funding for the arts remains a recurring subject of political debate', 'attitudes toward cultural spending often shift during periods of economic hardship', 'the value of the arts is measured in both economic and social terms', 'different countries take very different approaches to funding cultural institutions', 'digital platforms have changed how audiences access and engage with the arts', 'public arts funding is often among the first budget lines cut during financial pressure', 'smaller, community-based arts organisations are typically more vulnerable to funding cuts than major institutions'],
        'vocabulary': ['cultural heritage', 'public funding', 'creative industries', 'artistic expression', 'community engagement', 'cultural identity', 'arts education', 'civic pride', 'cultural capital'],
    },
    'urbanisation': {
        'keywords': {'urban', 'urbanisation', 'urbanization', 'skyscraper', 'skyscrapers', 'suburb', 'suburbs', 'megacity', 'megacities', 'metropolis'},
        'nouns': ['city planners', 'residents', 'local governments', 'developers', 'commuters', 'urban communities'],
        'benefits': ['create greater access to jobs and services', 'support more efficient public infrastructure', 'encourage innovation through closer collaboration', 'improve access to healthcare and education', 'make public transport more economically viable', 'concentrate cultural and economic opportunity', 'attract investment that benefits the wider region', 'concentrate economic opportunity where infrastructure already exists'],
        'drawbacks': ['increase pressure on housing affordability', 'worsen traffic congestion and air quality', 'strain existing infrastructure beyond its intended capacity', 'widen inequality between well-served and under-served areas', 'reduce access to green space for residents', 'make cities more vulnerable to overcrowding', 'require costly long-term infrastructure investment', 'increase pressure on already strained housing and transport systems'],
        'examples': ['a city expanding its metro network to keep pace with population growth', 'a local government introducing affordable-housing quotas for new developments', 'a district converting former industrial land into public green space', 'a city government piloting car-free zones to ease congestion', 'a rapidly growing city investing early in flood-resistant infrastructure', 'a fast-growing city struggling to expand public services quickly enough to match population growth', 'a formerly declining town attracting new residents after investment in transport links'],
        'contexts': ['urbanisation is proceeding at very different rates across different regions', 'the strain on housing and infrastructure varies considerably between cities', 'balancing growth with liveability remains a central challenge for planners', 'migration from rural areas continues to drive urban population growth', 'climate considerations increasingly shape how new urban areas are designed', 'rapid urban growth often outpaces the infrastructure needed to support it', 'rural areas in many countries continue to lose population as opportunities concentrate in cities'],
        'vocabulary': ['urban planning', 'population density', 'housing affordability', 'public infrastructure', 'urban sprawl', 'green space', 'sustainable city', 'commuting patterns', 'urban density'],
    },
    'tradition_modernity': {
        'keywords': {'tradition', 'traditions', 'traditional', 'modernisation', 'modernization', 'custom', 'customs', 'ancestral', 'folklore'},
        'nouns': ['communities', 'younger generations', 'older generations', 'societies', 'families', 'cultural groups'],
        'benefits': ['preserve a valuable sense of cultural identity', 'strengthen intergenerational bonds within families', 'provide continuity and stability during periods of change', 'pass down practical knowledge accumulated over generations', 'give communities a distinct cultural character', 'offer a meaningful counterbalance to rapid modernisation', 'support tourism built around cultural heritage', 'allow communities to adapt without fully abandoning their identity'],
        'drawbacks': ['sometimes conflict with the practical demands of modern life', 'be difficult to reconcile with evolving social attitudes', 'place pressure on younger generations to conform', 'lose relevance as circumstances change over time', 'be at risk of disappearing without active preservation', 'create tension between generations with different priorities', 'be challenged by increasing exposure to global culture', 'create friction between generations with differing expectations'],
        'examples': ['a community reviving a traditional craft as a source of local income', 'a family adapting a long-standing custom to fit modern working patterns', 'a country introducing heritage education programmes in schools', 'a city preserving its historic architecture while allowing modern development nearby', 'a younger generation blending traditional festivals with contemporary celebrations', 'a family adapting a traditional celebration to include newer, more convenient customs', 'a craftsperson combining traditional techniques with modern tools to reach new markets'],
        'contexts': ['the balance between tradition and modernity plays out differently across cultures', 'globalisation has accelerated the pace at which traditional practices are challenged', 'attitudes toward tradition often differ sharply between generations', 'many societies are actively working to preserve heritage alongside development', 'cultural identity remains an important source of belonging even amid rapid change', 'the pace of modernisation varies considerably between urban and rural communities', 'many communities actively debate how much tradition to preserve as modern life changes daily routines'],
        'vocabulary': ['cultural identity', 'intergenerational change', 'heritage preservation', 'social values', 'modernisation', 'customary practice', 'cultural continuity', 'globalised culture', 'generational change'],
    },
    'volunteering': {
        'keywords': {'volunteer', 'volunteering', 'charity', 'nonprofit', 'donation', 'fundraising', 'unpaid', 'philanthropy', 'giving back', 'outreach'},
        'nouns': ['volunteers', 'charities', 'local communities', 'young people', 'nonprofit organisations', 'employers'],
        'benefits': ['build valuable skills and practical experience', 'strengthen ties within local communities', 'support causes that public services cannot fully address', 'improve volunteers\' own sense of wellbeing and purpose', 'give young people meaningful early work experience', 'help charities extend their reach without large budgets', 'encourage a stronger culture of civic participation', 'build practical skills valued by future employers'],
        'drawbacks': ['be difficult to sustain without a steady base of volunteers', 'sometimes replace paid roles that should be properly funded', 'require training and coordination that charities may lack resources for', 'be inaccessible to people who cannot afford unpaid time', 'produce inconsistent quality without proper oversight', 'depend heavily on goodwill that can fade over time', 'be undervalued despite the real contribution volunteers make', 'be unsustainable when relying on a shrinking pool of willing participants'],
        'examples': ['a university making a short volunteering placement part of every degree', 'a local charity recruiting retirees to mentor young jobseekers', 'a company giving employees paid time off to volunteer locally', 'a food bank relying on weekend volunteers to meet rising demand', 'a national scheme matching skilled professionals with charities that need their expertise', 'a retiree taking up regular volunteering and reporting a renewed sense of purpose', 'a small charity struggling to recruit enough volunteers to keep a long-running programme going'],
        'contexts': ['rates of volunteering vary considerably between countries and age groups', 'the relationship between volunteering and paid employment remains debated', 'many charities depend heavily on volunteers to deliver their core services', 'schools and employers increasingly recognise the value of volunteering experience', 'public appetite for volunteering often rises during times of crisis', 'volunteering rates have shifted noticeably as people balance more demanding work schedules', 'many nonprofit organisations rely heavily on volunteers to deliver services they could not otherwise afford'],
        'vocabulary': ['civic participation', 'community service', 'nonprofit sector', 'volunteer programme', 'social impact', 'charitable work', 'skills development', 'public goodwill', 'community impact'],
    },
    'privacy_technology': {
        'keywords': {'privacy', 'surveillance', 'tracking', 'cybersecurity', 'encryption', 'data', 'personal', 'breach', 'hacking', 'password', 'security', 'online', 'digital', 'consent', 'monitoring', 'identity', 'cookies', 'biometric'},
        'nouns': ['technology companies', 'governments', 'users', 'regulators', 'consumers', 'security researchers'],
        'benefits': ['give individuals greater control over their personal information', 'improve trust between users and online services', 'reduce the risk of identity theft and fraud', 'encourage companies to adopt stronger security practices', 'support more informed consent around data collection', 'strengthen accountability for how data is used', 'protect vulnerable groups from targeted exploitation', 'give users clearer choices over how their data is used'],
        'drawbacks': ['be costly for smaller companies to implement fully', 'be difficult to enforce consistently across borders', 'sometimes limit the convenience of personalised services', 'struggle to keep pace with rapidly evolving technology', 'be undermined by inconsistent international regulation', 'require ongoing public education to be genuinely effective', 'create compliance burdens that favour larger companies', 'be undermined by opaque terms most users never fully read'],
        'examples': ['a country introducing strict data-protection laws that reshaped how companies operate', 'a technology company offering clearer privacy settings after user complaints', 'a bank adopting stronger authentication methods to prevent fraud', 'a regulator fining a company for mishandling customer data', 'a browser introducing default tracking protection for its users', 'a company facing public backlash after quietly changing its data-sharing policy', 'a user switching to a privacy-focused browser after learning how much data was being collected'],
        'contexts': ['data-privacy regulation varies considerably between different countries and regions', 'public awareness of data privacy has grown significantly in recent years', 'the balance between convenience and privacy remains a persistent source of debate', 'high-profile data breaches have repeatedly renewed public and political attention', 'rapid technological change continues to outpace existing legal frameworks', 'public awareness of data collection practices has grown significantly following major breaches', 'the tension between personalised services and personal privacy remains largely unresolved'],
        'vocabulary': ['data privacy', 'personal information', 'digital security', 'informed consent', 'data protection law', 'online tracking', 'cybersecurity risk', 'regulatory compliance', 'data minimisation'],
    },
    'mental_health': {
        'keywords': {'mental', 'anxiety', 'depression', 'therapy', 'counselling', 'burnout', 'stress', 'wellbeing', 'psychological', 'self-care', 'emotional', 'resilience', 'support group'},
        'nouns': ['individuals', 'employers', 'schools', 'healthcare providers', 'families', 'mental health professionals'],
        'benefits': ['help people manage stress before it becomes overwhelming', 'reduce the stigma surrounding mental health conditions', 'improve productivity and engagement in the workplace', 'give young people tools to cope with pressure early on', 'encourage earlier diagnosis and more effective treatment', 'strengthen relationships through greater emotional awareness', 'reduce long-term healthcare costs linked to untreated conditions', 'normalise conversations that were once considered taboo'],
        'drawbacks': ['be under-resourced relative to the scale of demand', 'face a shortage of trained mental health professionals', 'carry lingering social stigma that discourages people from seeking help', 'be difficult to access equally across income groups', 'require sustained funding that competes with other health priorities', 'vary considerably in quality between providers', 'be hard to measure in terms of clear, immediate outcomes', 'be limited by long waiting times for specialist care'],
        'examples': ['a school introducing counselling services and reporting improved student wellbeing', 'a company offering mental health days and seeing lower staff turnover', 'a national campaign that measurably reduced stigma around seeking help', 'a workplace training managers to recognise early signs of burnout', 'a healthcare system expanding access to free counselling for young people', 'a workplace introducing mental health days and reporting reduced staff burnout', 'a school adding a counsellor and seeing more students seek help earlier'],
        'contexts': ['awareness of mental health has grown substantially over the past decade', 'access to mental health support varies considerably by income and location', 'workplaces increasingly treat mental health as a core wellbeing priority', 'public discussion of mental health remains more open than in previous generations', 'demand for mental health services has risen faster than available resources', 'demand for mental health services has risen faster than many systems can currently meet', 'stigma around seeking mental health support has decreased but has not disappeared'],
        'vocabulary': ['mental wellbeing', 'stigma reduction', 'early intervention', 'workplace wellbeing', 'access to care', 'emotional resilience', 'burnout prevention', 'support services', 'treatment accessibility'],
    },
    'artificial_intelligence_ethics': {
        'keywords': {'deepfake', 'deepfakes', 'algorithmic', 'bias', 'ai', 'artificial', 'intelligence', 'automation', 'algorithm', 'automated', 'machine', 'learning', 'ethics', 'ethical', 'regulation', 'accountability', 'transparency', 'misuse', 'discrimination', 'surveillance'},
        'nouns': ['developers', 'regulators', 'companies', 'users', 'researchers', 'policymakers'],
        'benefits': ['help identify and correct bias before systems cause harm', 'build greater public trust in automated decision-making', 'ensure accountability when algorithms make consequential decisions', 'encourage more transparent and explainable systems', 'protect vulnerable groups from unfair automated outcomes', 'guide innovation toward genuinely beneficial applications', 'reduce the risk of unintended large-scale harm', 'clarify legal responsibility when automated systems cause harm'],
        'drawbacks': ['be difficult to define and measure consistently', 'slow the pace of innovation if applied too rigidly', 'be hard to enforce across international borders', 'require technical expertise that regulators often lack', 'struggle to keep pace with rapidly evolving technology', 'create compliance costs that smaller developers cannot easily absorb', 'be undermined without genuine international cooperation', 'struggle to keep pace with the speed of new model releases'],
        'examples': ['a company auditing its hiring algorithm after it showed unintended bias', 'a government introducing transparency requirements for automated decisions', 'a research team publishing an open framework for testing AI fairness', 'a regulator requiring disclosure when content is AI-generated', 'a company establishing an independent ethics review board for new AI products', 'a hiring platform suspending an algorithm after it was found to disadvantage certain applicants', 'a research lab publishing its model\'s limitations openly rather than only its successes'],
        'contexts': ['debate over AI regulation is evolving rapidly as the technology advances', 'different countries are taking notably different regulatory approaches', 'public trust in AI systems depends heavily on perceived fairness and transparency', 'the pace of technological change frequently outstrips existing legal frameworks', 'industry self-regulation and government oversight are both actively debated', 'regulatory frameworks for AI are still being developed in most countries', 'public concern about AI-generated misinformation has grown alongside the technology\'s rapid improvement'],
        'vocabulary': ['algorithmic bias', 'AI accountability', 'automated decision-making', 'ethical oversight', 'transparency requirements', 'responsible innovation', 'regulatory framework', 'public trust', 'algorithmic accountability'],
    },
    'remote_work': {
        'keywords': {'telecommute', 'telecommuting', 'hybrid', 'telework', 'remote', 'work', 'job', 'office', 'commute', 'commuting', 'flexible', 'flexibility', 'workplace', 'employer', 'employee', 'home', 'videoconference', 'collaboration'},
        'nouns': ['employees', 'employers', 'managers', 'companies', 'families', 'city planners'],
        'benefits': ['give employees greater flexibility over their daily schedule', 'reduce time and money spent commuting', 'widen the talent pool available to employers', 'improve work-life balance for many workers', 'reduce office overhead costs for companies', 'lower commuting-related emissions', 'allow people to live further from expensive city centres', 'reduce the environmental impact of daily commuting'],
        'drawbacks': ['make spontaneous collaboration and mentoring harder', 'blur boundaries between work and personal time', 'disadvantage employees without a suitable home workspace', 'weaken the sense of team culture and belonging', 'complicate performance management for some managers', 'be harder to implement fairly across different roles', 'reduce demand for commercial office space in city centres', 'leave newer employees with fewer informal learning opportunities'],
        'examples': ['a company adopting a hybrid model and reporting steady productivity', 'an employee saving significant commuting time after switching to remote work', 'a city seeing reduced peak-hour congestion as remote work became common', 'a firm redesigning its office around collaboration rather than daily desks', 'a manager introducing clearer check-ins to keep a remote team connected', 'a company scaling back its office space after most staff chose to stay remote', 'a new employee struggling to build workplace relationships without ever meeting colleagues in person'],
        'contexts': ['attitudes toward remote work shifted significantly following the pandemic', 'the right balance between remote and office work remains widely debated', 'the impact on city centres and commercial property is still unfolding', 'different industries and roles vary considerably in how well they suit remote work', 'employee expectations around flexibility have changed substantially in recent years', 'employer and employee expectations around remote work do not always align', 'the long-term effect of remote work on career progression remains a subject of active debate'],
        'vocabulary': ['work-life balance', 'hybrid working', 'digital collaboration', 'flexible scheduling', 'office culture', 'commuting patterns', 'talent retention', 'workplace flexibility', 'asynchronous collaboration'],
    },
    'consumerism': {
        'keywords': {'consumerism', 'overconsumption', 'materialism', 'disposable', 'consumerist', 'shopping', 'buying', 'spending', 'brand', 'fashion', 'waste', 'packaging', 'advertising', 'marketing', 'possessions', 'purchase', 'retail', 'impulse'},
        'nouns': ['consumers', 'retailers', 'manufacturers', 'regulators', 'young people', 'advertisers'],
        'benefits': ['drive economic growth and job creation', 'give consumers greater choice and lower prices', 'encourage competition that improves product quality', 'fund innovation through strong consumer demand', 'support livelihoods across global supply chains', 'reflect rising living standards in many societies', 'give people the means to express personal identity', 'give consumers meaningful power to reward responsible companies'],
        'drawbacks': ['generate significant waste and environmental harm', 'encourage spending beyond what people can genuinely afford', 'be linked to poor labour conditions in some supply chains', 'foster a culture that equates possessions with self-worth', 'be difficult to curb without affecting economic growth', 'disproportionately affect low-income consumers targeted by aggressive marketing', 'contribute to resource depletion at a global scale', 'normalise short product lifespans designed to encourage repeat purchases'],
        'examples': ['a clothing brand introducing a resale scheme to reduce fast-fashion waste', 'a country taxing single-use products to discourage overconsumption', 'a retailer publishing supply-chain audits after public pressure', 'a campaign encouraging consumers to repair rather than replace goods', 'a company shifting toward a subscription model to reduce unnecessary production', 'a fast-fashion brand facing criticism after an investigation into its supply chain practices', 'a family adopting a minimalist approach and reporting reduced spending and less clutter'],
        'contexts': ['attitudes toward consumerism vary considerably across cultures and income levels', 'the environmental cost of overconsumption has become a growing public concern', 'social media has intensified pressure to continually buy new products', 'the balance between economic growth and sustainable consumption remains contested', 'younger consumers increasingly say they value sustainability over low price alone', 'social media has intensified pressure to continually purchase newer products', 'consumer debt levels have risen in step with more accessible short-term credit options'],
        'vocabulary': ['consumer culture', 'overconsumption', 'sustainable consumption', 'supply chain', 'planned obsolescence', 'materialism', 'ethical consumption', 'disposable culture', 'brand loyalty'],
    },
    'renewable_energy_transition': {
        'keywords': {'fossil', 'fuels', 'emissions', 'transition', 'renewable', 'energy', 'solar', 'wind', 'coal', 'oil', 'gas', 'carbon', 'electricity', 'grid', 'clean', 'net-zero', 'decarbonisation', 'battery'},
        'nouns': ['governments', 'energy companies', 'households', 'investors', 'engineers', 'communities'],
        'benefits': ['reduce dependence on imported fossil fuels', 'lower long-term greenhouse gas emissions', 'create new jobs in emerging clean-energy industries', 'improve national energy security over time', 'reduce exposure to volatile fossil-fuel prices', 'improve local air quality by cutting pollution', 'position early-adopting countries as technology leaders', 'create durable jobs in a growing global industry'],
        'drawbacks': ['require very large upfront infrastructure investment', 'depend on weather conditions that vary by region', 'strain existing electricity grids not designed for them', 'displace workers in traditional fossil-fuel industries', 'face slow permitting and planning processes in some countries', 'need significant new storage technology to be fully reliable', 'meet local resistance to new infrastructure projects', 'be slowed by permitting delays for large-scale infrastructure projects'],
        'examples': ['a country reaching a record share of electricity from renewable sources', 'a region retraining former coal workers for jobs in wind energy', 'a utility company investing in large-scale battery storage', 'a city requiring new buildings to include solar panels', 'a government offering subsidies that accelerated household solar adoption', 'a country closing its last coal plant years ahead of an original target', 'a coastal community building local jobs around a new offshore wind project'],
        'contexts': ['the pace of the renewable energy transition varies considerably between countries', 'the balance between energy security and environmental goals is often debated', 'technological improvements have steadily reduced the cost of renewable energy', 'political and economic pressures both shape how quickly countries can transition', 'the transition creates both opportunities and disruption for different industries', 'the pace of the transition depends heavily on political will as much as available technology', 'energy security concerns have added new urgency to renewable investment in several countries'],
        'vocabulary': ['renewable energy', 'carbon emissions', 'energy security', 'grid infrastructure', 'clean-energy jobs', 'net-zero target', 'energy transition', 'fossil fuel dependence', 'grid interconnection'],
    },
    'genetic_engineering': {
        'keywords': {'genetic', 'gmo', 'gene', 'crispr', 'cloning', 'genetically', 'dna', 'engineering', 'modification', 'biotechnology', 'hereditary', 'mutation', 'embryo', 'breeding'},
        'nouns': ['scientists', 'farmers', 'regulators', 'consumers', 'researchers', 'biotechnology companies'],
        'benefits': ['increase crop yields to help address food shortages', 'enable crops that are more resistant to disease and drought', 'open new possibilities for treating genetic diseases', 'reduce reliance on chemical pesticides in agriculture', 'accelerate medical research into inherited conditions', 'improve food security in vulnerable regions', 'lower long-term costs of certain medical treatments', 'offer new treatment options for previously incurable conditions'],
        'drawbacks': ['raise unresolved ethical questions about altering living organisms', 'carry uncertain long-term environmental effects', 'be expensive to research and develop safely', 'face inconsistent regulation across different countries', 'meet significant public scepticism and mistrust', 'risk unintended consequences for biodiversity', 'be difficult to reverse once released into ecosystems', 'raise unresolved ethical questions about long-term unintended effects'],
        'examples': ['a research team developing a drought-resistant crop variety for a vulnerable region', 'a country requiring clear labelling of genetically modified food products', 'a biotechnology company developing a gene therapy for a rare inherited disease', 'a regulator approving a modified crop only after extensive safety trials', 'a farming cooperative reporting higher yields after adopting modified seed varieties', 'a research team developing a disease-resistant crop that reduced the need for pesticides', 'a family facing a difficult decision after genetic testing revealed an inherited health risk'],
        'contexts': ['public attitudes toward genetic engineering vary considerably between countries', 'the science continues to advance faster than public understanding in many cases', 'regulatory approaches differ significantly between regions with different risk tolerances', 'ethical debate over genetic engineering spans both agricultural and medical applications', 'trust in the technology often depends on transparency and independent oversight', 'public opinion on genetic engineering varies considerably depending on its specific application', 'regulatory approval processes for genetically modified products differ substantially between countries'],
        'vocabulary': ['genetic modification', 'gene editing', 'biotechnology', 'food security', 'ethical oversight', 'crop resilience', 'regulatory approval', 'unintended consequences', 'genetic screening'],
    },
    'social_inequality': {
        'keywords': {'inequality', 'wealth', 'gap', 'class', 'privilege', 'mobility', 'poverty', 'disadvantaged', 'opportunity', 'disparity', 'income gap', 'marginalised', 'marginalized'},
        'nouns': ['governments', 'policymakers', 'low-income families', 'employers', 'communities', 'economists'],
        'benefits': ['direct resources toward those who need them most', 'improve social mobility across generations', 'reduce social tension linked to economic disparity', 'strengthen long-term economic stability', 'give more people the chance to develop their full potential', 'improve public health outcomes tied to economic security', 'build broader public trust in institutions seen as fair', 'highlight where targeted public investment could have the greatest impact'],
        'drawbacks': ['be politically difficult to address without broader consensus', 'require sustained funding that competes with other priorities', 'be resisted by groups who benefit from the current system', 'take a long time to produce measurable change', 'be difficult to address through policy alone', 'vary enormously in cause and solution between regions', 'risk unintended consequences if poorly designed', 'be reinforced across generations without deliberate policy intervention'],
        'examples': ['a country introducing a minimum wage increase linked to falling poverty rates', 'a city expanding affordable housing and reporting improved social mobility', 'a government targeting early education funding at disadvantaged areas', 'a company adopting transparent pay bands to reduce internal disparities', 'a region investing in vocational training to widen access to skilled jobs', 'a city expanding free public transport and reporting improved access to jobs in lower-income areas', 'a graduate from a disadvantaged background struggling to access the same networks as wealthier peers'],
        'contexts': ['levels of inequality vary considerably between and within countries', 'the causes of inequality are debated extensively among economists and policymakers', 'public attitudes toward redistribution often reflect deeper political divisions', 'inequality has measurable effects on health, education and social outcomes', 'addressing inequality typically requires coordinated action across many policy areas', 'income inequality has widened in many countries over the past several decades', 'access to opportunity remains strongly linked to family background in most societies'],
        'vocabulary': ['income inequality', 'social mobility', 'wealth distribution', 'economic opportunity', 'structural disadvantage', 'redistribution policy', 'poverty reduction', 'equal opportunity', 'intergenerational mobility'],
    },
    'space_and_astronomy_education': {
        'keywords': {'astronomy', 'telescope', 'telescopes', 'stargazing', 'planetarium', 'cosmos', 'space', 'universe', 'galaxy', 'planet', 'planets', 'star', 'stars', 'constellation', 'observatory', 'satellite'},
        'nouns': ['students', 'science teachers', 'schools', 'science communicators', 'researchers', 'young people'],
        'benefits': ['inspire greater interest in science and mathematics', 'make abstract scientific concepts more tangible for students', 'encourage curiosity and critical thinking from an early age', 'attract more young people into STEM careers', 'improve public scientific literacy', 'foster wonder and engagement with the natural world', 'connect classroom learning to real scientific discovery', 'give students a tangible connection to real ongoing scientific discovery'],
        'drawbacks': ['require specialised, sometimes costly equipment', 'be underfunded relative to other parts of the curriculum', 'depend heavily on individual teachers\' enthusiasm and training', 'be less accessible to schools in light-polluted urban areas', 'be difficult to fit within an already crowded curriculum', 'need ongoing investment to keep pace with new discoveries', 'vary considerably in quality between schools and regions', 'remain inaccessible to schools without basic science funding'],
        'examples': ['a school installing a telescope and reporting increased interest in science subjects', 'a science museum offering free planetarium shows to local schools', 'a university running a mentorship programme linking students with astronomers', 'a rural school hosting a stargazing night that drew the whole community', 'a national programme livestreaming a space mission directly into classrooms', 'a school partnering with a local observatory and reporting a rise in science club membership', 'a rural student gaining access to a virtual telescope programme previously available only to city schools'],
        'contexts': ['interest in astronomy education has grown alongside major space missions', 'access to astronomy resources varies considerably between schools and regions', 'public fascination with space often creates valuable teaching opportunities', 'science education increasingly draws on real-time data from ongoing space research', 'engagement with astronomy can influence students\' broader interest in science', 'online access has made professional-quality astronomy resources available to schools that could not previously afford them', 'major space missions often produce a temporary but measurable spike in student interest in science subjects'],
        'vocabulary': ['scientific literacy', 'STEM education', 'science communication', 'classroom engagement', 'astronomical observation', 'curriculum design', 'public outreach', 'inspiring curiosity', 'hands-on learning'],
    },
    'disaster_preparedness': {
        'keywords': {'disaster', 'disasters', 'preparedness', 'earthquake', 'earthquakes', 'flooding', 'hurricane', 'wildfire', 'wildfires', 'emergency'},
        'nouns': ['governments', 'emergency services', 'communities', 'residents', 'city planners', 'aid organisations'],
        'benefits': ['save lives by enabling faster, better-coordinated responses', 'reduce long-term economic damage from disasters', 'give communities clearer guidance on how to respond', 'improve the resilience of critical infrastructure', 'strengthen coordination between different emergency agencies', 'reduce strain on emergency services during a crisis', 'help vulnerable populations recover more quickly', 'reduce the psychological toll of future emergencies through familiarity'],
        'drawbacks': ['require ongoing investment that can be hard to justify before a disaster strikes', 'be difficult to fully prepare for events of unpredictable scale', 'strain limited budgets, especially in lower-income regions', 'depend on coordination across agencies that do not always cooperate well', 'be undermined by outdated infrastructure that is costly to replace', 'require public awareness campaigns that are hard to sustain over time', 'face the challenge of balancing preparedness cost against uncertain risk', 'be deprioritised by officials focused on more immediate concerns'],
        'examples': ['a city upgrading its early-warning system after a previous disaster exposed gaps', 'a community running regular evacuation drills that reduced confusion during a real emergency', 'a country investing in flood defences that prevented major damage in a later storm', 'a region establishing a rapid-response fund to speed up post-disaster recovery', 'a neighbourhood organising a local preparedness network that helped elderly residents', 'a coastal town rebuilding its seawall after a near-miss storm exposed a critical weakness', 'a school district running a joint earthquake drill with local emergency services'],
        'contexts': ['disaster preparedness levels vary considerably depending on a country\'s resources', 'climate change has increased the frequency and severity of some natural disasters', 'coordination between local, national and international agencies is critical during a crisis', 'public awareness and community-level planning are increasingly seen as essential complements to official response', 'the cost of inaction is often far higher than the cost of preparation', 'insurance markets increasingly reflect the growing financial risk of extreme weather events', 'aid coordination between local and international agencies remains a persistent challenge during major disasters'],
        'vocabulary': ['emergency response', 'disaster resilience', 'early-warning system', 'critical infrastructure', 'evacuation planning', 'community preparedness', 'risk mitigation', 'recovery efforts', 'risk communication'],
    },
    'freedom_of_speech': {
        'keywords': {'freedom', 'speech', 'censorship', 'censor', 'expression', 'press', 'suppression', 'dissent', 'protest', 'moderation'},
        'nouns': ['governments', 'citizens', 'media organisations', 'social media platforms', 'courts', 'activists'],
        'benefits': ['allow open debate on important public issues', 'hold those in power accountable through scrutiny', 'protect minority viewpoints from being silenced', 'support a free press capable of investigating wrongdoing', 'encourage the exchange of new and challenging ideas', 'strengthen democratic participation and public trust', 'give individuals the means to challenge injustice publicly', 'allow injustices to be exposed even when powerful interests object'],
        'drawbacks': ['can be misused to spread harmful misinformation', 'make it harder to regulate genuinely dangerous content', 'be difficult to balance against protection from harassment', 'vary enormously in legal protection between countries', 'be exploited to incite violence or hatred in some cases', 'create tension between platform moderation and open expression', 'be restricted more easily during periods of political instability', 'be invoked to justify the spread of demonstrably false claims'],
        'examples': ['a court striking down a law that had restricted press criticism of officials', 'a platform introducing clearer, more transparent content-moderation policies', 'a journalist successfully challenging government censorship in court', 'a country strengthening legal protections for whistleblowers', 'a media organisation publishing an investigation despite political pressure to suppress it', 'a student newspaper facing pressure after publishing a critical investigation into school administration', 'a country reversing an internet shutdown after international criticism over restricted access to information'],
        'contexts': ['the balance between free expression and harm prevention is widely debated', 'legal protections for speech differ significantly between political systems', 'social media has raised new and unresolved questions about content moderation', 'public trust in institutions is closely tied to how openly they can be criticised', 'the line between legitimate regulation and censorship remains a source of ongoing dispute', 'legal protections for whistleblowers vary considerably between countries', 'the rise of online platforms has created entirely new categories of speech-related dispute'],
        'vocabulary': ['freedom of expression', 'press freedom', 'content moderation', 'public accountability', 'misinformation', 'civil liberties', 'democratic participation', 'legal protection', 'platform accountability'],
    },
    'nutrition_and_public_health': {
        'keywords': {'obesity', 'malnutrition', 'sugar', 'processed', 'nutrition', 'diet', 'calories', 'junk', 'food', 'healthy', 'unhealthy', 'vitamins', 'deficiency', 'overweight', 'sugary', 'snacks', 'labelling', 'portion'},
        'nouns': ['public health officials', 'schools', 'food companies', 'families', 'consumers', 'healthcare providers'],
        'benefits': ['reduce rates of diet-related illness across the population', 'lower long-term healthcare costs linked to poor nutrition', 'give people clearer information to make informed food choices', 'improve health outcomes for children from an early age', 'encourage food companies to reformulate products more healthily', 'reduce health inequalities linked to food access', 'support longer, healthier lives across the population', 'reduce long-term strain on already stretched healthcare systems'],
        'drawbacks': ['be resisted by industries whose products are targeted', 'disproportionately affect lower-income consumers if not carefully designed', 'be difficult to enforce consistently across a large food industry', 'take years to produce measurable improvements in public health', 'require sustained public education to be genuinely effective', 'be undermined by aggressive marketing of unhealthy products', 'face pushback framed as excessive government interference', 'be undermined by limited access to fresh food in some areas'],
        'examples': ['a country introducing a tax on sugary drinks that reduced consumption significantly', 'a school redesigning its lunch programme around fresh, unprocessed food', 'a public health campaign that measurably improved awareness of nutrition labels', 'a food company reformulating a popular product to reduce added sugar', 'a city expanding access to fresh food in areas previously without it', 'a school banning vending machine sales of sugary drinks and reporting improved student concentration', 'a low-income neighbourhood gaining its first full grocery store after years without fresh food access'],
        'contexts': ['rates of diet-related illness have risen substantially in many countries', 'public health policy in this area is often politically contested', 'access to healthy, affordable food varies considerably by income and location', 'the food industry\'s role in shaping public health outcomes remains widely debated', 'evidence on the most effective interventions continues to evolve', 'food deserts remain common in both rural areas and lower-income urban neighbourhoods', 'public health campaigns often struggle to compete with well-funded advertising for unhealthy products'],
        'vocabulary': ['public health policy', 'nutrition labelling', 'diet-related illness', 'food access', 'health inequality', 'preventive healthcare', 'consumer education', 'industry regulation', 'food desert'],
    },
    'city_vs_rural_life': {
        'keywords': {'countryside', 'village', 'rural', 'metropolitan', 'urbanite', 'commuter belt', 'village life', 'city life', 'rural life', 'quiet life', 'slow-paced', 'small town'},
        'nouns': ['city dwellers', 'rural residents', 'commuters', 'young families', 'retirees', 'small-town communities'],
        'benefits': ['offer a wider range of job opportunities close to home', 'give residents a stronger sense of community and familiarity', 'provide a slower, less stressful pace of daily life', 'put entertainment, culture, and services within easy reach', 'lower everyday living costs compared with major cities', 'offer cleaner air and easier access to green, open space', 'make it easier to build long-term relationships with neighbours', 'reduce daily commuting time for people who live close to work'],
        'drawbacks': ['make housing significantly more expensive relative to income', 'leave residents with fewer job options within easy reach', 'increase daily exposure to noise, crowding, and traffic', 'limit access to specialist healthcare, education, or public transport', 'contribute to feelings of isolation despite being surrounded by people', 'make it harder to maintain close-knit community ties', 'reduce opportunities for career progression outside of a few industries', 'make everyday errands and appointments take considerably longer'],
        'examples': ['a young professional moving to the capital for a job and adjusting to a much higher cost of living', 'a family relocating to a small town and reporting a noticeably calmer daily routine', 'a remote worker splitting time between a city apartment and a countryside cottage', 'a retiree moving away from a city and finding a stronger sense of community in a village', 'a graduate choosing a rural teaching post over a competitive city role for a better work-life balance', 'a couple leaving a crowded city neighbourhood after struggling to afford a larger home there', 'a small town losing younger residents to nearby cities in search of broader career options'],
        'contexts': ['migration between cities and smaller towns continues to shift with housing costs and remote-work opportunities', 'public services and transport links are typically far more developed in large cities than in the countryside', 'quality-of-life surveys often show different priorities between urban and rural residents', 'the rise of remote work has allowed some people to move away from cities without changing employer', 'younger generations are more likely to move to cities for education and early career opportunities', 'many rural communities have struggled with population decline as opportunities concentrate in larger cities', 'the choice between city and rural living increasingly depends on whether a job can be done remotely'],
        'vocabulary': ['quality of life', 'cost of living', 'community ties', 'work-life balance', 'population decline', 'urban-rural divide', 'commuter lifestyle', 'sense of belonging', 'access to services'],
    },
    'studying_abroad': {
        'keywords': {'abroad', 'exchange', 'overseas', 'homesick', 'homesickness', 'study abroad', 'exchange programme', 'exchange program', 'foreign university', 'host country', 'international student', 'host family'},
        'nouns': ['international students', 'exchange students', 'host universities', 'home universities', 'host families', 'study-abroad advisors'],
        'benefits': ['expose students to new cultures and ways of thinking', 'improve foreign-language fluency far faster than classroom study alone', 'build an international network of contacts and friendships', 'make a graduate\'s CV stand out to future employers', 'develop independence and practical problem-solving skills', 'open doors to postgraduate study or work in another country', 'broaden a student\'s understanding of global issues', 'strengthen adaptability and cross-cultural communication skills'],
        'drawbacks': ['be prohibitively expensive for many families', 'leave students dealing with homesickness and culture shock', 'create academic setbacks if credits do not transfer smoothly', 'expose students to unfamiliar risks without a familiar support network', 'be difficult to combine with part-time work students rely on at home', 'require navigating unfamiliar visa and healthcare systems', 'disrupt existing friendships and support networks back home', 'leave some students isolated if language barriers are significant'],
        'examples': ['a student spending a semester in another country and returning noticeably more confident and independent', 'an exchange student struggling with homesickness in the first few weeks before settling in', 'a graduate crediting a study-abroad year with landing a competitive international job offer', 'a university partnering with an overseas institution to offer a dual-degree programme', 'a student choosing a shorter summer exchange instead of a full year for financial reasons', 'a host family helping an international student adjust to unfamiliar customs and daily routines', 'a student discovering that credits from an overseas semester did not fully transfer toward their home degree'],
        'contexts': ['universities increasingly promote exchange partnerships as a way to attract prospective students', 'the cost of studying abroad varies enormously depending on the destination and funding available', 'scholarships and grants for international study remain limited relative to demand', 'many employers now view international experience as a meaningful advantage in graduates', 'visa and immigration policies can change the practical difficulty of studying in a given country from year to year', 'universities differ widely in how smoothly they recognise credits earned during an exchange', 'reliance on online learning during global disruptions temporarily reduced opportunities for physical exchange programmes'],
        'vocabulary': ['cultural immersion', 'academic credit transfer', 'culture shock', 'cross-cultural competence', 'exchange partnership', 'international employability', 'homesickness', 'host institution', 'global outlook'],
    },
    'cashless_society': {
        'keywords': {'cashless', 'contactless', 'payment', 'payments', 'wallet', 'ewallet', 'banknote', 'banknotes', 'coins', 'card', 'cards', 'fintech'},
        'nouns': ['consumers', 'small businesses', 'banks', 'elderly residents', 'retailers', 'central banks'],
        'benefits': ['make everyday transactions faster and more convenient', 'reduce the costs businesses face handling physical cash', 'make it easier to track spending and manage a household budget', 'reduce opportunities for cash-based tax evasion and money laundering', 'lower the risk of theft associated with carrying physical cash', 'speed up checkout times in shops and public transport', 'make cross-border and online payments considerably simpler', 'support more efficient record-keeping for small businesses'],
        'drawbacks': ['exclude people without reliable access to banking or smartphones', 'leave payment systems vulnerable to outages and technical failures', 'raise serious concerns about financial surveillance and data privacy', 'disadvantage elderly or vulnerable people less comfortable with digital tools', 'make it harder to budget for people prone to impulsive spending', 'concentrate significant power in the hands of a few payment providers', 'leave small, informal businesses struggling to adapt quickly', 'reduce financial privacy compared with anonymous cash transactions'],
        'examples': ['a country piloting a near-fully cashless payment system in its capital city', 'an elderly customer struggling to pay for groceries after a local bank branch closed', 'a small market stall losing customers after removing its only card reader during an outage', 'a city bus network switching entirely to contactless payment and speeding up boarding times', 'a bank introducing a simplified mobile app specifically to help older customers adapt', 'a country experiencing a nationwide card-payment outage that temporarily left shoppers unable to pay for anything', 'a low-income neighbourhood losing access to convenient cash withdrawal points as local bank branches closed'],
        'contexts': ['central banks in several countries are actively researching official digital currencies partly in response to this shift', 'rates of cash use continue to fall fastest among younger, urban populations', 'small businesses in some regions have pushed back against losing the option to accept cash', 'concerns about financial exclusion have led some governments to guarantee a minimum right to pay with cash', 'payment technology continues to evolve faster than the regulation designed to oversee it', 'rural and lower-income communities are often the last to gain reliable access to fast, affordable digital payment infrastructure', 'debate continues over how much commercial payment providers should be allowed to know about individual spending habits'],
        'vocabulary': ['financial inclusion', 'digital payment infrastructure', 'contactless technology', 'financial surveillance', 'transaction data', 'payment outage', 'central bank digital currency', 'cash dependency', 'digital divide'],
    },
}

GENERIC_FAMILY = {
    'nouns': ['individuals', 'communities', 'organisations', 'policymakers', 'society as a whole'],
    'benefits': ['produce clear practical benefits', 'save valuable time and resources', 'improve outcomes for the people involved', 'create new opportunities', 'address a genuine and growing need', 'strengthen long-term resilience', 'encourage more efficient use of resources'],
    'drawbacks': ['bring some notable drawbacks', 'be difficult to implement fairly', 'require careful long-term planning', 'not suit every situation equally', 'take time before real benefits appear', 'depend heavily on adequate funding', 'create unintended consequences if poorly managed'],
    'examples': ['a well-documented case where careful planning led to a clearly positive outcome', 'an organisation that adjusted its approach after early feedback and saw better results', 'a community that benefited noticeably once the right support was put in place', 'a project that scaled successfully after a carefully managed pilot phase', 'a group that revised its original plan after identifying a practical obstacle early on'],
    'contexts': ['different groups have approached this issue in noticeably different ways', 'opinions on this subject continue to shift as new evidence and experience accumulate', 'the right approach often depends heavily on the specific circumstances involved', 'available resources and local priorities strongly influence how this is handled', 'long-term outcomes are often harder to judge than early impressions suggest'],
    'vocabulary': ['practical outcomes', 'long-term planning', 'stakeholder involvement', 'measurable impact', 'resource allocation', 'sustainable approach', 'community benefit', 'balanced judgement'],
}

HEDGES = ['can', 'may', 'is likely to', 'can often', 'in many cases can']

# TRANSITIONS in writing_coach.py mixes true sentence-linking adverbs
# ("however", "furthermore") with subordinating conjunctions ("because",
# "while", "first") that are grammatical mid-clause but not as a
# standalone "Connector, ..." sentence opener. Keep our own filtered pool
# per level so every generated connector sentence is grammatical.
SAFE_CONNECTORS = {
    'A1': ['Also', 'And', 'So'],
    'A2': ['Also', 'However', 'For example'],
    'B1': ['However', 'Therefore', 'In addition', 'As a result', 'For example'],
    'B2': ['Furthermore', 'In addition', 'As a result', 'Nevertheless', 'For instance'],
    'C1': ['Moreover', 'Conversely', 'Consequently', 'By contrast', 'In light of this'],
    'C2': ['Nevertheless', 'Accordingly', 'Conversely', 'By the same token', 'Notwithstanding this'],
}
OPENERS_INTRO = [
    "In recent years, {topic_phrase} has become an increasingly debated issue.",
    "{topic_phrase} is a subject that continues to attract widespread attention and disagreement.",
    "There is growing discussion around {topic_phrase} in modern society.",
    "{topic_phrase} has become a significant topic for {actor} in recent times.",
    "The question of {topic_phrase} is one that affects {actor} in different ways.",
]
OPENERS_BODY = [
    "One of the main reasons for this is that",
    "A further point worth considering is that",
    "It is also important to note that",
    "Another significant factor is that",
    "This can be explained by the fact that",
]


def _title_phrase(title, anchor_words=None):
    """Turn a raw title into a short lowercase noun-ish phrase for reuse in
    generated sentences, e.g. "The impact of technology on education" ->
    "the impact of technology on education" (used as-is, it's already a
    noun phrase). Falls back to a safe generic phrase ("this policy" /
    "this practice" / "this topic") for titles phrased as a question or a
    full clause (e.g. "Should schools ban homework?", "Governments do more
    to protect the environment") — splicing those verb-bearing titles into
    a noun-phrase slot ("I believe that schools ban homework may...")
    produces ungrammatical sentences, so those are deliberately not spliced
    in and a generic noun phrase is used instead.

    `anchor_words` (optional, from _topic_anchor_words) lets that generic
    fallback still carry the title's specific content instead of being
    completely generic -- "this policy" becomes "this policy on
    single-use plastics" rather than losing "single-use plastics"
    entirely just because the title happened to be phrased as a
    question."""
    t = re.sub(r'[?!.]+$', '', title or '').strip()
    if not t:
        return "this topic"
    # Strip a leading essay-instruction imperative ("Discuss...", "Compare
    # and contrast...", "Explain...", "Analyse...") before anything else --
    # these are prompt framing, not part of the topic's own noun phrase,
    # and left in place they leak an ungrammatical bare verb into a
    # noun-phrase slot ("discuss the causes and effects of deforestation
    # is important" is not valid English).
    imperative_openers = (
        r'^(discuss|explain|describe|analyse|analyze|examine|explore|evaluate|assess|'
        r'outline|consider|compare and contrast|compare|contrast|argue|comment on|'
        r'write about|talk about)\s+(the\s+|whether\s+|how\s+|why\s+)?'
    )
    t = re.sub(imperative_openers, '', t, flags=re.I).strip()
    if not t:
        return "this topic"
    # Strip a leading "the advantages/benefits/drawbacks/pros and cons
    # (and disadvantages) of ..." framing down to just the actual subject
    # that follows "of". This framing describes the essay's STRUCTURE
    # (what kind of essay it is), not its subject matter, so repeating it
    # verbatim as a recurring sentence subject reads clumsily and
    # meta-textually ("...studying abroad carries both clear benefits and
    # notable costs" reading as "the benefits and drawbacks of studying
    # abroad carries..." is grammatically fine but stylistically poor --
    # a natural piece of writing would just say "studying abroad" once
    # the framing has done its job in the introduction).
    meta_framing = (
        r'^the\s+(advantages?\s+and\s+disadvantages?|benefits?\s+and\s+(drawbacks?|costs?|risks?)|'
        r'pros?\s+and\s+cons?|causes?\s+and\s+effects?|rise\s+and\s+fall)\s+of\s+'
    )
    t_after_meta = re.sub(meta_framing, '', t, flags=re.I).strip()
    if t_after_meta and t_after_meta != t:
        t = t_after_meta
    if not t:
        return "this topic"
    is_question = bool(re.match(r'^(should|do|does|is|are|can|will|why|how|what)\b', t, flags=re.I))
    # A body of text still reads as a clause (subject + finite verb) rather
    # than a noun phrase if, after the leading question/aux word and any
    # article, the next content word is a common finite verb form. This is
    # a lightweight heuristic (no POS tagger available offline) but catches
    # the two failure patterns seen in testing: "schools ban homework" and
    # "governments do more to protect the environment".
    rest = t
    if is_question:
        rest = re.sub(r'^(should|do|does|is|are|can|will|why|how|what)\s+', '', t, flags=re.I)
        rest = re.sub(r'^(is|are|does|do|can|will)\s+', '', rest, flags=re.I)
    words_in_rest = rest.split()
    finite_verbs = {'ban', 'do', 'does', 'make', 'help', 'protect', 'improve', 'reduce', 'increase',
                    'stop', 'allow', 'require', 'need', 'affect', 'cause', 'solve', 'change', 'support',
                    'harm', 'benefit', 'damage', 'encourage', 'discourage', 'limit', 'promote'}
    has_finite_verb = any(w.lower().rstrip('.,') in finite_verbs for w in words_in_rest[1:3])
    # NOTE: a long title is not automatically a clause -- "the causes and
    # effects of deforestation in the Amazon rainforest" is a perfectly
    # good long noun phrase, not a clause, so title length alone must
    # never trigger the generic fallback. Only genuine question-openers
    # or a detected finite verb should.
    looks_like_clause = is_question or has_finite_verb
    if looks_like_clause:
        policy_signal_words = {'ban', 'law', 'policy', 'government', 'governments', 'should', 'regulate', 'tax'}
        low_title = t.lower()
        head = "this policy" if any(w in low_title.split() for w in policy_signal_words) else "this topic"
        if anchor_words:
            joined = ', '.join(anchor_words[:-1]) + ' and ' + anchor_words[-1] if len(anchor_words) > 1 else anchor_words[0]
            # "involving" reads naturally whether the anchor words are
            # nouns ("involving TikTok and teenage sleep") or a bare
            # adjective left over from a clause like "Is social media
            # making us more isolated?" ("involving isolated" still
            # scans far better than "on isolated").
            return f"{head} involving {joined}"
        return head
    out = t[0].lower() + t[1:] if t else t
    return out or "this topic"


def _simple_stem(word):
    """Very small, conservative singular/plural normaliser used only for
    matching a title's words against a family's keyword list -- NOT a
    general-purpose stemmer, and deliberately does not touch verb tenses
    or derivational endings, to avoid collapsing genuinely different
    words together (e.g. "state" and "statement" must stay distinct).

    Without this, "athletes" (title) never matched the sports family's
    keyword "athlete" (singular only), and "exams" never matched
    education's "exam" -- normalize_topic() does no stemming at all, so
    a title using the plural form of almost any keyword silently failed
    to match. Rather than hand-adding every plural form to every
    family's keyword set (fragile, and every future family addition
    would need the same treatment), both sides of the comparison are
    passed through this same conservative singularisation."""
    if len(word) <= 3:
        return word
    if word.endswith('ies') and len(word) > 4:
        return word[:-3] + 'y'
    if word.endswith(('sses', 'shes', 'ches', 'xes')):
        return word[:-2]
    if word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
        return word[:-1]
    return word


def _stemmed_keyword_index(family):
    """Build (and cache on the family dict itself) a lookup from stemmed
    keyword -> original keyword, so family-matching can compare stemmed
    forms without repeatedly recomputing this for every call. Only
    single-word keywords go through this path -- multi-word keyword
    phrases (e.g. "peer pressure", "study abroad") are handled separately
    in _detect_family via substring matching against the raw title, since
    normalize_topic() only ever produces single-word tokens and so could
    never match a multi-word keyword here in the first place (a
    previously silent bug affecting every family with a multi-word
    keyword: libraries, youth, language, gender_equality, volunteering,
    mental_health, social_inequality, and both new families added below)."""
    cache = family.get('_stemmed_keywords_cache')
    if cache is not None:
        return cache
    index = {}
    for kw in family.get('keywords', ()):
        if ' ' in kw:
            continue
        index[_simple_stem(kw)] = kw
    family['_stemmed_keywords_cache'] = index
    return index


def _multiword_keywords(family):
    """Return this family's multi-word keyword phrases (cached), for
    substring matching against the raw title -- see _stemmed_keyword_index
    docstring for why these can't go through the single-token stem index."""
    cache = family.get('_multiword_keywords_cache')
    if cache is not None:
        return cache
    phrases = [kw for kw in family.get('keywords', ()) if ' ' in kw]
    family['_multiword_keywords_cache'] = phrases
    return phrases


def _detect_family(title):
    tw = normalize_topic(title or '')
    low_title = f" {(title or '').lower()} "
    # Score each family not just by how many keywords overlap, but by how
    # *specific* those overlapping keywords are: a keyword that appears in
    # only one family's list (e.g. "immigration") is a much stronger signal
    # than one shared by several families (e.g. "public", which appears in
    # government, libraries and democracy). Without this, a tie between a
    # generic shared word and a specific unique one would be broken purely
    # by dict declaration order, regardless of relevance. Weighting by
    # inverse document frequency (1 / how many families use that keyword)
    # makes the more specific, topic-defining word decide, and a secondary
    # tie-break on keyword length favours the more specific word when two
    # families still score exactly equal (e.g. a title genuinely straddling
    # two legitimate topics).
    #
    # Matching is done on STEMMED forms (see _simple_stem) so that a title
    # using the plural of a keyword ("athletes", "exams") still matches a
    # family whose keyword list only has the singular ("athlete", "exam"),
    # and vice versa -- previously this was a silent, systemic mismatch
    # across every family in the database.
    #
    # A handful of keywords are themselves generic essay-question
    # scaffolding ("government", "state", "public", "law", "tax",
    # "policy", "regulation", "citizen", "politics") that appear in almost
    # any "Should the government do X?" style title regardless of the
    # essay's actual subject. Left at full weight, one of these could tie
    # or beat a genuinely specific, topical word from a DIFFERENT family
    # purely because it happens to be a longer string (e.g. "government"
    # outscoring "plastic" for "Should governments ban single-use
    # plastics?", even though the essay is about plastics, not
    # government in general). These still count toward matching the
    # government family itself (a title that is genuinely ABOUT
    # government, with no other specific subject, should still match
    # it) -- they are only discounted so they can't drown out a more
    # specific word from a different family.
    _GENERIC_SCAFFOLD_STEMS = {
        'government', 'state', 'public', 'law', 'tax', 'policy',
        'regulation', 'citizen', 'politic', 'should',
    }
    tw_stemmed = {_simple_stem(w): w for w in tw}
    keyword_family_count = {}
    for data in TOPIC_FAMILIES.values():
        for stem in _stemmed_keyword_index(data):
            keyword_family_count[stem] = keyword_family_count.get(stem, 0) + 1
        for phrase in _multiword_keywords(data):
            keyword_family_count[phrase] = keyword_family_count.get(phrase, 0) + 1

    best, best_score, best_specificity = None, 0.0, 0
    for name, data in TOPIC_FAMILIES.items():
        stem_index = _stemmed_keyword_index(data)
        overlap = set(tw_stemmed) & set(stem_index)
        score = 0.0
        specificity = 0
        for stem in overlap:
            weight = 1.0 / keyword_family_count[stem]
            if stem in _GENERIC_SCAFFOLD_STEMS:
                weight *= 0.2  # still counts, but can't out-rank a specific word from another family
            else:
                specificity = max(specificity, len(stem_index[stem]))
            score += weight
        # A literal multi-word phrase appearing in the title (e.g. "study
        # abroad", "peer pressure") is an unambiguous, highly specific
        # signal -- weighted at least as strongly as the longest possible
        # single-word match, so a family whose defining content is a
        # phrase isn't out-scored by an unrelated family that happens to
        # share one shorter single word with the title.
        for phrase in _multiword_keywords(data):
            # Match the phrase allowing its LAST word to appear in either
            # singular or plural form (the far more common source of a
            # missed match than any earlier word in the phrase) -- e.g.
            # the keyword "single-use plastic" should still match a title
            # containing "single-use plastics", and "plastic bag" should
            # match "plastic bags". A plain literal substring check (the
            # previous behaviour) silently missed this for every
            # multi-word keyword in every family whenever the title used
            # the other number.
            pattern = re.escape(phrase) + r's?\b'
            if re.search(r'(?<!\w)' + pattern, low_title):
                score += 1.0 / keyword_family_count[phrase]
                specificity = max(specificity, len(phrase) + 10)
        if score <= 0:
            continue
        if score > best_score or (score == best_score and specificity > best_specificity):
            best, best_score, best_specificity = name, score, specificity
    return TOPIC_FAMILIES[best] if best else GENERIC_FAMILY


# Small set of very generic essay-instruction words that occasionally end
# up inside a title (from prompts like "Discuss the topic of X" or "Write
# about X") but are never themselves part of what the essay is actually
# about, so they must never be treated as topic-defining anchor words.
# Also excludes generic "essay-about-an-essay" nouns (impact, effect,
# role, influence, importance...) that describe the *shape* of the
# question rather than its actual subject matter -- "the impact of X on
# Y" is about X and Y, not about the word "impact" itself -- a few
# generic nouns ("patterns", "issues", "aspects") that almost never carry
# a title's real specificity on their own, and the generic actors/verbs
# that make up a policy-question's *shape* rather than its subject (e.g.
# "Should governments ban X?" is about X, not about "governments" or
# "ban", which are near-identical in almost every policy-question title).
_ANCHOR_STOPWORDS = {
    'discuss', 'write', 'essay', 'topic', 'about', 'explain', 'describe',
    'analyse', 'analyze', 'argue', 'consider', 'give', 'your', 'opinion',
    'opinions', 'views', 'view', 'compare', 'contrast', 'advantages',
    'disadvantages', 'benefits', 'drawbacks', 'both', 'sides', 'reasons',
    'causes', 'effects', 'solutions', 'problem', 'problems',
    'impact', 'impacts', 'effect', 'role', 'influence', 'importance',
    'significance', 'relationship', 'connection', 'link', 'links',
    'affect', 'affects', 'affecting', 'relating', 'related', 'regarding',
    'pattern', 'patterns', 'issue', 'issues', 'aspect', 'aspects',
    'factor', 'factors', 'matter', 'matters',
    'should', 'government', 'governments', 'ban', 'banned', 'law', 'laws',
    'allow', 'allowed', 'require', 'required', 'need', 'needed',
    'people', 'society', 'country', 'countries', 'world', 'today',
    # normalize_topic()'s own stopword list (writing_coach.py) is a
    # general-purpose relevance-scoring filter and doesn't catch every
    # function word that can slip through into a title (how/why/what,
    # among/within/without, does/do/did as auxiliaries) -- those are
    # harmless for relevance scoring but make poor anchor words, since
    # they never carry a title's actual specificity.
    'how', 'why', 'what', 'when', 'where', 'who', 'which',
    'among', 'within', 'without', 'against', 'through', 'towards', 'toward',
    'new', 'old', 'many', 'much', 'more', 'less', 'good', 'bad',
    'making', 'make', 'makes', 'getting', 'get', 'gets', 'having', 'have',
    'being', 'doing', 'going', 'become', 'becoming', 'becomes',
    # Past-participle/passive-voice verb forms that commonly appear in
    # policy-question titles ("Should X be replaced/banned/regulated/
    # introduced...?") describing the ACTION being proposed, not the
    # topic's actual subject matter -- "Should exams be replaced with
    # continuous assessment?" is about exams and continuous assessment,
    # not about the word "replaced". Plus a few generic evaluative nouns
    # ("waste", "value", "worth") that, like "impact"/"issue" above,
    # describe a judgement about the topic rather than the topic itself
    # -- "a waste of money" is a fixed idiom, and splitting it into
    # separate anchor words ("waste" + "money") distorts its meaning.
    'replaced', 'replace', 'replacing', 'introduced', 'introduce',
    'regulated', 'regulate', 'removed', 'remove', 'removing',
    'increased', 'decreased', 'reduced', 'improved', 'implemented',
    'lowered', 'raised', 'extended', 'restricted', 'expanded',
    'waste', 'wasted', 'worth', 'value', 'valuable', 'worthwhile',
    # Closed-class comparative/linking/light words that keep surfacing as
    # false anchor words across many different titles ("Is it better to
    # live in a big family...", "How does peer pressure affect teenagers
    # IN school", "the gap BETWEEN rich and poor", "MOVE entirely
    # online"): these are structural connective tissue of a sentence, not
    # content words, in essentially every title they appear in. Grouped
    # by function so future additions are easy to place correctly.
    # -- comparatives / degree words:
    'better', 'worse', 'best', 'worst', 'bigger', 'smaller', 'biggest',
    'smallest', 'higher', 'lower', 'greater', 'fewer', 'least', 'most',
    'rather', 'quite', 'fairly', 'somewhat', 'entirely', 'completely',
    'fully', 'partly', 'partially', 'increasingly', 'largely', 'mostly',
    # -- light/generic verbs of movement, existence or possession that
    # rarely carry a title's real subject matter on their own:
    'live', 'lives', 'living', 'lived', 'move', 'moves', 'moved', 'moving',
    'come', 'comes', 'came', 'coming', 'go', 'goes', 'went', 'take',
    'takes', 'took', 'taking', 'put', 'puts', 'putting', 'exist', 'exists',
    'remain', 'remains', 'stay', 'stays', 'seem', 'seems', 'seemed',
    'appear', 'appears', 'appeared', 'tend', 'tends', 'tended',
    # -- prepositions that occasionally survive normalize_topic()'s own
    # filtering (its stopword list is scoring-focused, not exhaustive):
    'between', 'across', 'around', 'behind', 'beyond', 'inside',
    'outside', 'under', 'over', 'above', 'below', 'during', 'before',
    'after', 'since', 'until', 'upon', 'onto', 'into', 'per',
}


def _topic_anchor_words(title, family):
    """Return the specific words from the user's own title that make it
    distinct — this is what makes a generated essay/brainstorm about "the
    impact of TikTok on teenage sleep patterns" read as being about
    TikTok and teenage sleep specifically, rather than generic,
    interchangeable "social media" content that would fit almost any
    title matching that family.

    Family keyword matching alone only decides *which pool of generic
    content* to draw from; without this, every essay in a family sounds
    identical regardless of what the student actually typed. This
    function finds the words that make THIS title distinct, so they can
    be woven back into the generated sentences.

    A word from the matched family's own keyword list is normally
    excluded (it's already implied by the family's generic content, e.g.
    "school" for the education family), UNLESS it is a proper noun/named
    entity in the original title (capitalised mid-sentence, e.g.
    "TikTok", "Instagram") — those stay in even if they happen to also
    appear in a family's keyword list, because a named platform, place,
    or organisation is exactly the kind of specific detail that must not
    be silently dropped just because the family recognises the word.

    When there are more surviving candidates than the caller's word cap,
    proper nouns are kept first, then the longest remaining words --
    longer words are reliably more specific/topic-defining in practice
    ("plastics", "teenage") than short, common ones that happen to sit
    earlier in the sentence ("use", "new"), so ranking by length instead
    of by raw title-order position keeps the *most* distinctive words
    rather than just the first few.
    """
    tw = normalize_topic(title or '')
    family_kw = family.get('keywords', set()) if isinstance(family, dict) else set()
    # Exclude a title word if it (or its stem) matches a family keyword
    # (or the family keyword's stem) -- not just an exact string match.
    # Without this, a plural topic word like "athletes" would survive as
    # a supposedly "distinctive" anchor word even for the sports family,
    # whose keyword list only has the singular "athlete"; the word is
    # already implied by the family's generic content either way, so it
    # should be excluded from the anchor set exactly like the singular
    # form is.
    family_kw_stems = {_simple_stem(kw) for kw in family_kw}
    family_kw = family_kw | {w for w in tw if _simple_stem(w) in family_kw_stems}
    # Use the exact same word-splitting regex as normalize_topic()/words()
    # (writing_coach.py) here, rather than a hyphen-preserving variant --
    # using two different tokenizers on the same title caused compound
    # words like "single-use" to split inconsistently between the two
    # (kept whole here, split into "single"/"use" by normalize_topic），
    # leaving orphaned words with no recorded title position.
    title_words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", title or '')
    proper_nouns = {w.lower() for i, w in enumerate(title_words) if i > 0 and w[:1].isupper()}
    specific = (tw - family_kw - _ANCHOR_STOPWORDS) | (tw & proper_nouns)
    if not specific:
        return []
    # Record EVERY occurrence of each specific word (position, lowercase,
    # display form), not just the first -- a repeated word ("city life
    # and rural life") must still be able to merge into its own adjacent
    # compound ("rural life") at its second occurrence, which a
    # first-occurrence-only position map would miss entirely.
    occurrences = [(i, w.lower(), w) for i, w in enumerate(title_words) if w.lower() in specific]

    # Drop an INDIVIDUAL occurrence of a surviving word if, at that
    # specific position in the title, it sits immediately next to a word
    # that was excluded for being a family keyword (not a stopword) --
    # that adjacency is strong evidence this particular occurrence
    # originally formed one meaningful compound with its neighbour (e.g.
    # "studying" + "abroad" in a title matched to the studying_abroad
    # family, whose keyword list already covers "abroad"). This is
    # applied per OCCURRENCE, not by removing the word globally, because
    # a repeated word can have one occurrence that still forms a valid
    # surviving compound and another that doesn't -- e.g. in "city life
    # and rural life" (matched to city_vs_rural_life, which lists
    # "rural" as a keyword), the first "life" correctly stays paired with
    # "city" as "city life", while only the second "life" (next to the
    # now-excluded "rural") should be dropped; removing "life" from the
    # global candidate set would have destroyed the first, valid pairing
    # too. Proper nouns are exempt, since a named entity is never "just
    # half of a compound" in this sense (e.g. "TikTok" must survive even
    # next to an excluded family keyword like "social").
    family_kw_only = family_kw - _ANCHOR_STOPWORDS  # words excluded specifically as family keywords
    filtered_occurrences = []
    for i, lw, disp in occurrences:
        if lw in proper_nouns:
            filtered_occurrences.append((i, lw, disp))
            continue
        prev_w = title_words[i - 1].lower() if i > 0 else None
        next_w = title_words[i + 1].lower() if i + 1 < len(title_words) else None
        # Only consider a neighbour that was itself a genuine topic-word
        # candidate before family/stopword filtering (i.e. it appears in
        # tw, the full normalised token set) -- a neighbour like "of" or
        # "the" was never a candidate word at all (it's filtered out by
        # normalize_topic()'s own stopword list well before this
        # function runs), so its presence next to "studying" in "...of
        # studying abroad" says nothing about whether "studying" was
        # "half of a compound"; only "abroad" (itself a real candidate
        # word that got excluded as a family keyword) is meaningful
        # evidence here.
        relevant_neighbours = [n for n in (prev_w, next_w) if n in tw]
        if relevant_neighbours and all(n in family_kw_only for n in relevant_neighbours):
            continue
        filtered_occurrences.append((i, lw, disp))
    occurrences = filtered_occurrences
    if not occurrences:
        return []

    # Merge runs of consecutive selected words (by actual title position,
    # using every occurrence so a repeated word can still merge into a
    # fresh compound at each of its positions) into single multi-word
    # units BEFORE ranking/capping, e.g. "single" + "use" adjacent in the
    # title become one unit "single use" instead of being ranked and
    # possibly capped independently -- this both reads more naturally and
    # avoids one half of a compound term surviving the word cap while the
    # other half is cut.
    units = []  # list of (dedupe_key, display_text, min_position, contains_proper_noun)
    run = []
    prev_pos = None
    def _flush(run):
        if not run:
            return
        lws = [lw for _, lw, _ in run]
        forms = [disp for _, _, disp in run]
        units.append((
            ' '.join(lws),
            ' '.join(forms),
            run[0][0],
            any(lw in proper_nouns for lw in lws),
        ))
    for pos, lw, disp in occurrences:
        if prev_pos is not None and pos == prev_pos + 1:
            run.append((pos, lw, disp))
        else:
            _flush(run)
            run = [(pos, lw, disp)]
        prev_pos = pos
    _flush(run)

    # A compound unit might appear more than once verbatim (e.g. if the
    # same two-word phrase occurred twice) -- dedupe by its lowercase key,
    # keeping the earliest position.
    seen_keys = set()
    deduped = []
    for key, display, pos, is_proper in units:
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append((key, display, pos, is_proper))

    # Drop any single-word unit whose word is ALSO a component of some
    # other, longer unit -- e.g. for "city life and rural life", "life"
    # merges with "city" at its first occurrence ("city life") but its
    # second occurrence has no surviving neighbour once "rural" is
    # excluded as a family keyword, leaving an orphaned bare "life" unit
    # that duplicates a word already present in "city life". Keeping both
    # produced an ugly, repetitive anchor phrase ("this issue involving
    # city life and life"); dropping the orphan leaves the clean,
    # non-redundant "city life" alone.
    multiword_component_words = {
        w for key, _, _, _ in deduped if ' ' in key for w in key.split()
    }
    deduped = [
        (key, display, pos, is_proper) for key, display, pos, is_proper in deduped
        if ' ' in key or key not in multiword_component_words
    ]

    ranked = sorted(deduped, key=lambda u: (not u[3], -len(u[0]), u[2]))
    top = ranked[:5]  # a handful is plenty; more would feel like keyword-stuffing
    # Re-order the selected units back into their original title order
    # (reads more naturally than length-descending order in a sentence).
    top.sort(key=lambda u: u[2])
    return [display for _, display, _, _ in top]


def _topic_anchor_phrase(title, family, max_words=3):
    """Build a short, grammatical noun phrase that keeps the user's own
    specific topic words visible wherever a generated sentence would
    otherwise use the bare, generic pronoun "it" -- e.g. for the title
    "the impact of TikTok on teenage sleep patterns" this returns
    something like "this issue with TikTok and teenage sleep", which
    slots correctly into "{ref} can reduce face-to-face interaction" as
    "this issue with TikTok and teenage sleep can reduce face-to-face
    interaction."

    Earlier iteration bug (fixed here): simply joining the bare anchor
    words ("TikTok, sleep and teenage") and dropping that straight into a
    subject slot produced ungrammatical output like "TikTok, sleep and
    teenage can give...". A list of nouns is not itself a noun phrase
    that can stand as the subject of "can {verb}" -- it needs its own
    head noun. Wrapping the words in "this issue with ..." (or "this
    approach to ..." for a policy-flavoured topic) gives them a proper
    grammatical anchor while still keeping the user's specific wording
    front and centre in the sentence, which is the actual goal.

    Returns '' if the title has no words beyond its matched family's own
    generic keywords (a genuinely generic title like plain "Technology",
    where there is nothing more specific to anchor to) — callers must
    handle the empty case by falling back to the existing generic "it"
    rather than producing an awkward sentence."""
    words = _topic_anchor_words(title, family)[:max_words]
    if not words:
        return ''
    if len(words) == 1:
        joined = words[0]
    else:
        joined = ', '.join(words[:-1]) + ' and ' + words[-1]
    low_title = (title or '').lower()
    policy_signal_words = {'ban', 'law', 'policy', 'government', 'governments', 'regulate', 'tax'}
    # "involving" (like in _title_phrase above) reads naturally whether
    # the anchor words are plain nouns ("involving TikTok and teenage
    # sleep") or a bare adjective/participle left over from a title with
    # no other distinctive noun ("involving isolated") -- "this issue
    # with isolated" does not.
    head = 'this policy involving' if any(w in low_title.split() for w in policy_signal_words) else 'this issue involving'
    return f"{head} {joined}"



def _pick(seq, rng, k=None):
    if k is None:
        return rng.choice(seq)
    return rng.sample(seq, min(k, len(seq)))


def _connectors(level, rng, kind='mid'):
    pool = SAFE_CONNECTORS.get(level, SAFE_CONNECTORS['B2'])
    return rng.choice(pool)


def _conclusion_opener(level, rng):
    pool = CONCLUSION_LINKS.get(level, CONCLUSION_LINKS['B2'])
    return rng.choice(pool)


def _build_intro(title, essay_type, family, level, rng, actor, has_position):
    topic_phrase = _title_phrase(title)
    frame_by_type = {
        'general': [
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} is a subject that is well worth exploring in some detail.",
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} touches on several interesting aspects that are worth setting out in turn.",
        ],
        'opinion': [
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} is a subject that continues to attract considerable attention, and views on it differ widely.",
            f"Few issues affecting {actor} generate as much discussion as {topic_phrase}.",
        ],
        'discussion': [
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} is widely discussed, and reasonable people hold quite different views on it.",
            f"Opinions on {topic_phrase} tend to be sharply divided, with valid points raised on more than one side.",
        ],
        'advantages_disadvantages': [
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} has become increasingly common, bringing with it a mixture of benefits and drawbacks.",
            f"Like many developments that affect {actor}, {topic_phrase} carries both clear benefits and notable costs.",
        ],
        'problem_solution': [
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} has become a persistent difficulty for {actor} in recent years.",
            f"Few problems affecting {actor} have proved as stubborn as {topic_phrase}.",
        ],
        'two_part': [
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} raises two distinct questions that are worth considering in turn.",
            f"When people discuss {topic_phrase}, they are usually really asking about two separate things.",
        ],
        'cause_effect': [
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} has emerged gradually, driven by a number of related factors, and its consequences are now becoming clear.",
            f"Several interconnected forces lie behind {topic_phrase}, and its effects are increasingly visible in the lives of {actor}.",
        ],
        'positive_negative': [
            f"{topic_phrase[0].upper()}{topic_phrase[1:]} is a development that has changed the way {actor} live and work.",
            f"Like most significant changes affecting {actor}, {topic_phrase} has brought both welcome and unwelcome effects.",
        ],
    }
    stance_by_type = {
        'general': [
            f"The following paragraphs look at some of its most notable aspects in turn.",
            f"This essay sets out its main features one by one, building up a fuller picture.",
        ],
        'opinion': [
            f"In my view, it is, on balance, a positive development, although it is not without genuine concerns.",
            f"I would argue that its benefits outweigh its drawbacks, provided it is approached carefully.",
        ],
        'discussion': [
            f"This essay will consider the strongest arguments on each side before reaching a balanced conclusion.",
            f"Both perspectives deserve serious consideration before a fair judgement can be reached.",
        ],
        'advantages_disadvantages': [
            f"On the whole, the advantages appear to outweigh the disadvantages, though both deserve close attention.",
            f"Weighing the two sides fairly suggests that its overall impact is a positive one.",
        ],
        'problem_solution': [
            f"Understanding why it has arisen is the first step towards addressing it effectively.",
            f"A combination of realistic measures could go a long way towards resolving it.",
        ],
        'two_part': [
            f"Both parts of the question deserve a considered answer.",
            f"Taken together, the two questions reveal a more complete picture of the issue.",
        ],
        'cause_effect': [
            f"Understanding these causes helps explain why its effects have been so significant.",
            f"Its causes and its consequences are closely linked, and one cannot really be understood without the other.",
        ],
        'positive_negative': [
            f"On balance, it represents a largely positive development for {actor}, although its success depends on how well it is managed.",
            f"Whether it is ultimately positive or negative depends heavily on how carefully it is managed.",
        ],
    }
    context_by_type = {
        'general': [
            f"There are several angles from which {topic_phrase} can usefully be examined.",
            f"A closer look at {topic_phrase} reveals more depth than a first glance might suggest.",
        ],
        'opinion': [
            f"Supporters and critics of {topic_phrase} both raise points that deserve genuine consideration.",
            f"Before taking a firm position, it is worth examining what lies behind the debate over {topic_phrase}.",
        ],
        'discussion': [
            f"Those on either side of the debate over {topic_phrase} tend to draw on quite different priorities and evidence.",
            f"Examining {topic_phrase} from more than one angle helps explain why opinion remains so divided.",
        ],
        'advantages_disadvantages': [
            f"Understanding both sides of {topic_phrase} is essential before forming a balanced judgement.",
            f"The advantages of {topic_phrase} are often discussed, but its drawbacks deserve equal attention.",
        ],
        'problem_solution': [
            f"A number of factors have contributed to {topic_phrase}, and addressing them calls for a considered response.",
            f"Before turning to solutions, it is worth briefly outlining why {topic_phrase} has become so persistent.",
        ],
        'two_part': [
            f"Each part of this question calls for its own line of reasoning.",
            f"Treating the two elements of {topic_phrase} separately makes the overall picture easier to follow.",
        ],
        'cause_effect': [
            f"Tracing these factors back to their roots helps clarify why {topic_phrase} has unfolded as it has.",
            f"The relationship between cause and effect here is more complex than it might first appear.",
        ],
        'positive_negative': [
            f"Both the welcome and the unwelcome effects of {topic_phrase} are worth setting out clearly.",
            f"Weighing the positive effects of {topic_phrase} against the negative ones requires a fair-minded approach.",
        ],
    }
    frame = rng.choice(frame_by_type.get(essay_type, frame_by_type['opinion']))
    context = rng.choice(context_by_type.get(essay_type, context_by_type['opinion']))
    stance = rng.choice(stance_by_type.get(essay_type, stance_by_type['opinion']))
    return f"{frame} {context} {stance}"


def _vocab_sentence(family, rng, used_vocab, used_templates=None):
    """Return one natural sentence built around an unused topic-specific
    vocabulary/collocation term for this family, or None if the family has
    no vocabulary list, every term has already been used in this essay, or
    every template shape has already been used (so the same sentence
    pattern doesn't repeat several times in one essay even with different
    terms slotted in). `used_templates` is a set shared across the essay."""
    pool = family.get('vocabulary') or GENERIC_FAMILY.get('vocabulary') or []
    available = [t for t in pool if t not in used_vocab]
    if not available:
        return None
    templates = [
        "This is closely tied to the wider issue of {term}, which shapes how the topic is generally understood.",
        "Much of this comes down to {term}, a factor that is often central to this kind of discussion.",
        "Considerations around {term} help explain why opinions on this point are rarely unanimous.",
        "{term_cap} is one of the underlying issues that makes this topic worth taking seriously.",
        "A closer look at {term} reveals why the picture is more complicated than it first appears.",
        "This connects to a broader concern about {term} that extends well beyond this single case.",
    ]
    if used_templates is None:
        used_templates = set()
    remaining_templates = [t for t in templates if t not in used_templates]
    if not remaining_templates:
        return None
    template = rng.choice(remaining_templates)
    used_templates.add(template)
    term = rng.choice(available)
    used_vocab.add(term)
    sentence = template.format(term=term, term_cap=term[0].upper() + term[1:])
    return sentence


def _build_body_paragraph(kind, family, level, rng, topic_phrase, actor, para_index, used_points, ref='it', used_vocab=None, used_templates=None, vocab_budget=None, anchor_phrase=''):
    """kind: 'benefit', 'drawback', 'cause', 'cause2', 'solution', 'example',
    or 'context'. used_points avoids picking the same supporting point twice
    within one essay. `ref` is the pronoun/short substitute used to refer
    back to the topic after its first mention in the intro, so body
    paragraphs don't repeat the full topic phrase every sentence.
    `used_vocab` (a set, shared across the essay) tracks which topic
    vocabulary terms have already appeared, so a body paragraph can
    optionally gain a third sentence grounded in fresh topic-specific
    vocabulary rather than only generic connective sentences.
    `anchor_phrase` (from _topic_anchor_phrase) holds the specific words
    from the user's own title that go beyond the matched family's generic
    keywords -- e.g. "TikTok, sleep and teenagers" for a title about
    "the impact of TikTok on teenage sleep patterns". When present, it
    occasionally replaces the generic `ref` pronoun so the paragraph
    stays visibly anchored to exactly what the user typed, not just to
    the family's generic subject matter."""
    if used_vocab is None:
        used_vocab = set()
    if used_templates is None:
        used_templates = set()
    # Use the user's own specific wording in place of the generic "it"
    # for roughly half of this paragraph's references -- often enough
    # that the essay reads as unmistakably about the user's exact topic,
    # but not so often that every sentence starts sounding mechanical.
    effective_ref = ref
    if anchor_phrase and rng.random() < 0.5:
        effective_ref = anchor_phrase
    ref = effective_ref
    body_opener = rng.choice(OPENERS_BODY)
    pool_key = 'drawbacks' if kind in ('drawback', 'cause', 'cause2') else 'benefits'
    if kind in ('example', 'context'):
        pool_key = 'examples' if kind == 'example' else 'contexts'
        pool = family.get(pool_key) or GENERIC_FAMILY[pool_key]
        available = [p for p in pool if p not in used_points] or pool
        point = rng.choice(available)
        used_points.add(point)
    else:
        available = [p for p in family[pool_key] if p not in used_points] or family[pool_key]
        point = rng.choice(available)
        used_points.add(point)
    # Cap vocabulary-grounded sentences at 2 per essay (checked by the
    # caller via vocab_budget) so this stays a light seasoning rather than
    # a dominant, easily-noticed sentence pattern across every paragraph.
    vocab_sent = _vocab_sentence(family, rng, used_vocab, used_templates) if vocab_budget and vocab_budget[0] > 0 else None
    if vocab_sent and vocab_budget:
        vocab_budget[0] -= 1
    if kind == 'benefit':
        sent1 = f"{body_opener} {ref} can {point}, which directly benefits {actor}."
        sent2 = rng.choice([
            f"This kind of improvement tends to have a positive knock-on effect over time.",
            f"Over time, this advantage tends to reinforce itself as {actor} adapt to the change.",
        ])
        out = f"{sent1} {sent2}"
    elif kind == 'drawback':
        opener = rng.choice(["However,", "Nevertheless,", "On the other hand,"])
        sent1 = f"{opener} {ref} can also {point}, which is a genuine concern for {actor}."
        sent2 = rng.choice([
            f"This drawback should not be dismissed simply because the overall trend is positive.",
            f"Without careful planning, this issue could outweigh some of the benefits already described.",
        ])
        out = f"{sent1} {sent2}"
    elif kind == 'cause':
        sent1 = f"{body_opener} rapid change in this area can {point}, which helps explain why the problem has grown."
        sent2 = f"As a result, {actor} are often unable to adapt quickly enough to keep pace with these changes."
        out = f"{sent1} {sent2}"
    elif kind == 'cause2':
        sent1 = f"A second, related factor is that a lack of coordinated planning can {point}."
        sent2 = f"Left unaddressed, this factor tends to reinforce the difficulties {actor} already face."
        out = f"{sent1} {sent2}"
    elif kind == 'example':
        example_opener = rng.choice([
            "A useful illustration of this is",
            "A clear real-world case is",
            "One concrete example that supports this is",
        ])
        sent1 = f"{example_opener} {point}."
        sent2 = rng.choice([
            f"A case like this shows that the effects are not merely theoretical.",
            f"Examples of this kind make the practical consequences much easier to grasp.",
        ])
        out = f"{sent1} {sent2}"
    elif kind == 'context':
        context_opener = rng.choice([
            f"It is also worth placing this in a wider context, since {point}",
            f"Looking beyond the immediate issue, {point}",
        ])
        sent1 = f"{context_opener}."
        sent2 = rng.choice([
            f"Recognising this variation makes it easier to judge the issue fairly rather than assuming one outcome applies everywhere.",
            f"This does not weaken the overall picture, but it does call for a degree of caution before generalising too far.",
        ])
        out = f"{sent1} {sent2}"
    else:  # solution
        sent1 = f"{body_opener} targeted measures could help {actor} {point}."
        sent2 = f"If implemented consistently, this approach could produce a measurable improvement within a reasonable timeframe."
        out = f"{sent1} {sent2}"
    # Occasionally (not every paragraph, to avoid a formulaic feel) add the
    # vocabulary-grounded sentence as a natural third sentence.
    if vocab_sent and rng.random() < 0.35:
        out = f"{out} {vocab_sent}"
    return out


def _build_conclusion(title, essay_type, family, level, rng, ref='it', anchor_phrase=''):
    # For the conclusion specifically, prefer the anchor phrase whenever
    # one exists -- restating the user's own specific topic wording one
    # final time is one of the clearest signals (to both the student and
    # any grader) that the essay actually answered what was asked, rather
    # than drifting into generic territory by the final paragraph.
    if anchor_phrase:
        ref = anchor_phrase
    opener = "In conclusion,"
    by_type = {
        'general': f"{opener} {ref} is a subject with many sides worth appreciating, and a closer look at it reveals more than a first glance would suggest.",
        'opinion': f"{opener} {ref} is largely beneficial, provided that any risks are properly managed.",
        'discussion': f"{opener} both perspectives have merit, but a balanced approach that considers the concerns on each side is the most realistic way forward.",
        'advantages_disadvantages': f"{opener} the advantages appear to outweigh the disadvantages, particularly when appropriate safeguards are in place.",
        'problem_solution': f"{opener} addressing this problem will require sustained effort, but the measures outlined above offer a realistic starting point.",
        'two_part': f"{opener} the issue brings both opportunities and challenges, and the right response depends on the specific context.",
        'cause_effect': f"{opener} the causes described above are closely linked to the effects that follow, and addressing them early would limit further damage.",
        'positive_negative': f"{opener} {ref} is, on balance, a positive development, although its success ultimately depends on how well it is managed.",
    }
    support_by_type = {
        'general': [
            "Taken together, the points discussed above show why the subject rewards closer attention.",
            "Each of the aspects covered here contributes to a fuller understanding of the topic as a whole.",
        ],
        'opinion': [
            "The arguments set out above suggest that a cautious but broadly positive stance is justified.",
            "Weighing the points discussed, the case in favour is, on balance, the stronger one.",
        ],
        'discussion': [
            "Neither side of the debate can be dismissed outright, and the strongest response acknowledges the merit in both.",
            "The evidence on each side suggests that a middle-ground position is more realistic than an absolute one.",
        ],
        'advantages_disadvantages': [
            "The benefits identified above are significant, though they should not be allowed to overshadow the genuine costs involved.",
            "Recognising both sides of the balance sheet leads to a more honest overall assessment.",
        ],
        'problem_solution': [
            "None of the measures discussed is a complete solution on its own, but together they offer real progress.",
            "Sustained commitment, rather than a single fix, is likely to be what makes the biggest difference.",
        ],
        'two_part': [
            "Considering both parts together gives a more complete answer than treating either in isolation.",
            "The two strands of this question are closely related, and neither can be fully understood without the other.",
        ],
        'cause_effect': [
            "Recognising these causes early offers the best chance of limiting their more serious effects.",
            "The chain of cause and effect described above points to where intervention would be most useful.",
        ],
        'positive_negative': [
            "How this balance plays out in practice will depend largely on the choices made by those involved.",
            "The positive effects identified above are real, but so are the risks that come with them.",
        ],
    }
    recommendation_by_type = {
        'general': [
            "For anyone encountering this subject for the first time, these are the aspects most worth remembering.",
            "A well-rounded view of the topic keeps all of these strands in mind.",
        ],
        'opinion': [
            "Going forward, careful management of the drawbacks would allow the benefits to be realised more fully.",
            "With the right safeguards in place, the overall outcome is likely to remain a positive one.",
        ],
        'discussion': [
            "A thoughtful compromise that draws on the strongest points of each side offers the most sensible way forward.",
            "Continued open discussion, rather than a fixed position, seems the most productive path.",
        ],
        'advantages_disadvantages': [
            "Careful planning would help ensure that the advantages are not undermined by avoidable problems.",
            "With sensible safeguards, the disadvantages need not outweigh the clear benefits on offer.",
        ],
        'problem_solution': [
            "A combination of the measures outlined above, applied consistently, offers the most realistic path forward.",
            "With sustained effort from all involved, meaningful improvement is well within reach.",
        ],
        'two_part': [
            "Approaching each part on its own terms, while keeping the connection between them in view, offers the clearest way forward.",
            "A response that addresses both elements together is likely to prove the most effective.",
        ],
        'cause_effect': [
            "Tackling the underlying causes, rather than only the visible effects, offers the most lasting solution.",
            "Early, well-targeted action remains the most effective way to limit the effects described above.",
        ],
        'positive_negative': [
            "Careful, ongoing management offers the best chance of preserving the positives while limiting the negatives.",
            "How well this balance is maintained will ultimately determine whether the outcome proves a lasting success.",
        ],
    }
    core = by_type.get(essay_type, by_type['opinion'])
    support = rng.choice(support_by_type.get(essay_type, support_by_type['opinion']))
    recommendation = rng.choice(recommendation_by_type.get(essay_type, recommendation_by_type['opinion']))
    return f"{core} {support} {recommendation}"



def _generate_myanmar_essay(title, essay_type='opinion', level='B2', target_words=250, seed=None):
    """Deterministic Myanmar-language model essay generator.
    This is intentionally local/offline and returns Burmese prose suitable for
    the same Edu editor. Burmese does not use spaces between every word, so
    target_words is treated as an approximate token/segment target.
    """
    rng = random.Random(seed)
    title = (title or '').strip() or "ဤအကြောင်းအရာ"
    type_openers = {
        'opinion': "ဤအကြောင်းအရာနှင့် ပတ်သက်၍ ကျွန်ုပ်အမြင်အရ အကျိုးကျေးဇူးများနှင့် အခက်အခဲများကို ချိန်ဆပြီး ရှင်းလင်းစွာ သုံးသပ်သင့်သည်။",
        'discussion': "ဤကိစ္စတွင် အမြင်နှစ်ဖက်စလုံးကို မျှတစွာ စဉ်းစားရန် လိုအပ်ပြီး နောက်ဆုံးတွင် အကြောင်းပြချက်ရှိသော သဘောထားတစ်ရပ်ကို ချမှတ်နိုင်သည်။",
        'advantages_disadvantages': "ဤအကြောင်းအရာတွင် အားသာချက်များနှင့် အားနည်းချက်များ နှစ်မျိုးစလုံး ရှိသောကြောင့် အကျိုးဆက်များကို သေချာစွာ ချိန်ဆသင့်သည်။",
        'problem_solution': "ဤပြဿနာ၏ အကြောင်းရင်းများကို နားလည်ပြီး လက်တွေ့ကျသော ဖြေရှင်းနည်းများကို အဆင့်ဆင့် စဉ်းစားရန် လိုအပ်သည်။",
        'two_part': "ဤမေးခွန်းကို ဖြေဆိုရာတွင် အပိုင်းနှစ်ပိုင်းစလုံးကို သီးခြားစီ စဉ်းစားပြီး ဆက်စပ်မှုရှိသော အကြောင်းပြချက်များဖြင့် ရှင်းပြသင့်သည်။",
        'cause_effect': "ဤအကြောင်းအရာကို နားလည်ရန် အဓိကအကြောင်းရင်းများနှင့် ဖြစ်ပေါ်လာနိုင်သည့် အကျိုးဆက်များကို ခွဲခြမ်းစိတ်ဖြာရန် လိုအပ်သည်။",
        'positive_negative': "ဤဖွံ့ဖြိုးတိုးတက်မှုသည် လူတစ်ဦးချင်းနှင့် လူ့အဖွဲ့အစည်းအပေါ် မည်သို့သက်ရောက်သည်ကို အပြုသဘောနှင့် အနုတ်သဘော နှစ်ဖက်စလုံးမှ သုံးသပ်သင့်သည်။",
    }
    transitions = ["ထို့အပြင်", "သို့သော်", "ထို့ကြောင့်", "အခြားတစ်ဖက်တွင်", "အထူးသဖြင့်", "အဆုံးတွင်"]
    bodies = [
        f"ပထမအချက်အနေဖြင့် {title} သည် နေ့စဉ်ဘဝနှင့် ပညာရေး၊ အလုပ်အကိုင် သို့မဟုတ် လူမှုဘဝတို့တွင် ထင်ရှားသော သက်ရောက်မှုရှိနိုင်သည်။ မှန်ကန်စွာ အသုံးချပါက အချိန်ကို ချွေတာနိုင်ပြီး သတင်းအချက်အလက်နှင့် အခွင့်အလမ်းများကို ပိုမိုလွယ်ကူစွာ ရရှိစေနိုင်သည်။",
        f"{rng.choice(transitions)} အကျိုးကျေးဇူးများရှိသကဲ့သို့ စိန်ခေါ်မှုများလည်း ရှိနိုင်သည်။ စနစ်တကျ မစီမံပါက အချိန်ကုန်ဆုံးမှု၊ မညီမျှမှု သို့မဟုတ် မလိုလားအပ်သော အကျိုးဆက်များ ဖြစ်ပေါ်လာနိုင်သည်။ ထို့ကြောင့် တာဝန်ရှိစွာ အသုံးပြုခြင်းနှင့် သင့်လျော်သော စည်းမျဉ်းများထားရှိခြင်းသည် အရေးကြီးသည်။",
        f"ထို့အပြင် လူငယ်များနှင့် ကျောင်းသားများအတွက် ဤအကြောင်းအရာကို ဝေဖန်စဉ်းစားနိုင်စွမ်းဖြင့် လေ့လာခြင်းက အကျိုးရှိသည်။ မတူညီသော အမြင်များကို နားထောင်ပြီး အထောက်အထားနှင့် ကိုက်ညီသော ဆုံးဖြတ်ချက်ကို ချမှတ်သင့်သည်။",
    ]
    conclusion = f"အနှစ်ချုပ်အားဖြင့် {title} သည် အခွင့်အလမ်းများနှင့် စိန်ခေါ်မှုများကို တစ်ပြိုင်နက်တည်း ဖြစ်စေနိုင်သော အကြောင်းအရာတစ်ရပ် ဖြစ်သည်။ သင့်လျော်သော စီမံခန့်ခွဲမှု၊ ပညာပေးမှုနှင့် တာဝန်ယူမှုတို့ဖြင့် ကောင်းကျိုးများကို တိုးမြှင့်ပြီး အားနည်းချက်များကို လျှော့ချနိုင်မည်ဟု ယုံကြည်သည်။"
    paras=[type_openers.get(essay_type,type_openers['opinion']), *bodies, conclusion]
    # Add useful supporting sentences until roughly the requested size.
    extras=[
        "ယင်းအချက်သည် အခြေအနေတစ်ခုနှင့်တစ်ခု မတူညီနိုင်သောကြောင့် ဒေသအလိုက် လိုအပ်ချက်များကိုလည်း ထည့်သွင်းစဉ်းစားသင့်သည်။",
        "အထောက်အထားများကို စစ်ဆေးပြီး အကျိုးရှိသော နည်းလမ်းများကို ရွေးချယ်ခြင်းက ပိုမိုကောင်းမွန်သော ရလဒ်ကို ဖြစ်စေနိုင်သည်။",
        "မိသားစု၊ ကျောင်းနှင့် လူမှုအသိုင်းအဝိုင်းတို့ ပူးပေါင်းပါဝင်ပါက အပြောင်းအလဲကို ပိုမိုတည်ငြိမ်စွာ ဆောင်ရွက်နိုင်သည်။",
        "ရေရှည်တွင် ပညာရေးနှင့် အသိပညာမြှင့်တင်မှုသည် ဤကိစ္စကို ဖြေရှင်းရာတွင် အရေးပါသော အခြေခံတစ်ရပ် ဖြစ်လာမည်။",
    ]
    def count_units(parts):
        # target_words is an English-essay-length number (120-500) reused as
        # a rough Myanmar length target. Burmese has no spaces between every
        # word, so neither a whitespace-word count nor a raw syllable count
        # (re.findall(r'[\u1000-\u109F]+', x), which collapses each
        # multi-syllable run into a single "unit" and under-counts by
        # roughly 5-10x) tracks target_words on a consistent scale — both
        # made this loop hit its guard limit almost immediately regardless
        # of target_words, so essay length stopped scaling with the
        # requested word count at all. Character count (excluding
        # whitespace) scales consistently with reading length in both
        # scripts, so compare against that using the same rough
        # chars-per-word ratio (~5.5) used for English word counts.
        return sum(len(re.sub(r'\s+', '', x)) for x in parts) / 5.5
    guard=0
    while count_units(paras) < target_words and guard < len(extras)*2:
        paras[1 + guard % len(bodies)] += " " + extras[guard % len(extras)]
        guard += 1
    return {"title": title, "essay": "\n\n".join(paras), "engine": "offline-myanmar"}


def _generate_custom_edu_essay(title, essay_type, level, target_words, language='en', mode='essay', seed=None):
    """Generate the four school essay types plus Debate mode locally."""
    rng = random.Random(seed)
    title = (title or '').strip() or ("ဤအကြောင်းအရာ" if language == 'my' else "This topic")
    if language == 'my':
        intros = {
            'descriptive': f"{title} နှင့် ပတ်သက်သော အဓိပ္ပာယ်၊ သဘောသဘာဝနှင့် ထင်ရှားသော အချက်များကို စနစ်တကျ တင်ပြသွားမည်ဖြစ်သည်။",
            'process': f"{title} နှင့် သက်ဆိုင်သော ဖြစ်စဉ်ကို အစမှအဆုံး အဆင့်ဆင့် ခွဲခြမ်း၍ ရှင်းလင်းတင်ပြသွားမည်ဖြစ်သည်။",
            'expository': f"{title} ကို နားလည်နိုင်ရန် အဓိပ္ပာယ်၊ အကြောင်းရင်း၊ အကျိုးဆက်နှင့် အရေးပါမှုတို့ကို ဖွင့်ဆိုရှင်းပြသွားမည်ဖြစ်သည်။",
            'argumentative': f"{title} နှင့် ပတ်သက်၍ မိမိရပ်တည်ချက်ကို ရှင်းလင်းစွာ ဖော်ပြပြီး အကြောင်းပြချက်နှင့် ဥပမာများဖြင့် ထောက်ခံတင်ပြသွားမည်ဖြစ်သည်။",
        }
        if mode == 'debate':
            # Myanmar school-debate style blueprint based on the supplied
            # exemplars: formal written register, four paragraphs, a clear
            # thesis in paragraph 2, concrete cause/effect examples in the
            # bodies, and a repeated position in the conclusion.
            if essay_type == 'balanced_two_sided':
                intro = f"{title} ဟူသောအဆိုသည် မိမိတို့၏ နေ့စဉ်ဘဝနှင့် လူမှုအသိုင်းအဝိုင်းအပေါ် သက်ရောက်မှုရှိသော အကြောင်းအရာတစ်ရပ် ဖြစ်သည်။ ယင်းအကြောင်းအရာကို တစ်ဖက်တည်းမှ မကြည့်ဘဲ အားသာချက်၊ အားနည်းချက်တို့ကို နှိုင်းယှဉ်စဉ်းစားသင့်သည်။ ထို့ကြောင့် {title} ဟူသောအဆိုကို မိမိအနေဖြင့် ထောက်ခံပါသည်။"
                p2 = f"{title} နှင့် ပတ်သက်၍ မိမိရပ်တည်ချက်ကို ထောက်ခံရသည့် အကြောင်းရင်းများစွာ ရှိပါသည်။ ပထမအချက်အနေဖြင့် ဤအကြောင်းအရာသည် လူတစ်ဦးချင်းနှင့် လူမှုအသိုင်းအဝိုင်းအတွက် လက်တွေ့ကျသော အကျိုးကျေးဇူးများ ဖြစ်ပေါ်စေနိုင်သည်။ ထို့အပြင် အခြေအနေကို မှန်ကန်စွာ စီမံခန့်ခွဲနိုင်ပါက ကောင်းကျိုးများကို ပိုမိုရရှိနိုင်မည်ဖြစ်သည်။"
                p3 = f"အခြားတစ်ဖက်တွင် {title} ၏ ဆန့်ကျင်ဘက်အမြင်ကိုလည်း ထည့်သွင်းစဉ်းစားရမည်ဖြစ်သည်။ ယင်းဘက်တွင် ကန့်သတ်ချက်များ၊ အခက်အခဲများနှင့် မလိုလားအပ်သော အကျိုးဆက်များ ဖြစ်ပေါ်နိုင်ခြေရှိသည်။ အထူးသဖြင့် အခြေအနေကို စနစ်တကျ မစီမံနိုင်ပါက အဆိုပါ အားနည်းချက်များ ပိုမိုထင်ရှားလာနိုင်သည်။ ထို့ကြောင့် ဆန့်ကျင်ဘက်၏ အားနည်းချက်များကို လက်တွေ့အခြေအနေများနှင့် ချိန်ဆ၍ စဉ်းစားသင့်သည်။"
                p4 = f"မိမိရပ်တည်သည့်ဘက်တွင်မူ အကျိုးကျေးဇူးများ ပိုမိုထင်ရှားသည်။ {title} ကို သင့်လျော်စွာ အသုံးချနိုင်ခြင်း၊ စနစ်တကျ စီမံနိုင်ခြင်းနှင့် လိုအပ်သည့် အသိပညာပေးမှုများ ပြုလုပ်နိုင်ခြင်းတို့ကြောင့် ကောင်းကျိုးများကို ရရှိနိုင်သည်။ ထို့ကြောင့် အကြောင်းပြချက်များကို ချိန်ဆစဉ်းစားလျှင် {title} ဟူသောအဆိုသည် မိမိအတွက် ပိုမိုနှစ်သက်ဖွယ်ကောင်းပြီး လက်တွေ့ကျသော အမြင်ဖြစ်သဖြင့် ထောက်ခံရခြင်းဖြစ်ပါသည်။"
                paras=[intro,p2,p3,p4]
            elif essay_type in ('balanced_pro_con','comparative_many'):
                intro = f"{title} ဟူသောအဆိုသည် ယနေ့ခေတ်တွင် စဉ်းစားသုံးသပ်ရန် လိုအပ်သော အကြောင်းအရာတစ်ရပ် ဖြစ်သည်။ ယင်းအဆိုတွင် အားသာချက်နှင့် အားနည်းချက် နှစ်ဖက်စလုံး ရှိနိုင်သဖြင့် မျှတစွာ ချိန်ဆသုံးသပ်ရန် လိုအပ်သည်။ ထို့ကြောင့် မိမိအနေဖြင့် ဤအဆိုကို ထောက်ခံပါသည်။"
                p2 = f"ပထမဦးစွာ {title} ကို ထောက်ခံရသည့် အဓိကအကြောင်းရင်းမှာ လက်တွေ့ဘဝတွင် အကျိုးရှိသော ရလဒ်များကို ဖြစ်ပေါ်စေနိုင်ခြင်းကြောင့် ဖြစ်သည်။ မိမိရပ်တည်သည့်ဘက်မှ ကြည့်လျှင် အချိန်၊ အရင်းအမြစ် သို့မဟုတ် အခွင့်အလမ်းများကို ပိုမိုထိရောက်စွာ အသုံးချနိုင်သည်။ ထို့ကြောင့် မိမိရပ်တည်ချက်သည် လက်တွေ့အခြေအနေနှင့် ကိုက်ညီသည်ဟု ယူဆပါသည်။"
                p3 = f"တစ်ဖက်တွင် {title} ၏ ဆန့်ကျင်ဘက်ဘက်၌ အခက်အခဲများနှင့် ကန့်သတ်ချက်များ ရှိနိုင်သည်။ အခြေအနေမမှန်ကန်လျှင် ကုန်ကျစရိတ်၊ အချိန်ကြန့်ကြာမှု သို့မဟုတ် မမျှတမှုများ ဖြစ်ပေါ်နိုင်သည်။ သို့သော် မိမိရပ်တည်သည့်ဘက်၏ အားသာချက်များမှာ ယင်းအားနည်းချက်များကို သင့်လျော်သော စီမံခန့်ခွဲမှုဖြင့် လျှော့ချနိုင်ခြင်း ဖြစ်သည်။"
                p4 = f"ထို့အပြင် ဆန့်ကျင်ဘက်၏ အားနည်းချက်များကို ချိန်ဆပြီး မိမိရပ်တည်သည့်ဘက်၏ အားသာချက်များကို နှိုင်းယှဉ်ကြည့်လျှင် {title} ၏ အကျိုးကျေးဇူးများက ပိုမိုထင်ရှားသည်။ ထို့ကြောင့် လက်တွေ့အကျိုးဆက်များနှင့် အကြောင်းပြချက်များအရ {title} ဟူသောအဆိုကို မိမိအနေဖြင့် ထောက်ခံရခြင်းဖြစ်ပါသည်။"
                paras=[intro,p2,p3,p4]
            else:
                # Covers 'one_sided' explicitly (a single committed position,
                # argued throughout with no opposing side engaged), and acts
                # as the final fallback for any future/unknown debate type.
                intro = f"{title} ဟူသောအဆိုသည် မိမိတို့အနေဖြင့် အလေးအနက်ထား စဉ်းစားသင့်သော အကြောင်းအရာတစ်ရပ် ဖြစ်သည်။ ယင်းအဆို၏ အဓိပ္ပာယ်နှင့် လက်တွေ့သက်ရောက်မှုများကို ချိန်ဆကြည့်လျှင် မိမိရပ်တည်သည့်ဘက်၏ အားသာချက်များကို တွေ့မြင်နိုင်သည်။ ထို့ကြောင့် ဤအဆိုကို ထောက်ခံပါသည်။"
                p2 = f"မိမိရပ်တည်ချက်ကို အစပြု၍ ဆိုရလျှင် {title} သည် လူတစ်ဦးချင်း၏ဘဝ၊ ပညာရေး သို့မဟုတ် လူမှုရေးအခြေအနေများအတွက် အကျိုးရှိစေနိုင်သည်။ ထို့အပြင် မှန်ကန်သော နည်းလမ်းဖြင့် ဆောင်ရွက်နိုင်ပါက ရေရှည်ကောင်းကျိုးများကိုလည်း ရရှိနိုင်သည်။ ထို့ကြောင့် ဤအဆိုကို ထောက်ခံရခြင်းဖြစ်ပါသည်။"
                p3 = f"ပထမအချက်အနေဖြင့် {title} သည် လက်တွေ့ဘဝတွင် အကျိုးကျေးဇူးများစွာ ပေးစွမ်းနိုင်သည်။ အချိန်နှင့် အရင်းအမြစ်များကို ထိရောက်စွာ အသုံးချနိုင်ခြင်း၊ အခွင့်အလမ်းများ ပိုမိုရရှိနိုင်ခြင်းတို့သည် ထင်ရှားသော အားသာချက်များ ဖြစ်သည်။ ထိုအကျိုးကျေးဇူးများကြောင့် လူတစ်ဦးချင်းနှင့် လူမှုအသိုင်းအဝိုင်းအတွက် ကောင်းကျိုးများ ဖြစ်ပေါ်လာနိုင်သည်။"
                p4 = f"ထို့အပြင် {title} ၏ အကျိုးကျေးဇူးများကို ရေရှည်အမြင်ဖြင့် စဉ်းစားလျှင် ပညာရေး၊ လူမှုရေးနှင့် စီးပွားရေးဘက်များတွင်လည်း အထောက်အကူပြုနိုင်သည်။ သို့ဖြစ်၍ အကြောင်းပြချက်များနှင့် လက်တွေ့အခြေအနေများကို ချိန်ဆသုံးသပ်ပြီးနောက် {title} ဟူသောအဆိုသည် သင့်လျော်မှန်ကန်သည်ဟု ယူဆသဖြင့် မိမိအနေဖြင့် အတည်ပြုထောက်ခံပါသည်။"
                paras=[intro,p2,p3,p4]
        else:
            intro = intros.get(essay_type, intros['argumentative'])
            my_bodies = {
                'descriptive': [
                    f"ပထမအချက်အနေဖြင့် {title} ၏ အဓိပ္ပာယ်နှင့် သွင်ပြင်လက္ခဏာများကို ဖော်ပြရမည်ဆိုပါက ၎င်းသည် ထင်ရှားသော ဂုဏ်သတ္တိများနှင့် ကွဲပြားသော အင်္ဂါရပ်များကို ပိုင်ဆိုင်ကြောင်း တွေ့ရသည်။ ဤအင်္ဂါရပ်များကြောင့် {title} သည် အခြားအရာများနှင့် ခွဲခြားသိမြင်နိုင်စေသည်။",
                    f"ဒုတိယအနေဖြင့် {title} နှင့်ပတ်သက်သော အသေးစိတ်အချက်များနှင့် ထင်ရှားသော ဥပမာများကို လေ့လာကြည့်ခြင်းအားဖြင့် ၎င်း၏ အနှစ်သာရကို ပိုမိုနားလည်နိုင်စေသည်။ လက်တွေ့ဘဝတွင် တွေ့ကြုံရသော ဥပမာများသည် ဤအချက်ကို ပိုမိုထင်ရှားစေသည်။",
                    f"တတိယအနေဖြင့် {title} ၏ ကျယ်ပြန့်သော အရေးပါမှုနှင့် တန်ဖိုးကို ထည့်သွင်းစဉ်းစားသင့်သည်။ လူတစ်ဦးချင်းအတွက်သာမက လူမှုအသိုင်းအဝိုင်းတစ်ခုလုံးအတွက်ပါ အဓိပ္ပာယ်ရှိကြောင်း တွေ့ရသည်။",
                ],
                'process': [
                    f"ပထမအဆင့်အနေဖြင့် {title} ၏ အစပြုခြင်းအဆင့်ကို ဖော်ပြရမည်ဆိုပါက အခြေခံအချက်များကို ရှင်းလင်းစွာ သိရှိထားရန် လိုအပ်သည်။ ဤအဆင့်သည် ဆက်လက်ဖြစ်ပေါ်လာမည့် အခြားအဆင့်များ၏ အခြေခံအုတ်မြစ် ဖြစ်သည်။",
                    f"ဒုတိယအဆင့်တွင် {title} ၏ အလယ်အလတ်အဆင့်များကို အစီအစဉ်အတိုင်း ဆက်လက်ဆောင်ရွက်ရသည်။ ပထမအဆင့်ကနေ ဆက်လက်ပေါ်ပေါက်လာသော ဤအဆင့်များသည် အချင်းချင်း ဆက်စပ်မှုရှိပြီး အစီအစဉ်တကျ ဖြစ်ပေါ်လာရသည်။",
                    f"နောက်ဆုံးအဆင့်အနေဖြင့် {title} ၏ အဆုံးသတ်အဆင့်နှင့် ရလဒ်ကို တွေ့ရသည်။ ယခင်အဆင့်များအားလုံး မှန်ကန်စွာ ပြီးဆုံးမှသာ ဤနောက်ဆုံးအဆင့်ကို အောင်မြင်စွာ ရောက်ရှိနိုင်မည် ဖြစ်သည်။",
                ],
                'expository': [
                    f"ပထမအချက်အနေဖြင့် {title} ၏ အကြောင်းရင်းများကို ရှင်းပြရမည်ဆိုပါက ၎င်းသည် များစွာသော အကြောင်းအချက်များကြောင့် ဖြစ်ပေါ်လာကြောင်း တွေ့ရသည်။ ဤအကြောင်းရင်းများကို နားလည်ခြင်းသည် ဆက်လက်ဖြစ်ပေါ်လာမည့် အကျိုးဆက်များကို ကြိုတင်နားလည်နိုင်စေသည်။",
                    f"ဒုတိယအချက်အနေဖြင့် {title} ကြောင့် ဖြစ်ပေါ်လာနိုင်သော အကျိုးဆက်များနှင့် သက်ရောက်မှုများကို ဆန်းစစ်ရမည်ဖြစ်သည်။ ကောင်းကျိုးနှင့် ဆိုးကျိုး နှစ်မျိုးစလုံး ဖြစ်ပေါ်နိုင်သောကြောင့် ဤအချက်များကို ရှင်းလင်းစွာ ခွဲခြားသိမြင်ရန် လိုအပ်သည်။",
                    f"တတိယအချက်အနေဖြင့် {title} ၏ အရေးပါမှုနှင့် လက်တွေ့ဘဝအတွက် အဓိပ္ပာယ်ကို ထည့်သွင်းစဉ်းစားသင့်သည်။ ဤအကြောင်းအရာကို နက်နဲစွာ နားလည်ထားခြင်းသည် ပိုမိုကောင်းမွန်သော ဆုံးဖြတ်ချက်များ ချမှတ်နိုင်ရန် အထောက်အကူပြုသည်။",
                ],
                'argumentative': [
                    f"ပထမအချက်အနေဖြင့် {title} ကို ထောက်ခံရသည့် အဓိကအကြောင်းရင်းမှာ လက်တွေ့ဘဝတွင် တိုက်ရိုက် အကျိုးကျေးဇူးများ ဖြစ်ပေါ်စေနိုင်ခြင်းကြောင့် ဖြစ်သည်။ ဤအချက်ကို ထောက်ခံသည့် ဥပမာများစွာ တွေ့ရှိနိုင်သည်။",
                    f"ဒုတိယအချက်အနေဖြင့် {title} သည် ရေရှည်တွင်လည်း ကောင်းကျိုးများကို ဆက်လက်ဖြစ်ပေါ်စေနိုင်သည်။ သင့်လျော်သော နည်းလမ်းများဖြင့် ဆောင်ရွက်ပါက ဤအကျိုးကျေးဇူးများ ပိုမိုထင်ရှားလာနိုင်သည်။",
                    f"မည်သို့ပင်ဆိုစေကာမူ {title} တွင် ထည့်သွင်းစဉ်းစားသင့်သည့် ကန့်သတ်ချက်အချို့လည်း ရှိနိုင်သည်။ သို့သော် ယင်းကန့်သတ်ချက်များထက် ရရှိနိုင်သော အကျိုးကျေးဇူးများက ပိုမိုအလေးထားထိုက်သောကြောင့် မိမိရပ်တည်ချက်မှာ {title} ကို ထောက်ခံရခြင်းဖြစ်ပါသည်။",
                ],
            }
            my_conclusions = {
                'descriptive': f"အနှစ်ချုပ်အားဖြင့် {title} သည် ထင်ရှားသော အင်္ဂါရပ်များနှင့် အသေးစိတ်အချက်များ ပါဝင်သော အကြောင်းအရာတစ်ခု ဖြစ်ကြောင်း တွေ့ရသည်။ ဤအချက်များကို နားလည်ခြင်းသည် {title} ၏ အနှစ်သာရကို ပိုမိုကျယ်ပြန့်စွာ သိမြင်နိုင်စေသည်။",
                'process': f"အနှစ်ချုပ်အားဖြင့် {title} ၏ လုပ်ငန်းစဉ်ကို အဆင့်ဆင့် လိုက်နာဆောင်ရွက်ခြင်းသည် အောင်မြင်သော ရလဒ်ကို ရရှိစေသည်။ ဤအဆင့်များကို စနစ်တကျ လိုက်နာခြင်းသည် ရလဒ်ကောင်းအတွက် မရှိမဖြစ် အရေးကြီးကြောင်း တွေ့ရသည်။",
                'expository': f"အနှစ်ချုပ်အားဖြင့် {title} ၏ အကြောင်းရင်းနှင့် အကျိုးဆက်များကို နားလည်ခြင်းသည် ဤအကြောင်းအရာ၏ အရေးပါမှုကို ပိုမိုထင်ရှားစေသည်။ သင့်လျော်သော နားလည်မှုဖြင့် ချဉ်းကပ်ပါက ကောင်းကျိုးများကို တိုးမြှင့်နိုင်မည် ဖြစ်သည်။",
                'argumentative': f"အနှစ်ချုပ်အားဖြင့် အထက်ပါ အကြောင်းပြချက်များအရ {title} ကို မိမိအနေဖြင့် ထောက်ခံပါသည်။ ကန့်သတ်ချက်များ ရှိနိုင်သော်လည်း လက်တွေ့ကျသော အကျိုးကျေးဇူးများက ပိုမိုအရေးကြီးသည်ဟု ယုံကြည်ပါသည်။",
            }
            bodies = my_bodies.get(essay_type, my_bodies['descriptive'])
            conclusion = my_conclusions.get(essay_type, my_conclusions['descriptive'])
            paras=[intro,*bodies,conclusion]
    else:
        intros = {
            'descriptive': f"This essay describes {title} by examining its main features, setting and effects in a clear and organised way.",
            'process': f"This essay explains the process connected with {title} in a logical sequence, from the starting point to the final outcome.",
            'expository': f"This essay explains {title} by defining the issue, examining its causes and effects, and clarifying why it matters.",
            'argumentative': f"This essay presents a clear position on {title} and supports it with reasons, examples and consideration of an opposing view.",
        }
        if mode == 'debate':
            debate_openers_en = {
                'balanced_two_sided': f"This debate presents both sides of {title} fairly before reaching a reasoned conclusion.",
                'balanced_pro_con': f"This debate weighs the advantages and disadvantages of {title} before reaching a reasoned conclusion.",
                'one_sided': f"This debate emphasizes one clear position on {title} and supports it with strong reasons.",
                'comparative_many': f"This debate compares the relevant sides of {title} and weighs their relative strengths and weaknesses."
            }
            debate_context_en = {
                'balanced_two_sided': f"Reasonable people hold genuinely different views on {title}, and both deserve a fair hearing.",
                'balanced_pro_con': f"Like most debates of this kind, {title} involves a real trade-off between benefit and cost.",
                'one_sided': f"While {title} is sometimes contested, the case in favour rests on solid and consistent reasoning.",
                'comparative_many': f"Several distinct positions are possible on {title}, each resting on different priorities and evidence.",
            }
            debate_final_en = {
                'balanced_two_sided': "The paragraphs that follow set out the strongest points on each side before arriving at a final judgement.",
                'balanced_pro_con': "The discussion below sets out the main advantages first, followed by the most significant drawbacks.",
                'one_sided': "The following paragraphs build the case step by step, addressing likely objections along the way.",
                'comparative_many': "The sections that follow compare these positions directly before identifying the most convincing one.",
            }
            intro = (
                f"{debate_openers_en.get(essay_type, debate_openers_en['balanced_two_sided'])} "
                f"{debate_context_en.get(essay_type, debate_context_en['balanced_two_sided'])} "
                f"{debate_final_en.get(essay_type, debate_final_en['balanced_two_sided'])}"
            )
            bodies = [
                f"Supporters argue that {title} can bring practical benefits and create meaningful opportunities. This position is strengthened when the available evidence shows clear advantages.",
                f"However, opponents point out that {title} may also create limitations, costs or unintended consequences. These concerns should not be dismissed when judging the overall issue.",
                f"On balance, the strongest position is one that compares both sides carefully and distinguishes strong evidence from unsupported claims.",
            ]
            conclusion = (
                f"In conclusion, {title} should be judged through a balanced comparison of the arguments for and against it. "
                "Neither side can be dismissed outright, and the strongest judgement is the one that weighs the evidence on both sides fairly. "
                "Keeping this balance in mind offers the most convincing way to settle the debate."
            )
        else:
            intro = intros.get(essay_type, intros['argumentative'])
            intro_context_en = {
                'descriptive': f"Several distinct features of {title} are worth setting out in turn.",
                'process': f"Each stage of this process builds on the one before it, so the order matters.",
                'expository': f"A number of related factors help explain why {title} matters and how it developed.",
                'argumentative': f"The strongest case rests on evidence and reasoning rather than assertion alone.",
            }
            intro_final_en = {
                'descriptive': "The paragraphs that follow describe these features one by one.",
                'process': "The following paragraphs trace the process from beginning to end.",
                'expository': "The discussion below examines these factors in a logical order.",
                'argumentative': "The paragraphs that follow set out the reasoning behind this position, along with an opposing view.",
            }
            intro = (
                f"{intro} "
                f"{intro_context_en.get(essay_type, intro_context_en['argumentative'])} "
                f"{intro_final_en.get(essay_type, intro_final_en['argumentative'])}"
            )
            bodies = [
                f"One important aspect of {title} is its direct effect on individuals and communities. Clear examples can help explain why this issue deserves attention.",
                f"Furthermore, the wider consequences of {title} should be considered rather than focusing only on its immediate effects. Different circumstances can lead to different outcomes.",
                f"Another useful perspective is to examine the issue from more than one angle. A balanced explanation is more convincing when it recognises limitations as well as strengths.",
            ]
            conclusion = (
                f"In conclusion, {title} should be understood through clear explanation, relevant examples and careful consideration of its wider implications. "
                "Taken together, the points discussed above give a fuller and more balanced picture than any single perspective could offer on its own. "
                "Keeping all of these aspects in mind is the best way to reach a fair and well-supported understanding of the issue."
            )
    # For Myanmar debate mode, the four-paragraph blueprint above already
    # defines the complete paragraph list. Do not rebuild it from `bodies`
    # and `conclusion` here because those locals are intentionally not
    # created in the debate branches. Rebuilding them caused an
    # UnboundLocalError when Generate အဆိုအချေ was clicked.
    if not (language == 'my' and mode == 'debate'):
        paras=[intro]+bodies+[conclusion]
    extras = ([
        "ဤအချက်သည် အခြေအနေအလိုက် ကွဲပြားနိုင်သောကြောင့် လက်တွေ့လိုအပ်ချက်များကိုလည်း ထည့်သွင်းစဉ်းစားသင့်သည်။",
        "ပညာရေးနှင့် လူမှုအသိုင်းအဝိုင်း ပူးပေါင်းပါဝင်ပါက ရလဒ်ကောင်းများ ရရှိနိုင်သည်။",
    ] if language=='my' else [
        "This point can vary according to context, so practical circumstances should also be considered.",
        "Education and cooperation between schools, families and communities can improve the final outcome.",
    ])
    def units():
        # See count_units() in _generate_myanmar_essay above: target_words
        # is an English-length number reused for Myanmar, so compare
        # against non-whitespace character count (which scales consistently
        # with reading length in Burmese) using the same rough
        # chars-per-word ratio as English, not a raw syllable-run count —
        # a raw count made this loop stop scaling with target_words almost
        # immediately for every Myanmar essay/debate length option.
        return sum(len(re.sub(r'\s+', '', p)) / 5.5 for p in paras) if language=='my' else sum(len(p.split()) for p in paras)
    guard=0
    while units() < int(target_words)*0.75 and guard < 12:
        # Append to a body paragraph for normal essays, or to one of the
        # middle paragraphs for Myanmar debate mode.
        body_indexes = list(range(1, max(2, len(paras)-1)))
        paras[body_indexes[guard % len(body_indexes)]] += " " + extras[guard%len(extras)]
        guard += 1
    return {"title": title, "essay": "\n\n".join(paras), "engine": "offline", "mode": mode}

def generate_essay_offline(title, essay_type='opinion', level='B2', target_words=250, seed=None, language='en', mode='essay'):
    """Build a complete model essay locally, with no AI call.

    Returns a dict: {"title": str, "essay": str, "engine": "offline"}.
    Randomised per call (unless a seed is given) so repeated generations on
    the same title are not identical — this is the "humanize" variation
    pass that keeps output from reading like one fixed canned template.
    """
    language = 'my' if str(language or 'en').lower().startswith('my') else 'en'
    # _generate_custom_edu_essay() covers two cases only: (1) real debate
    # mode (any language), and (2) Myanmar's four school essay types
    # (descriptive/process/expository/argumentative), which have no
    # equivalent in the English opinion/discussion/etc. template system
    # below. It must NOT be reached for English essay-mode requests, since
    # its English 'else' branch falls back to argumentative/debate-style
    # phrasing ("supporters argue... opponents point out...") regardless of
    # the essay type the student actually asked for.
    if mode == 'debate' or (language == 'my' and essay_type in {'descriptive','process','expository','argumentative'}):
        return _generate_custom_edu_essay(title, essay_type=essay_type, level=level, target_words=target_words, language=language, mode=mode, seed=seed)
    if language == 'my':
        return _generate_myanmar_essay(title, essay_type=essay_type, level=level, target_words=target_words, seed=seed)
    rng = random.Random(seed)
    title = (title or '').strip() or "This issue"
    essay_type = essay_type if essay_type else 'opinion'
    level = (level or 'B2').upper()
    target_words = max(120, min(500, int(target_words or 250)))

    family = _detect_family(title)
    # The specific words from the user's own title, beyond whatever the
    # matched family's generic keyword set already covers -- this is what
    # keeps the essay tied to exactly what the user typed (e.g. "TikTok",
    # "teenage sleep") rather than reading as generic, swappable content
    # for the family it was matched to. Falls back to '' for a genuinely
    # generic title with nothing more specific to anchor to, in which case
    # body paragraphs simply keep using the plain "it" reference as before.
    anchor_words = _topic_anchor_words(title, family)
    anchor_phrase = _topic_anchor_phrase(title, family)
    # Pass the same anchor words into _title_phrase so that a
    # question/clause-style title (which falls back to a generic "this
    # policy"/"this topic" noun phrase) still carries the title's specific
    # content in its very first mention, e.g. "this policy on single-use
    # plastics" instead of a bare, contentless "this policy".
    topic_phrase = _title_phrase(title, anchor_words=anchor_words)
    # Pick one actor for the whole essay (not a fresh one per paragraph) so
    # the essay consistently refers to the same group throughout, and avoid
    # any noun that duplicates a word already in the topic phrase itself
    # (e.g. topic "governments do more..." picking actor "governments" would
    # produce "...which directly benefits governments").
    topic_words = set(topic_phrase.lower().split())
    actor_candidates = [n for n in family['nouns'] if not (set(n.lower().split()) & topic_words)] or family['nouns']
    actor = rng.choice(actor_candidates)

    intro = _build_intro(title, essay_type, family, level, rng, actor, has_position=True)

    if essay_type == 'general':
        # A general (descriptive/expository/narrative) essay does not argue
        # a side, so it never uses the benefit/drawback or cause/solution
        # pairings — it simply develops separate descriptive aspects.
        core_kinds = ['example', 'context']
    elif essay_type == 'problem_solution':
        core_kinds = ['cause', 'cause2', 'solution']
    elif essay_type in ('advantages_disadvantages', 'discussion', 'two_part', 'positive_negative'):
        core_kinds = ['benefit', 'drawback']
    elif essay_type == 'cause_effect':
        core_kinds = ['cause', 'drawback']
    else:  # opinion
        core_kinds = ['benefit', 'drawback']

    # Scale the essay's depth to the requested length instead of padding
    # a fixed skeleton with loose repeated sentences. Short/medium targets
    # (up to ~300 words) stay in the tight five-paragraph model-essay shape
    # (intro, 3 body paragraphs, conclusion). Longer targets add up to two
    # further body paragraphs — each a genuinely new point, not a repeat —
    # so 500-word requests are reached with real content rather than
    # padding a handful of sentences past the point of making sense.
    max_body_paras = 3 if target_words <= 300 else (4 if target_words <= 380 else (5 if target_words <= 460 else 6))
    est_para_words = 38
    fixed_words = 85  # rough intro (3-4 sentences) + conclusion (3-4 sentences) length
    wanted_body_paras = max(len(core_kinds), round((target_words - fixed_words) / (est_para_words * 2)))
    wanted_body_paras = min(wanted_body_paras, max_body_paras)

    # Build the paragraph plan: the essay-type-defining kinds first (so the
    # structure required by that essay type is always present), then extend
    # with 'example' and 'context' paragraphs — genuinely new content rather
    # than repeated points — to reach the target length.
    kinds = list(core_kinds)
    filler_cycle = ['example', 'context']
    fi = 0
    while len(kinds) < wanted_body_paras:
        kinds.append(filler_cycle[fi % len(filler_cycle)])
        fi += 1

    body_paragraphs = []
    used_points = set()
    used_vocab = set()
    used_templates = set()
    vocab_budget = [2]  # cap total vocabulary-grounded sentences per essay
    for i, kind in enumerate(kinds):
        body_paragraphs.append(
            _build_body_paragraph(kind, family, level, rng, topic_phrase, actor, i, used_points, ref='it', used_vocab=used_vocab, used_templates=used_templates, vocab_budget=vocab_budget, anchor_phrase=anchor_phrase)
        )

    conclusion = _build_conclusion(title, essay_type, family, level, rng, ref='it', anchor_phrase=anchor_phrase)

    paragraphs = [intro] + body_paragraphs + [conclusion]

    def word_count(paras):
        return sum(len(p.split()) for p in paras)

    # Fine-tune toward the target: first add further body paragraphs (up to
    # max_body_paras, real new content each time); once that cap is
    # reached, extend existing paragraphs with fresh supporting sentences
    # from a pool large enough that longer essays (up to 500 words) don't
    # need to repeat a sentence.
    tolerance = max(20, round(target_words * 0.12))
    extra_sentences = [
        "This is a pattern that shows up in many different situations, not just isolated cases.",
        "It is a factor that becomes more noticeable the longer the underlying trend continues.",
        "This is worth bearing in mind when judging the issue as a whole.",
        "The scale of the effect can vary considerably depending on how the change is managed.",
        "Over time, this tends to shape expectations about what is considered normal practice.",
        "It is a consideration that policymakers and practitioners increasingly take into account.",
        "The precise outcome often depends on the resources and planning available at the time.",
        "This is why a one-size-fits-all judgement rarely captures the full picture.",
        "Attitudes toward this have shifted noticeably as more evidence has become available.",
        "For this reason, most careful assessments treat it as one factor among several.",
        "This helps explain why views on the issue can differ so widely between groups.",
        "It also illustrates why the topic continues to attract close attention.",
        "Circumstances differ from one case to another, so the exact impact is rarely identical.",
        "This has encouraged closer attention from researchers, educators and the public alike.",
        "Recognising this complexity is part of forming a fair overall judgement.",
        "It also reflects a broader shift in how the issue is generally understood.",
        "This tendency has become clearer as more long-term evidence has accumulated.",
        "Such variation is one reason blanket conclusions should be treated with caution.",
    ]

    guard = 0
    used_extras = set()
    pad_vocab_budget = [2]  # separate small cap for padding-phase vocab sentences
    while word_count(paragraphs) < target_words - tolerance and guard < 60:
        if len(kinds) < max_body_paras:
            kind = filler_cycle[(len(kinds) - len(core_kinds)) % len(filler_cycle)]
            new_para = _build_body_paragraph(kind, family, level, rng, topic_phrase, actor, len(kinds), used_points, ref='it', used_vocab=used_vocab, used_templates=used_templates, vocab_budget=vocab_budget, anchor_phrase=anchor_phrase)
            paragraphs.insert(-1, new_para)
            kinds.append(kind)
        else:
            candidates = [i for i in range(1, len(paragraphs) - 1) if paragraphs[i].count('. ') + 1 < 4]
            if not candidates:
                break
            idx = candidates[guard % len(candidates)]
            # Prefer a fresh vocabulary-grounded sentence over a generic
            # filler one, so padding stays topically relevant where
            # possible; only fall back to the generic pool once the
            # essay's topic vocabulary is exhausted.
            vocab_sent = _vocab_sentence(family, rng, used_vocab, used_templates) if pad_vocab_budget[0] > 0 else None
            if vocab_sent:
                pad_vocab_budget[0] -= 1
            remaining = [s for s in extra_sentences if s not in used_extras]
            if vocab_sent:
                sentence = vocab_sent
            elif remaining:
                sentence = rng.choice(remaining)
                used_extras.add(sentence)
            else:
                sentence = None
            if sentence is None:
                break
            paragraphs[idx] = paragraphs[idx] + " " + sentence
        guard += 1

    structural_minimum = len(core_kinds) + 2  # intro + core body paragraphs + conclusion
    guard = 0
    while word_count(paragraphs) > target_words + tolerance and guard < 10:
        idx = max(range(1, len(paragraphs) - 1), key=lambda i: len(paragraphs[i].split()))
        sents = re.split(r'(?<=[.!?])\s+', paragraphs[idx])
        if len(sents) > 1:
            paragraphs[idx] = ' '.join(sents[:-1])
        elif len(paragraphs) > structural_minimum:
            # Nothing left to trim in that paragraph — drop a whole filler
            # paragraph (never below the essay type's structural minimum).
            del paragraphs[idx]
        else:
            break
        guard += 1

    essay_text = "\n\n".join(paragraphs)
    clean_title = title[0].upper() + title[1:] if title else title
    essay_text = _adapt_to_level(essay_text, level, rng)
    return {"title": clean_title, "essay": essay_text, "engine": "offline"}


# ---------------------------------------------------------------------------
# CEFR level adaptation for English output
# ---------------------------------------------------------------------------
# The paragraph builders above (_build_intro/_build_body_paragraph/
# _build_conclusion) are written once, at a roughly B1/B2 sentence
# complexity, and the `level` argument was previously threaded through the
# whole call chain without ever changing the output — an A1 request and a
# C2 request produced identical prose. This pass adapts that shared B1/B2
# baseline text after the fact: simplifying it for A1/A2 (short sentences,
# basic connectors, plainer words) or upgrading it for C1/C2 (joined
# clauses, more advanced connectors and vocabulary). B1/B2 stay unchanged,
# since the baseline text was written at that level already.

# Advanced -> simple word swaps, used going down to A1/A2. Deliberately
# small and conservative: only words that appear in the generator's own
# templates above, so the swap is guaranteed to fit the sentence it lands
# in rather than risking an awkward substitution in arbitrary text.
_SIMPLIFY_WORDS = [
    (r'\bconsiderable\b', 'large'), (r'\bconsiderably\b', 'a lot'),
    (r'\bsignificant(ly)?\b', lambda m: 'big' if not m.group(1) else 'a lot'),
    (r'\bdemonstrates?\b', 'shows'), (r'\bindicates?\b', 'shows'),
    (r'\billustrates?\b', 'shows'),
    (r'\bnumerous\b', 'many'),
    (r'\butilises\b', 'uses'), (r'\butilise\b', 'use'),
    (r'\butilised\b', 'used'), (r'\butilising\b', 'using'),
    (r'\bobtains\b', 'gets'), (r'\bobtain\b', 'get'),
    (r'\bobtained\b', 'got'), (r'\bobtaining\b', 'getting'),
    (r'\bpurchases\b', 'buys'), (r'\bpurchase\b', 'buy'),
    (r'\bpurchased\b', 'bought'), (r'\bpurchasing\b', 'buying'),
    (r'\bapproximately\b', 'about'), (r'\bconsequently\b', 'so'),
    (r'\bnevertheless\b', 'but'), (r'\bfurthermore\b', 'also'),
    (r'\bmoreover\b', 'also'), (r'\bnotwithstanding\b', 'even so'),
    (r'\bconversely\b', 'but'), (r'\binsofar as\b', 'because'),
    (r'\baccordingly\b', 'so'), (r'\bsubstantial(ly)?\b', 'big'),
    (r'\benhances\b', 'improves'), (r'\benhance\b', 'improve'),
    (r'\benhanced\b', 'improved'), (r'\benhancing\b', 'improving'),
    (r'\bmitigates\b', 'reduces'), (r'\bmitigate\b', 'reduce'),
    (r'\bmitigated\b', 'reduced'), (r'\bmitigating\b', 'reducing'),
]

# Simple -> advanced word swaps, used going up to C1/C2.
_UPGRADE_WORDS = [
    (r'\bbig\b', 'considerable'), (r'\bshows?\b', 'demonstrates'),
    (r'\bmany\b', 'numerous'), (r'\bget[s]?\b', 'obtains'),
    (r'\babout\b(?=\s+\d)', 'approximately'),
    (r'\bimproves\b', 'enhances'), (r'\bimprove\b', 'enhance'),
    (r'\bimproved\b', 'enhanced'), (r'\bimproving\b', 'enhancing'),
    # 'reduce' -> 'mitigate' was deliberately removed: "mitigate" only
    # means to lessen something HARMFUL or negative ("mitigate the risk",
    # "mitigate pollution"). "Reduce" is used across this file for both
    # negative objects (reduce pollution -- fine to upgrade) and neutral
    # or positive ones (reduce opportunities, reduce access, reduce
    # options -- where "mitigate" is not just stylistically off but
    # actually the wrong word, since you cannot "mitigate" a good thing
    # being taken away). A blind regex swap has no way to tell these
    # apart, and reducING a positive noun is exactly the shape of many
    # drawback-list sentences in TOPIC_FAMILIES, so this swap was
    # silently producing incorrect vocabulary in drawback paragraphs
    # specifically. Rather than risk more of that, the swap is removed;
    # "reduce" remains correct, natural English at every CEFR level.
]
# 'help' -> 'facilitate' was deliberately removed: "help" freely takes a
# bare infinitive ("helps explain why..."), but "facilitate" grammatically
# needs a gerund or noun object ("facilitates explaining"/"facilitates the
# process"), so a blind word swap produced ungrammatical output like
# "facilitates explain why..." wherever the generator's own templates used
# "helps + bare verb" (a pattern that appears in several of them). Rather
# than special-case every context this word appears in, the swap is
# skipped entirely so C-level output stays grammatical.
# These three are connector words, so the swap is only grammatical at the
# very start of a sentence (a connector) — "it can also add" is a mid-
# clause adverb, and swapping that occurrence to "it can furthermore add"
# is wrong placement, whereas "Also, it can add..." -> "Furthermore, it
# can add..." at the start of a sentence is a safe, natural swap. These
# are matched separately, anchored to the sentence start, rather than
# folded into _UPGRADE_WORDS above.
_UPGRADE_CONNECTORS_SENTENCE_START = [
    (r'^so\b', 'Consequently'), (r'^but\b', 'Nevertheless'), (r'^also\b', 'Furthermore'),
]

_BASIC_CONNECTORS = {'however': 'but', 'furthermore': 'also', 'moreover': 'also',
                      'nevertheless': 'but', 'consequently': 'so', 'therefore': 'so',
                      'in addition': 'also', 'as a result': 'so', 'for instance': 'for example',
                      'in contrast': 'but', 'notwithstanding': 'even so', 'conversely': 'but',
                      'accordingly': 'so', 'in light of this': 'because of this',
                      'to that extent': 'in that way', 'henceforth': 'from now on',
                      'insofar as': 'because', 'by the same token': 'in the same way',
                      'by contrast': 'but'}


def _simplify_sentence_for_a_level(sentence):
    """Split one B1/B2-complexity sentence into shorter, plainer sentences
    for A1/A2 output. Targets the comma-joined clause and subordinate-clause
    patterns the generator's own templates actually produce, rather than
    attempting general-purpose parsing."""
    s = sentence.strip()
    if not s:
        return s
    # Downgrade any advanced connector at the very start of the sentence
    # to a basic one first, so the split below doesn't leave an advanced
    # word stranded as its own short sentence. A sentence-initial "But"/
    # "So" reads correctly without a following comma, unlike "However,"/
    # "Therefore,", so the replacement omits it rather than reusing the
    # advanced connector's comma.
    for adv, basic in _BASIC_CONNECTORS.items():
        s = re.sub(rf'^{re.escape(adv)},?\s*', basic.capitalize() + ' ', s, flags=re.I, count=1)
    # Split at "because"/"since" (reason) and "although"/"though"/"while"/
    # "whereas"/"provided that" (contrast/condition) separately, since
    # simply cutting the sentence in two at either would silently drop the
    # logical relationship between the resulting clauses (e.g. "X should
    # not be dismissed because Y is positive" split blindly becomes two
    # unrelated statements that read as a contradiction). Each kind keeps a
    # short connector at the start of the second sentence instead.
    m = re.search(r',?\s+\b(because|since)\b\s+', s, re.I)
    if m and m.start() > 15:
        first = s[:m.start()].rstrip(' ,')
        rest = s[m.end():]
        if first and rest:
            first = first[0].upper() + first[1:]
            if not first.endswith(('.', '!', '?')):
                first += '.'
            rest = 'This is because ' + rest[0].lower() + rest[1:]
            s = f"{first} {rest}"
    else:
        m = re.search(r',?\s+\b(although|though|while|whereas|provided that)\b\s+', s, re.I)
        if m and m.start() > 15:
            first = s[:m.start()].rstrip(' ,')
            rest = s[m.end():]
            if first and rest:
                first = first[0].upper() + first[1:]
                if not first.endswith(('.', '!', '?')):
                    first += '.'
                rest = 'But ' + rest[0].lower() + rest[1:]
                s = f"{first} {rest}"
    # Split at ", and"/", but"/", so" — a very common B2 compound-sentence
    # shape in this generator's own template output — into two sentences.
    m = re.search(r',\s+(and|but|so|which)\s+', s)
    if m and m.start() > 15:
        first = s[:m.start()].rstrip(' ,')
        rest = s[m.end():]
        if first and rest:
            first = first[0].upper() + first[1:]
            if not first.endswith(('.', '!', '?')):
                first += '.'
            # "which" refers back to the previous clause; replace it with
            # "This" so the second half still reads as a complete sentence.
            if m.group(1) == 'which':
                rest = 'This ' + rest
            else:
                rest = rest[0].upper() + rest[1:]
            if not rest.endswith(('.', '!', '?')):
                rest += '.'
            s = f"{first} {rest}"
    return s


def _upgrade_sentence_for_c_level(sentences_list, rng):
    """Join short adjacent sentences with a sophisticated connector for
    C1/C2 output. Works on a paragraph's sentence list (not one sentence at
    a time) since upgrading complexity means combining, not splitting.
    Only semicolon-led connectors are used (not ", which"/", a point
    that"), because those require the second clause to grammatically
    describe the first clause as a whole — the generator's own sentences
    don't reliably have that shape, and forcing the join produced
    nonsensical output (e.g. "...properly managed — and this weighing the
    points discussed..."). A semicolon connector works regardless of the
    second sentence's internal grammar, since both sides stay complete,
    independent clauses either way."""
    c_connectors = ['; furthermore,', '; indeed,', '; moreover,', '; in fact,', '; notably,']
    out = []
    i = 0
    while i < len(sentences_list):
        cur = sentences_list[i].strip()
        # Only join two genuinely short sentences (roughly clause-length),
        # so this doesn't chain three or four sentences into one
        # unreadable run — and only about a third of the time, so C-level
        # output still has natural sentence-length variety rather than
        # every sentence being maximally joined.
        if (i + 1 < len(sentences_list) and len(cur.split()) <= 14
                and len(sentences_list[i + 1].split()) <= 16 and rng.random() < 0.55):
            nxt = sentences_list[i + 1].strip()
            connector = rng.choice(c_connectors)
            joined = cur.rstrip('.!?')
            nxt_lower = nxt[0].lower() + nxt[1:] if nxt else nxt
            out.append(f"{joined}{connector} {nxt_lower}")
            i += 2
        else:
            out.append(cur)
            i += 1
    return out


def _adapt_to_level(essay_text, level, rng):
    """Post-process the generated (B1/B2-baseline) essay text so A1/A2 and
    C1/C2 requests actually read differently, instead of `level` being
    accepted as a parameter but never affecting sentence complexity or
    vocabulary. B1/B2 are returned unchanged: the paragraph builders above
    already target that band, so there is nothing to adapt."""
    level = (level or 'B2').upper()
    if level not in ('A1', 'A2', 'C1', 'C2'):
        return essay_text

    paragraphs = essay_text.split('\n\n')
    adapted_paragraphs = []

    if level in ('A1', 'A2'):
        for para in paragraphs:
            sents = re.split(r'(?<=[.!?])\s+', para.strip())
            new_sents = []
            for s in sents:
                simplified = _simplify_sentence_for_a_level(s)
                for word in re.split(r'(?<=[.!?])\s+', simplified):
                    for pattern, repl in _SIMPLIFY_WORDS:
                        word = re.sub(pattern, repl, word, flags=re.I)
                    new_sents.append(word)
            adapted_paragraphs.append(' '.join(new_sents))
    else:  # C1/C2
        for para in paragraphs:
            sents = re.split(r'(?<=[.!?])\s+', para.strip())
            joined = _upgrade_sentence_for_c_level(sents, rng)
            upgraded = []
            for s in joined:
                for pattern, repl in _UPGRADE_WORDS:
                    s = re.sub(pattern, repl, s, flags=re.I, count=1)
                for pattern, repl in _UPGRADE_CONNECTORS_SENTENCE_START:
                    s = re.sub(pattern, repl, s, flags=re.I, count=1)
                upgraded.append(s)
            adapted_paragraphs.append(' '.join(upgraded))

    return '\n\n'.join(adapted_paragraphs)


# ---------------------------------------------------------------------------
# Local LLM essay engine
# ---------------------------------------------------------------------------
# This is intentionally independent from OpenAI/Groq. It talks only to an
# Ollama server running on the same machine/network. The model can be an
# OpenAI open-weight gpt-oss model (20B or 120B), or another Ollama model.
# The application therefore has no cloud AI dependency for essay generation.

import json as _local_json
import os as _local_os
import urllib.error as _local_urllib_error
import urllib.request as _local_urllib_request

LOCAL_LLM_URL = _local_os.getenv("TSO_LOCAL_LLM_URL", "http://127.0.0.1:11434/api/chat").strip()
LOCAL_LLM_MODEL = _local_os.getenv("TSO_LOCAL_LLM_MODEL", "gpt-oss:20b").strip()
LOCAL_LLM_TIMEOUT = int(_local_os.getenv("TSO_LOCAL_LLM_TIMEOUT", "180"))
LOCAL_LLM_FALLBACK = _local_os.getenv("TSO_LOCAL_LLM_FALLBACK", "true").lower() in {"1", "true", "yes", "on"}


def _generation_database_context(title, level, essay_type, language="en"):
    """Retrieve compact, original knowledge from the bundled generation DB.

    The DB is a grounding/reference layer, not a source of copyrighted essay
    text. The model receives topic angles, benefits/risks, examples, level
    guidance and a paragraph plan. This makes local generation substantially
    less template-driven while keeping it deterministic about task rules.

    Topic fidelity: rows are only included when they genuinely matched a
    word from the title. Previously, a title with no keyword match at all
    fell back to unrelated "most useful general records" and presented
    them to the model as if they were relevant topic knowledge — which
    actively risked pulling a narrow/unusual topic toward whatever
    unrelated domain happened to be first in the database. Now, an
    unmatched title gets no domain rows at all (just level/type/paragraph
    guidance), and the prompt says so explicitly, so the model relies on
    its own understanding of the actual title instead of being nudged
    toward a mismatched "example" domain.
    """
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        words = [w for w in re.findall(r"[A-Za-z]{3,}|[\u1000-\u109F]{2,}", (title or "").lower())]
        rows = []
        for w in words[:12]:
            rows.extend(con.execute(
                "SELECT * FROM generation_topic_knowledge WHERE lower(keywords) LIKE ? OR lower(title) LIKE ? LIMIT 4",
                (f"%{w}%", f"%{w}%")).fetchall())
        # Deduplicate. Deliberately no longer falls back to unrelated
        # "most useful general records" when nothing matches — presenting
        # mismatched domain knowledge as grounding risks pulling the essay
        # off the user's actual (possibly narrow or unusual) topic.
        seen = set(); unique = []
        for r in rows:
            if r["domain"] not in seen:
                seen.add(r["domain"]); unique.append(r)
        unique = unique[:3]
        lr = con.execute("SELECT rule FROM generation_level_rules WHERE level=?", (level,)).fetchone()
        tr = con.execute("SELECT rule FROM generation_type_rules WHERE type_key=?", (essay_type,)).fetchone()
        pr = con.execute("SELECT paragraph_plan FROM generation_pair_rules WHERE level=? AND type_key=?", (level, essay_type)).fetchone()
        parts = ["LOCAL TSO EDU KNOWLEDGE DATABASE (original pedagogical metadata):"]
        if lr: parts.append(f"Level guidance: {lr['rule']}")
        if tr: parts.append(f"Task guidance: {tr['rule']}")
        if pr: parts.append(f"Paragraph plan: {pr['paragraph_plan']}")
        if unique:
            for r in unique:
                parts.append(
                    f"Topic domain: {r['title']}\n"
                    f"Relevant angles: {r['angles']}\n"
                    f"Potential benefits: {r['benefits']}\n"
                    f"Potential risks/limitations: {r['risks']}\n"
                    f"Example contexts: {r['examples']}"
                )
        else:
            parts.append(
                "No stored topic domain closely matches this exact title. Do NOT substitute a "
                "nearby or more general domain's angles/benefits/risks below as if they were "
                "written for this topic — reason about this specific title directly from your "
                "own understanding of it instead."
            )
        con.close()
        return "\n\n".join(parts)
    except Exception:
        return "LOCAL TSO EDU KNOWLEDGE DATABASE: unavailable; rely on the topic and task instructions only."


def _local_word_count(text, language):
    if language == "my":
        return len(re.findall(r"[\u1000-\u109F]+", text or ""))
    return len((text or "").split())


def generate_essay_local(title, essay_type="opinion", level="B2", target_words=250,
                         language="en", mode="essay"):
    """Generate an essay with a self-hosted local LLM through Ollama.

    No OpenAI/Groq/Hugging Face request is made here. The detailed system
    prompt is deliberately explicit so the local model behaves like a
    purpose-built TSO Edu writing system rather than a generic chatbot.
    """
    language = "my" if str(language or "en").lower().startswith("my") else "en"
    level = str(level or "B2").upper()
    target_words = max(120, min(500, int(target_words or 250)))

    type_map = {
        "general": "general essay (descriptive, expository, or narrative — informative in purpose, not argumentative)",
        "opinion": "opinion essay with a clear position",
        "discussion": "discussion essay covering both views and a conclusion",
        "advantages_disadvantages": "advantages and disadvantages essay",
        "problem_solution": "problem and solution essay",
        "two_part": "two-part question essay answering both parts",
        "cause_effect": "cause and effect essay",
        "positive_negative": "positive and negative aspects essay",
        "descriptive": "Myanmar school descriptive/expository စာစီစာကုံး",
        "process": "Myanmar school process စာစီစာကုံး",
        "expository": "Myanmar school explanatory စာစီစာကုံး",
        "argumentative": "Myanmar school argumentative စာစီစာကုံး",
        "balanced_two_sided": "အကြောင်းအရာနှစ်ခု နှစ်ဖက်မျှအဆိုအချေ",
        "balanced_pro_con": "အကြောင်းအရာနှစ်ခု နှစ်ဖက်မျှအဆိုအချေ",
        "one_sided": "အကြောင်းအရာတစ်ခုကျိုးကြောင်းဆီလျော်သော တစ်ဖက်သတ်အဆိုအချေ",
        "comparative_many": "နှိုင်းယှဉ်သုံးသပ်သော အဆိုအချေ",
    }
    task = type_map.get(essay_type, essay_type)

    if language == "my":
        language_rules = """Write entirely in natural Myanmar Unicode (မြန်မာယူနီကုဒ်) and follow Myanmar school စာစီစာကုံး conventions. This is NOT an English essay translated word-for-word. Use natural Myanmar sentence order, Myanmar grammar, age-appropriate vocabulary, smooth paragraph transitions, and a clear beginning, development and conclusion.

Myanmar composition structure rules:
- For descriptive/expository/process/argumentative စာစီစာကုံး, write a complete school composition with: (1) နိဒါန်း, (2) စာကိုယ် အပိုင်းများ developing the topic logically, and (3) နိဂုံး. Normally use 5 natural paragraphs: introduction, 3 body paragraphs, conclusion.
- Do NOT print labels such as "နိဒါန်း", "စာကိုယ်", "နိဂုံး", "Paragraph 1", or numbered headings unless the user explicitly asks for them. Separate paragraphs with blank lines.
- The introduction must introduce the exact topic naturally, not say "ဤစာစီစာကုံးတွင်..." or translate "This essay will discuss...".
- Body paragraphs must contain concrete explanation, relevant details/examples and topic-specific ideas. Do not fill space with generic statements.
- The conclusion must naturally summarise the main idea and close the composition; do not introduce a completely new argument.
- Do not use IELTS-style English structure, English connectors, debate-script language, bullet points, Markdown headings, or meta commentary.
- Do not invent statistics, quotations, citations or named studies.
- Keep the title/topic exactly as the subject of the composition and keep every paragraph relevant to it.
- If the requested type is descriptive, describe characteristics/importance rather than arguing for or against. If process, explain stages in chronological order. If expository, explain meaning, causes, effects and importance. If argumentative, state a clear position and support it with reasons and examples.
- စာစီစာကုံး (essay mode) and အဆိုအချေ (debate mode) are DIFFERENT formats and must never be blended: စာစီစာကုံး is a five-paragraph school composition (introduction, three body paragraphs, conclusion) that does not follow a marks rubric here; အဆိုအချေ is a fixed four-paragraph proposition response scored 2+3+3+2 by a separate rubric, with an explicit stance stated in paragraph 2. If this is debate mode, follow the selected အဆိုအချေ pattern's four-paragraph structure exactly and use formal Myanmar debate-writing register — do not fall back to the five-paragraph စာစီစာကုံး structure under any circumstances."""
    else:
        language_rules = f"Write entirely in English at approximately CEFR {level}. Use natural student-appropriate grammar and vocabulary, not artificial template language."

    if mode == "debate":
        mode_rules = "This is DEBATE mode. Write in a debate/argumentative register: state a clear position, argue for it, and address the opposing side directly, following the requested debate type exactly."
    else:
        mode_rules = (
            "This is ESSAY mode, not debate mode. Do NOT write in a debate register. "
            "Do not use phrases like 'supporters argue', 'opponents argue', 'this debate presents', "
            "'on balance', or address an opposing side as if rebutting it in a live argument. "
            "Follow the conventions of the requested essay type exactly (for example: an opinion essay "
            "states and develops the writer's own view in a measured, explanatory tone; a discussion essay "
            "presents both views before giving a balanced conclusion; an advantages/disadvantages essay "
            "weighs both sides analytically; a GENERAL essay is purely descriptive, expository, or "
            "narrative — it must NOT take a side, weigh pros and cons, or argue a position at all, since "
            "the topic itself does not ask for one). The tone throughout should read like a school/exam "
            "model essay, not a spoken or written debate speech."
        )

    if language == "my" and mode == "debate":
        # အဆိုအချေ (debate) mode has its own fixed four-paragraph, 2+3+3+2
        # mark structure, scored by debate_engine._paragraph_score_flags.
        # This is NOT the five-paragraph စာစီစာကုံး format used by essay mode
        # (descriptive/process/expository/argumentative), and the two must
        # never be interchanged: mixing them produces writing the debate
        # rubric cannot score, or a school essay wrongly written as a
        # rebuttal speech.
        my_debate_rules = {
            "balanced_two_sided": """Use debate Pattern 1 (အကြောင်းအရာနှစ်ခု နှစ်ဖက်မျှအဆို). Exactly four paragraphs:
1. နိဒါန်း — introduce the proposition/topic neutrally (unscored, structurally required).
2. Clearly state your own position (ထောက်ခံ or ကန့်ကွက်) using explicit stance wording early in the paragraph — worth 2 marks.
3. Explain the WEAKNESS of the side you do not hold, with reasoning and example — worth 3 marks.
4. Explain the STRENGTH of your own side with reasoning/evidence, then close by reaffirming your position (နိဂုံး/အနှစ်ချုပ်/ထို့ကြောင့်) in the same paragraph — worth 3 + 2 marks.""",
            "balanced_pro_con": """Use debate Pattern J (အကြောင်းအရာတစ်ခု ကျိုး/ပြစ်မျှအဆို). Exactly four paragraphs:
1. နိဒါန်း — introduce the topic neutrally (unscored, structurally required).
2. Clearly state your own position using explicit stance wording early in the paragraph — worth 2 marks.
3. Body paragraph combining BOTH the opposing side's weakness and your own side's strength together — worth 3 marks.
4. A second body paragraph again combining both the opposing side's weakness and your own side's strength, then close by reaffirming your position (နိဂုံး/အနှစ်ချုပ်/ထို့ကြောင့်) — worth 3 + 2 marks.""",
            "comparative_many": """Use debate Pattern J (နှိုင်းယှဉ်သုံးသပ်သော အဆို). Exactly four paragraphs:
1. နိဒါန်း — introduce the topic and the several sides being compared (unscored, structurally required).
2. Clearly state your own position using explicit stance wording early in the paragraph — worth 2 marks.
3. Body paragraph comparing sides, combining weaknesses of other options with the strength of your preferred one — worth 3 marks.
4. A second comparative body paragraph doing the same, then close by reaffirming your position (နိဂုံး/အနှစ်ချုပ်/ထို့ကြောင့်) — worth 3 + 2 marks.""",
            "one_sided": """Use the one-sided debate pattern (တစ်ဖက်အလေးကဲအဆို). Exactly four paragraphs:
1. နိဒါန်း — introduce the topic neutrally (unscored, structurally required).
2. Clearly state your own position using explicit stance wording early in the paragraph — worth 2 marks.
3. Body paragraph giving a strong reason/evidence for your position — worth 3 marks.
4. A second body paragraph giving a further reason/evidence for your position, then close by reaffirming your position (နိဂုံး/အနှစ်ချုပ်/ထို့ကြောင့်) — worth 3 + 2 marks.""",
        }
        format_rules = "\n\n" + my_debate_rules.get(essay_type, my_debate_rules["balanced_two_sided"]) + """

Myanmar debate (အဆိုအချေ) output format:
- Output ONLY the finished four-paragraph debate composition — never five paragraphs, never the school-essay format.
- Use formal written Myanmar debate register, not a spoken speech and not a neutral descriptive composition.
- First line may be the proposition title if appropriate; do not add labels such as "Essay:" or "Paragraph 1".
- Separate the four paragraphs with exactly one blank line each; do not print paragraph labels or numbers.
- Do not use bullets, numbered lists, Markdown, emojis, English words, or explanatory notes.
- Stance words (ထောက်ခံ/ကန့်ကွက် style language) must appear early in paragraph 2, not deferred to later paragraphs.
- Aim for approximately the requested length, but the four-paragraph architecture and mark-earning content in each paragraph take priority over exact word count.
"""
    elif language == "my":
        my_type_rules = {
            "descriptive": """Use a Myanmar descriptive/expository school composition. Structure: introduction of the subject; body paragraph 1 on its meaning/characteristics; body paragraph 2 on important details, effects or examples; body paragraph 3 on wider significance or practical value; conclusion. Do not argue a side.""",
            "process": """Use a Myanmar process composition. Structure: introduction of the process; body paragraphs explaining the stages in correct chronological order with clear cause-and-effect links; final paragraph explaining the result/significance. Never rearrange the stages or turn the answer into an argumentative essay.""",
            "expository": """Use a Myanmar explanatory composition. Structure: introduction/definition; body paragraph 1 explaining the main idea or causes; body paragraph 2 explaining effects, examples or practical details; body paragraph 3 explaining importance, lessons or solutions where relevant; conclusion.""",
            "argumentative": """Use a Myanmar argumentative စာစီစာကုံး. Structure: introduction and clear position; body paragraph 1 with the strongest reason; body paragraph 2 with another reason and relevant example; body paragraph 3 addressing a reasonable limitation/counterpoint and explaining why the position still stands; conclusion reaffirming the position. This is a formal composition, not a spoken debate.""",
        }
        format_rules = "\n\n" + my_type_rules.get(essay_type, my_type_rules["argumentative"]) + """

Myanmar စာစီစာကုံး output format (five-paragraph school essay — this is NOT the four-paragraph အဆိုအချေ debate format):
- Output ONLY the finished composition.
- First line may be the composition title if a title is appropriate; do not add labels such as "Essay:".
- Use exactly one blank line between paragraphs.
- Do not use bullets, numbered lists, Markdown, emojis, English words, or explanatory notes.
- Aim for approximately the requested length, but prioritize natural Myanmar composition quality and complete structure over exact word count.
- Every paragraph must be substantive and connected to the title.
"""
    elif mode == "debate":
        format_rules = ""
    elif essay_type == "general":
        format_rules = """
Follow this exact five-paragraph GENERAL essay format (descriptive, expository, or narrative — this is NOT an argumentative task, so do not manufacture a debate):
1. Introduction (3-5 sentences): open by framing the topic — what it is, and why it is interesting or significant — without announcing 'this essay will discuss/examine...'. End with a clear thesis sentence that states the essay's main focus or central idea (not a "for or against" stance, since a general essay does not argue a side).
2. Body paragraph 1: develop ONE clear aspect, feature, stage, or part of the topic. Open with a topic sentence, then explain and support it with a concrete descriptive detail or realistic example.
3. Body paragraph 2: develop a second, different aspect, feature, stage, or part of the topic (not a "however/on the other hand" counterpoint — a general essay does not need to present an opposing side). Explain and support it the same way.
4. Body paragraph 3 (optional for shorter targets, include for longer ones): add a further aspect, detail, or reflection that deepens the picture already given.
5. Conclusion (2-3 sentences): begin with 'In conclusion,' briefly draw the picture together (not a repeat of the intro sentence-for-sentence), and end on a reflective or memorable closing note.

Additional style rules:
- Do NOT use debate/argument language anywhere: avoid 'I agree/disagree', 'in my opinion', 'the advantages outweigh', 'on the other hand', 'supporters/opponents argue', 'on balance'.
- Do not repeat the exact topic phrase in almost every sentence; after the first mention, refer back to it with pronouns ('it', 'this') or short substitutes.
- Vary sentence length and structure naturally rather than repeating one mechanical pattern in every paragraph.
- Prefer plain topic sentences over rhetorical openers like 'It goes without saying that...' or 'Nowadays, more and more...'.
"""
    else:
        format_rules = """
Follow this exact five-paragraph model-essay format:
1. Introduction (3-5 sentences): open by defining or framing the topic in general terms — what it is and why it matters — without announcing 'this essay will discuss/examine...'. End the paragraph with a clear thesis or stance sentence.
2. Body paragraph 1: develop ONE main point in support of the thesis (a benefit, cause, or first aspect). Open with a topic sentence stating the point, then explain it, then give one concrete supporting detail or realistic example.
3. Body paragraph 2: develop a second, different point — often a contrasting or complicating one (a drawback, counterpoint, or second aspect) introduced with a contrast word (however/nevertheless/on the other hand). Explain it and support it the same way.
4. Body paragraph 3 (optional for shorter targets, include for longer ones): add a further consideration, practical implication, or a note on who is responsible/what should be done, so the essay does not stop at only two points.
5. Conclusion (2-3 sentences): begin with 'In conclusion,' briefly restate the overall judgment or synthesis (not a repeat of the intro sentence-for-sentence), and end on a forward-looking or evaluative note.

Additional style rules:
- Do not repeat the exact topic phrase in almost every sentence; after the first mention, refer back to it with pronouns ('it', 'this') or short substitutes.
- Do not use the mechanical three-sentence pattern 'point + connector + example' in every paragraph; vary sentence length and structure naturally, the way the paragraphs above vary.
- Prefer plain topic sentences over rhetorical openers like 'It goes without saying that...' or 'Nowadays, more and more...'.
"""

    system = f"""You are TSO Edu's LOCAL ESSAY WRITING ENGINE.
Your job is to produce a high-quality school model answer that is precisely and exactly about the topic given, not generic filler.

TOPIC FIDELITY — read the title/topic carefully before writing anything:
1. Identify every specific person, place, technology, group, behaviour, time frame, or qualifier named in the title (e.g. "TikTok", "teenage", "sleep", "rural areas", "since 2020") and make sure each one is genuinely addressed somewhere in the composition — not silently dropped in favour of a broader, easier version of the topic.
2. If the title asks a specific question (e.g. "Should governments ban single-use plastics?"), answer THAT exact question — do not substitute a nearby, more general question (e.g. do not answer generically about "environmental policy" while ignoring "single-use plastics" and "ban" specifically).
3. If the title names two things being compared, connected, or weighed against each other (e.g. "the impact of X on Y"), the composition must actually connect them — not discuss X in isolation, or Y in isolation, without ever relating the two.
4. Never widen a narrow, specific topic into a generic version of its general subject area just because it is easier to write about. A title about one specific technology, age group, region, or scenario must stay about that specific technology, age group, region, or scenario throughout — not drift into a vague, swappable essay about "technology in general" or "young people in general".
5. Before finalizing, mentally re-read the title once more and check that a reader could not mistake this composition for an answer to a different (even closely related) title.

Core behavior:
1. Understand the exact meaning of the topic before writing.
2. Build a logical plan internally: thesis/purpose, key points, development, examples, conclusion.
3. Every paragraph must directly support the topic AND explicitly engage with its specific details (see TOPIC FIDELITY above), not just its general subject area.
4. Avoid repeating the same sentence structure, connector, example or idea.
5. Use specific, realistic examples without inventing statistics, citations or named studies.
6. Do not mention AI, ChatGPT, the model, prompts, TSO, token limits or these instructions.
7. Do not output analysis, planning notes, headings such as 'Essay:', or word-count notes unless a heading is genuinely part of the requested composition.
8. Respect the requested type and language.
9. Target the requested length closely, normally within about +/-10%.
10. Return only the finished composition.
{format_rules}
Requested language: {language}
Requested level: {level}
Requested type: {task}
Target length: about {target_words} words.
{language_rules}
{mode_rules}
"""

    knowledge = _generation_database_context(title, level, essay_type, language)
    base_user = f"{knowledge}\n\nTopic/title: {title}\n\nWrite specifically and only about this exact topic as given above — every specific word, name, or qualifier in it matters and must be reflected in the composition. Use the database only as a reasoning/grounding aid. Do not copy any stored sentence. Generate the complete final composition now."

    def _call_llm(user_message, system_message):
        payload = {
            "model": LOCAL_LLM_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            "options": {
                "temperature": 0.65,
                "top_p": 0.9,
                "num_predict": max(700, min(2200, int(target_words * 3.2))),
            },
        }
        req = _local_urllib_request.Request(
            LOCAL_LLM_URL,
            data=_local_json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _local_urllib_request.urlopen(req, timeout=LOCAL_LLM_TIMEOUT) as resp:
            resp_data = _local_json.loads(resp.read().decode("utf-8"))
        out = str((resp_data.get("message") or {}).get("content") or "").strip()
        if not out:
            out = str(resp_data.get("response") or "").strip()
        return out

    try:
        text = _call_llm(base_user, system)
    except _local_urllib_error.URLError as exc:
        if LOCAL_LLM_FALLBACK:
            result = generate_essay_offline(title, essay_type, level, target_words, language=language, mode=mode)
            result["engine"] = "offline-template-fallback"
            result["local_error"] = "Local LLM unavailable"
            return result["title"], result["essay"]
        raise RuntimeError(f"Local essay model is unavailable at {LOCAL_LLM_URL}: {exc}") from exc
    except Exception as exc:
        if LOCAL_LLM_FALLBACK:
            result = generate_essay_offline(title, essay_type, level, target_words, language=language, mode=mode)
            result["engine"] = "offline-template-fallback"
            return result["title"], result["essay"]
        raise RuntimeError(f"Local essay model request failed: {exc}") from exc

    if not text:
        if LOCAL_LLM_FALLBACK:
            result = generate_essay_offline(title, essay_type, level, target_words, language=language, mode=mode)
            return result["title"], result["essay"]
        raise RuntimeError("Local essay model returned an empty response.")

    # Post-generation topic-fidelity check (English only -- the anchor-word
    # machinery below is built on Latin-script tokenisation and English
    # stopword/family data, so it isn't meaningful for Myanmar output).
    # The system prompt already instructs the model at length to stay on
    # the exact topic, but instructions alone are not a guarantee: if the
    # model still drifted into a generic version of the subject (dropping
    # every specific named entity/qualifier from the title), this gives
    # the pipeline one automatic, targeted retry rather than silently
    # returning an off-topic composition to the user. This mirrors, for
    # the LLM path, the same anchor-word idea already used to keep the
    # offline template engine grounded in the user's exact wording.
    if language == "en":
        family = _detect_family(title)
        anchor_words = _topic_anchor_words(title, family)
        if anchor_words:
            text_lower = text.lower()

            def _mentioned(word):
                # Tolerate a plural/singular mismatch the same way family
                # matching does. For a multi-word anchor phrase (e.g.
                # "teenage sleep", built by the offline engine's
                # compound-merging logic), check that EACH significant
                # component word appears somewhere in the essay
                # independently, rather than requiring the exact literal
                # phrase adjacency from the title -- a genuinely on-topic
                # essay will naturally paraphrase "teenage sleep patterns"
                # as "teenagers... sleep..." across a sentence or two, not
                # necessarily reproduce that exact three-word run, and a
                # literal-substring check was flagging good, on-topic
                # essays as failures purely for paraphrasing normally.
                sub_words = word.split() if ' ' in word else [word]
                for sw in sub_words:
                    stem = _simple_stem(sw.lower())
                    if not re.search(r'\b' + re.escape(stem) + r'\w*\b', text_lower):
                        return False
                return True

            missing = [w for w in anchor_words if not _mentioned(w)]
            # Only treat this as a fidelity failure if the essay missed
            # MOST of its specific anchor words -- a single word in a long
            # title (e.g. only "Amazon" absent because the essay said
            # "the rainforest" instead) is well within normal paraphrase
            # and must not trigger an unnecessary, slower retry.
            if len(missing) >= max(1, (len(anchor_words) + 1) // 2):
                corrective_system = system + (
                    "\n\nIMPORTANT CORRECTION: a previous attempt at this exact task drifted away from the "
                    f"topic's specific details. The composition MUST explicitly engage with: {', '.join(missing)}. "
                    "Do not write a generic composition about the topic's general subject area -- "
                    "these specific words/names/qualifiers from the title must be clearly reflected in the text."
                )
                try:
                    retry_text = _call_llm(base_user, corrective_system)
                    if retry_text:
                        text = retry_text
                except Exception:
                    pass  # keep the original (still on-topic-ish) text rather than losing the response entirely

    # Remove accidental wrapper labels/markdown while preserving the actual composition.
    text = re.sub(r"^\s*(?:essay|answer|response)\s*:\s*", "", text, flags=re.I)
    if language == "my":
        # The UI expects a clean school composition, not a chatbot response.
        text = re.sub(r"^\s*(?:စာစီစာကုံး|အဖြေ|အကြောင်းအရာ)\s*[:：]\s*", "", text)
        text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)
        text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
        text = re.sub(r"^\s*\d+[.)、]\s+", "", text, flags=re.M)
        # Never let the model accidentally return English section labels.
        text = re.sub(r"^\s*(?:Introduction|Body|Conclusion|Paragraph\s*\d+)\s*[:：-]?\s*", "", text, flags=re.I|re.M)
        text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text.strip()
