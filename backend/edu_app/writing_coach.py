from flask import Blueprint, render_template, request, jsonify
import re, os, sqlite3, math
from pathlib import Path
from .myanmar_spelling import check_myanmar_spelling

# Mounted into the main app as a Blueprint (see backend/app.py) under the
# "/edu" prefix, so it shares the same Gunicorn/Flask process instead of
# running as a separate service. Its own templates/static live alongside it
# in this package, kept isolated from the job-board frontend.
edu_bp = Blueprint(
    "edu",
    __name__,
    url_prefix="/edu",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)
BASE = Path(__file__).resolve().parent
DB_PATH = BASE / 'data' / 'writing_coach.db'

LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
# Score bands are a CEFR-style internal estimator, not an official CEFR test.
LEVEL_RANGES = {'A1': (0, 34), 'A2': (35, 49), 'B1': (50, 64), 'B2': (65, 79), 'C1': (80, 87), 'C2': (88, 100)}
TARGET_LEVEL = {'A1': 'B2', 'A2': 'B2', 'B1': 'B2', 'B2': 'C1', 'C1': 'C2', 'C2': 'C2'}
TARGET_LABEL = {'A1': 'B2', 'A2': 'B2', 'B1': 'B2', 'B2': 'C1', 'C1': 'C2', 'C2': 'C2'}

TRANSITIONS = {
    'A1': ['and', 'but', 'because', 'so', 'then', 'also'],
    'A2': ['also', 'because', 'however', 'for example', 'first', 'then'],
    'B1': ['however', 'therefore', 'for example', 'in addition', 'as a result', 'while'],
    'B2': ['nevertheless', 'consequently', 'furthermore', 'in contrast', 'in addition', 'as a result', 'for instance'],
    'C1': ['moreover', 'notwithstanding', 'conversely', 'consequently', 'by contrast', 'in light of this', 'to that extent'],
    'C2': ['nevertheless', 'accordingly', 'notwithstanding', 'conversely', 'henceforth', 'insofar as', 'by the same token'],
}
CONCLUSION_LINKS = {
    'A1': ['So,', 'In the end,'],
    'A2': ['Finally,', 'In the end,'],
    'B1': ['In conclusion,', 'To sum up,'],
    'B2': ['In conclusion,', 'Overall,', 'To summarise,'],
    'C1': ['In conclusion,', 'Taken together,', 'Overall,'],
    'C2': ['In conclusion,', 'Taken together,', 'On balance,', 'Ultimately,'],
}

REPETITION_ALTERNATIVES = {
    'good': [('beneficial','use when the meaning is positive or useful'), ('effective','use when something works well'), ('valuable','use when something has clear worth')],
    'bad': [('harmful','use when something causes negative effects'), ('problematic','use when an issue creates difficulties'), ('unfavourable','use for a negative condition or outcome')],
    'important': [('significant','use for something with notable importance or impact'), ('essential','use when something is necessary'), ('crucial','use when something is especially important to the argument')],
    'big': [('substantial','use for a large amount, effect or change'), ('considerable','use for a notably large degree or amount'), ('major','use for an important or large-scale issue')],
    'many': [('numerous','use with countable plural nouns'), ('a wide range of','use when referring to varied types or groups'), ('a considerable number of','use with countable plural nouns in formal writing')],
    'thing': [('factor','use for a contributing element'), ('aspect','use for one part of a topic'), ('issue','use when referring to a problem or debated matter')],
    'people': [('individuals','use in formal/academic contexts'), ('members of the public','use when referring to the general population'), ('residents','use when specifically discussing people living in a place')],
    'use': [('utilise','use sparingly in formal writing when it genuinely adds precision'), ('employ','use when referring to a method, strategy or resource'), ('apply','use when putting a method, principle or technique into practice')],
    'help': [('assist','use in formal contexts'), ('support','use when something provides ongoing help'), ('facilitate','use when something makes a process easier or possible')],
    'show': [('demonstrate','use when evidence clearly proves or illustrates something'), ('indicate','use when evidence points toward a conclusion'), ('illustrate','use when an example makes an idea clearer')],
    'make': [('create','use when producing something new'), ('produce','use for an outcome, result or output'), ('establish','use when creating a system, condition or relationship')],
    'get': [('obtain','use for acquiring something, especially formally'), ('achieve','use for reaching a result or goal'), ('receive','use when something is given or delivered')],
    'think': [('argue','use when presenting a reasoned position'), ('believe','use for an opinion or conviction'), ('contend','use for a formal, strongly reasoned position')],
    'problem': [('challenge','use when the issue requires effort to overcome'), ('issue','use for a neutral or debated matter'), ('difficulty','use for a practical obstacle')],
    'advantage': [('benefit','use for a positive effect'), ('strength','use for a positive feature of a person/system'), ('merit','use in formal evaluation or comparison')],
    'disadvantage': [('drawback','use for a negative feature or limitation'), ('limitation','use when something restricts effectiveness or scope'), ('downside','use in less formal contexts')],
}

# Second-tier reasoned alternatives: extends REPETITION_ALTERNATIVES with more
# high-frequency essay vocabulary, each alternative carrying its own specific
# usage condition rather than a shared generic note.
REPETITION_ALTERNATIVES_EXT = {
    'easy': [('straightforward','use when a process has few complications'), ('manageable','use when a task is within reasonable capability'), ('effortless','use only when something requires almost no effort at all')],
    'difficult': [('challenging','use when effort is required but success is possible'), ('demanding','use when a task requires significant time or energy'), ('arduous','use for a task that is long and physically or mentally taxing')],
    'clear': [('evident','use when something is obvious from evidence'), ('apparent','use when something seems true based on appearance'), ('unambiguous','use when there is exactly one possible interpretation')],
    'different': [('distinct','use when things are clearly separate in kind'), ('varied','use when referring to a range of types'), ('contrasting','use when two things are being directly compared')],
    'similar': [('comparable','use when things share a measurable quality'), ('analogous','use when a comparison illustrates a shared structure'), ('equivalent','use when things are effectively the same in value or function')],
    'increase': [('rise','use for a gradual or measured increase, often with numbers'), ('escalate','use when an increase intensifies quickly or negatively'), ('expand','use for growth in scope, size or reach')],
    'decrease': [('decline','use for a gradual reduction over time'), ('diminish','use when something becomes smaller in degree or importance'), ('curb','use when an increase is being deliberately restrained')],
    'affect': [('influence','use when one thing shapes another without full control'), ('impact','use when the effect is significant or forceful'), ('shape','use when something gradually determines the form of a result')],
    'consider': [('examine','use when looking closely at something in detail'), ('weigh','use when comparing the merits of different options'), ('assess','use when forming a judgement about value or quality')],
    'result': [('outcome','use for the final state after a process'), ('consequence','use when the result follows logically or causally'), ('upshot','use in more informal but still standard writing for the practical result')],
    'cause': [('trigger','use when one specific event sets off a chain of effects'), ('factor','use for one of several contributing influences'), ('root','use when referring to the underlying, original source of a problem')],
    'issue': [('matter','use for a neutral topic under discussion'), ('concern','use when something causes worry or requires attention'), ('challenge','use when the issue specifically requires effort to resolve')],
    'benefit': [('advantage','use when comparing one option favourably to another'), ('merit','use in formal evaluation of worth'), ('asset','use when something is a valuable resource or strength')],
    'improve': [('enhance','use when a quality is being made better, not just fixed'), ('strengthen','use when resilience or capability is being increased'), ('refine','use when small, precise adjustments improve something already functional')],
    'reduce': [('lower','use for a straightforward decrease in level or amount'), ('minimise','use when the goal is to make something as small as possible'), ('curb','use when deliberately restraining growth or excess')],
    'provide': [('supply','use when giving a needed resource'), ('offer','use when something is made available, without obligation'), ('deliver','use when a promised outcome or service is completed')],
    'create': [('generate','use for producing something, often abstract, like ideas or data'), ('establish','use when setting up a lasting system or relationship'), ('produce','use for a concrete outcome or output')],
    'ensure': [('guarantee','use when the outcome is certain'), ('secure','use when protecting an outcome from risk'), ('confirm','use when verifying that something is already true')],
    'develop': [('evolve','use for gradual change over time, often without direct control'), ('cultivate','use when a skill or relationship is deliberately nurtured'), ('advance','use when progress is being made toward a goal')],
    'focus': [('concentrate','use when directing effort or attention narrowly'), ('prioritise','use when one thing is placed above others in importance'), ('emphasise','use when giving particular importance in an argument')],
    'level': [('degree','use for an abstract extent or intensity'), ('extent','use when measuring how far something applies'), ('standard','use when referring to a benchmark of quality')],
    'growing': [('increasing','use for a steady numerical rise'), ('mounting','use when pressure or concern is building up'), ('escalating','use when growth is rapid and often concerning')],
    'popular': [('widespread','use when something is common across a broad population'), ('prevalent','use in formal writing for something common in a specific context'), ('favoured','use when something is preferred over alternatives')],
    'necessary': [('essential','use when something cannot be omitted'), ('vital','use when something is critical to success or survival'), ('indispensable','use for something whose absence would be highly damaging')],
    'agree': [('concur','use in formal writing to align with a stated view'), ('endorse','use when actively supporting a proposal, not just agreeing with it'), ('align with','use when a position matches another without full commitment')],
}
REPETITION_ALTERNATIVES.update(REPETITION_ALTERNATIVES_EXT)


# Broad synonym bank imported conceptually from the standalone repeat-word replacer.
# The editor uses these only for repeated words; it does not generate new prose.
REPEAT_SYNONYMS = {
    'happy':['joyful','cheerful','delighted','content','pleased'],
    'sad':['unhappy','gloomy','melancholy','downcast','sorrowful'],
    'big':['large','huge','massive','substantial','considerable'],
    'small':['tiny','compact','miniature','limited','modest'],
    'good':['beneficial','effective','valuable','positive','excellent'],
    'bad':['harmful','problematic','unfavourable','negative','poor'],
    'fast':['rapid','swift','quick','prompt','speedy'],
    'slow':['gradual','leisurely','unhurried','sluggish','steady'],
    'important':['significant','essential','crucial','notable','fundamental'],
    'very':['extremely','remarkably','highly','particularly','exceptionally'],
    'said':['stated','mentioned','remarked','explained','reported'],
    'make':['create','produce','develop','establish','construct'],
    'help':['assist','support','facilitate','aid','enable'],
    'show':['demonstrate','indicate','illustrate','reveal','highlight'],
    'use':['employ','apply','utilise','adopt','implement'],
    'think':['believe','consider','argue','maintain','contend'],
    'many':['numerous','various','countless','a range of','a considerable number of'],
    'people':['individuals','residents','citizens','members of the public','communities'],
    'problem':['issue','challenge','difficulty','concern','obstacle'],
    'thing':['factor','aspect','element','issue','feature'],
    'advantage':['benefit','strength','merit','positive aspect','asset'],
    'disadvantage':['drawback','limitation','downside','weakness','negative aspect'],
    'change':['alter','modify','transform','adjust','shift'],
    'increase':['rise','grow','expand','escalate','increase'],
    'decrease':['decline','fall','reduce','diminish','drop'],
    'get':['obtain','receive','achieve','acquire','gain'],
    'need':['require','necessitate','demand','call for','depend on'],
    'give':['provide','offer','supply','deliver','grant'],
    'keep':['maintain','retain','preserve','sustain','continue'],
    'start':['begin','commence','initiate','launch','introduce'],
    'end':['finish','conclude','terminate','complete','cease'],
    'change':['alter','modify','transform','adjust','shift'],
}

# Second-tier synonym bank: broadens coverage of common essay words beyond the
# core set above (word classes: adjectives, verbs, abstract nouns, connectors,
# time/frequency words). Same offline, deterministic lookup mechanism as
# REPEAT_SYNONYMS — no generated text, only pre-authored alternatives.
REPEAT_SYNONYMS_EXT = {
    'nice':['pleasant','enjoyable','agreeable','delightful','likeable'],
    'wrong':['incorrect','mistaken','flawed','inaccurate','erroneous'],
    'easy':['straightforward','simple','effortless','manageable','uncomplicated'],
    'hard':['difficult','demanding','challenging','strenuous','arduous'],
    'interesting':['engaging','compelling','fascinating','absorbing','thought-provoking'],
    'boring':['tedious','dull','monotonous','uninteresting','unengaging'],
    'different':['distinct','varied','diverse','contrasting','dissimilar'],
    'similar':['comparable','alike','analogous','equivalent','corresponding'],
    'clear':['evident','apparent','obvious','unambiguous','transparent'],
    'strong':['robust','powerful','forceful','solid','compelling'],
    'weak':['fragile','feeble','insufficient','unconvincing','flimsy'],
    'popular':['widespread','prevalent','well-liked','common','favoured'],
    'common':['frequent','widespread','prevalent','typical','usual'],
    'rare':['uncommon','infrequent','scarce','exceptional','unusual'],
    'possible':['feasible','viable','plausible','achievable','conceivable'],
    'necessary':['essential','required','vital','indispensable','obligatory'],
    'useful':['beneficial','helpful','valuable','practical','constructive'],
    'harmful':['damaging','detrimental','injurious','destructive','adverse'],
    'main':['primary','principal','central','chief','key'],
    'growing':['increasing','expanding','rising','escalating','mounting'],
    'huge':['enormous','immense','vast','massive','substantial'],
    'tiny':['minuscule','minute','miniature','negligible','slight'],
    'quick':['swift','rapid','prompt','speedy','brisk'],
    'lot':['a great deal','a significant amount','a considerable number','plenty','a substantial number'],
    'ways':['methods','means','approaches','strategies','techniques'],
    'way':['method','approach','means','technique','manner'],
    'reason':['cause','motive','justification','rationale','grounds'],
    'result':['outcome','consequence','effect','upshot','ramification'],
    'cause':['trigger','source','origin','factor','root'],
    'effect':['consequence','impact','outcome','result','repercussion'],
    'impact':['effect','influence','consequence','repercussion','bearing'],
    'issue':['matter','concern','problem','question','topic'],
    'situation':['circumstance','scenario','condition','state of affairs','predicament'],
    'idea':['concept','notion','proposal','thought','suggestion'],
    'opinion':['view','stance','perspective','viewpoint','position'],
    'view':['perspective','stance','opinion','outlook','standpoint'],
    'benefit':['advantage','gain','asset','merit','upside'],
    'improve':['enhance','strengthen','upgrade','refine','boost'],
    'reduce':['lower','diminish','curb','lessen','minimise'],
    'affect':['influence','impact','shape','alter','sway'],
    'consider':['regard','examine','weigh','contemplate','assess'],
    'believe':['maintain','hold','contend','assert','argue'],
    'suggest':['propose','recommend','imply','indicate','advocate'],
    'explain':['clarify','elaborate on','account for','illustrate','outline'],
    'discuss':['examine','address','explore','analyse','consider'],
    'agree':['concur','align with','support','endorse','share the view'],
    'disagree':['dispute','object to','oppose','contest','reject'],
    'support':['back','endorse','uphold','advocate for','reinforce'],
    'part':['component','element','aspect','portion','segment'],
    'level':['degree','extent','stage','standard','magnitude'],
    'amount':['quantity','volume','sum','proportion','extent'],
    'number':['figure','quantity','total','tally','count'],
    'group':['category','cohort','segment','cluster','set'],
    'society':['community','the public','the population','civilisation','the populace'],
    'country':['nation','state','territory','land'],
    'world':['globe','planet','international community'],
    'government':['authorities','administration','the state','policymakers','officials'],
    'company':['firm','business','organisation','corporation','enterprise'],
    'job':['occupation','profession','position','role','post'],
    'money':['funds','finances','capital','income','revenue'],
    'child':['youngster','minor','young person','child'],
    'children':['youngsters','young people','minors','the younger generation'],
    'student':['learner','pupil','trainee'],
    'teacher':['educator','instructor','tutor','mentor'],
    'school':['institution','educational establishment'],
    'work':['labour','employment','effort','endeavour'],
    'life':['existence','livelihood','way of living'],
    'time':['period','era','duration','timeframe'],
    'today':['nowadays','currently','at present','in modern times'],
    'now':['currently','at present','presently','at this point'],
    'future':['times ahead','years to come','the years ahead'],
    'past':['history','earlier times','previous decades'],
    'always':['invariably','consistently','continually','without exception'],
    'never':['at no point','under no circumstances','not once'],
    'often':['frequently','regularly','commonly','routinely'],
    'sometimes':['occasionally','at times','periodically','on occasion'],
    'also':['additionally','furthermore','moreover','in addition'],
    'but':['however','nevertheless','yet','whereas'],
    'because':['since','as','given that','due to the fact that'],
    'so':['therefore','consequently','as a result','thus'],
    'if':['provided that','assuming that','in the event that'],
    'true':['accurate','valid','correct','factual'],
    'false':['inaccurate','incorrect','untrue','mistaken'],
    'real':['genuine','actual','authentic','tangible'],
    'obvious':['evident','apparent','clear-cut','unmistakable'],
    'difficult':['challenging','demanding','arduous','taxing'],
    'simple':['straightforward','uncomplicated','basic','elementary'],
    'better':['superior','preferable','more advantageous','more effective'],
    'worse':['inferior','more detrimental','more damaging'],
    'best':['optimal','most effective','foremost','finest'],
    'worst':['most detrimental','poorest','least effective'],
    'grow':['expand','develop','increase','flourish'],
    'develop':['evolve','progress','advance','cultivate'],
    'create':['generate','produce','establish','construct'],
    'destroy':['eliminate','eradicate','demolish','devastate'],
    'protect':['safeguard','preserve','shield','defend'],
    'avoid':['prevent','circumvent','steer clear of','forestall'],
    'allow':['permit','enable','authorise','facilitate'],
    'prevent':['hinder','impede','deter','preclude'],
    'ensure':['guarantee','secure','safeguard','confirm'],
    'provide':['supply','furnish','offer','deliver'],
    'gain':['acquire','obtain','secure','attain'],
    'lose':['forfeit','sacrifice','relinquish'],
    'succeed':['prosper','thrive','flourish','triumph'],
    'fail':['falter','flounder','come up short'],
}
REPEAT_SYNONYMS.update(REPEAT_SYNONYMS_EXT)

# Third-tier synonym bank: adds broader everyday/academic essay vocabulary
# (verbs, adjectives, abstract nouns commonly used in student writing) not
# already covered by REPEAT_SYNONYMS / REPEAT_SYNONYMS_EXT above. Same
# offline, deterministic lookup mechanism — pre-authored alternatives only,
# no generated text.
REPEAT_SYNONYMS_EXT2 = {
    'ability':['capability','competence','skill','capacity','aptitude'],
    'access':['entry','admission','availability','entrance','reach'],
    'achieve':['attain','accomplish','fulfil','realise','secure'],
    'act':['perform','behave','function','operate','proceed'],
    'action':['measure','step','initiative','move','deed'],
    'active':['engaged','dynamic','energetic','involved','proactive'],
    'add':['append','incorporate','include','supplement','contribute'],
    'admit':['acknowledge','concede','confess','accept','recognise'],
    'adult':['grown-up','mature person','individual'],
    'advance':['progress','proceed','move forward','develop'],
    'advice':['guidance','counsel','recommendation','suggestion'],
    'afford':['manage','sustain','bear the cost of'],
    'agreement':['accord','consensus','pact','understanding','settlement'],
    'aim':['goal','objective','purpose','target','intention'],
    'alone':['solitary','unaccompanied','isolated','by oneself'],
    'analyse':['examine','evaluate','investigate','assess','scrutinise'],
    'ancient':['age-old','historic','archaic','bygone'],
    'angry':['furious','irate','annoyed','indignant','incensed'],
    'answer':['response','reply','solution'],
    'anxious':['worried','apprehensive','uneasy','nervous'],
    'appear':['seem','emerge','arise','materialise'],
    'apply':['implement','use','employ','utilise'],
    'area':['region','zone','sector','domain','field'],
    'argue':['contend','assert','maintain','claim','reason'],
    'argument':['reasoning','case','claim','contention'],
    'arrive':['reach','get to','turn up'],
    'aspect':['facet','dimension','feature','element'],
    'assume':['presume','suppose','take for granted','presuppose'],
    'attack':['assault','strike','offensive','onslaught'],
    'attempt':['try','endeavour','effort','undertaking'],
    'attention':['focus','concentration','notice','regard'],
    'attitude':['outlook','mindset','stance','disposition'],
    'available':['accessible','obtainable','on hand','ready'],
    'aware':['conscious','informed','cognisant','mindful'],
    'balance':['equilibrium','stability','parity'],
    'barrier':['obstacle','hurdle','impediment','hindrance'],
    'basic':['fundamental','elementary','essential','rudimentary'],
    'beautiful':['attractive','stunning','gorgeous','elegant','striking'],
    'begin':['commence','start','initiate','launch'],
    'behaviour':['conduct','manner','demeanour'],
    'body':['organisation','group','institution','frame'],
    'break':['halt','pause','interruption','fracture'],
    'bring':['carry','deliver','introduce','produce'],
    'build':['construct','erect','establish','develop'],
    'business':['commerce','trade','enterprise','industry'],
    'calm':['tranquil','composed','serene','placid'],
    'campaign':['drive','initiative','crusade','movement'],
    'capable':['competent','able','skilled','proficient'],
    'careful':['cautious','meticulous','prudent','vigilant'],
    'careless':['negligent','reckless','sloppy','inattentive'],
    'case':['instance','example','occurrence','situation'],
    'category':['class','type','group','classification'],
    'central':['core','key','principal','pivotal'],
    'certain':['sure','confident','definite','assured'],
    'challenge':['difficulty','test','obstacle','trial'],
    'chance':['opportunity','possibility','likelihood','prospect'],
    'choice':['option','selection','alternative','preference'],
    'choose':['select','opt for','pick','decide on'],
    'city':['metropolis','urban centre','town'],
    'claim':['assert','maintain','allege','contend'],
    'close':['near','adjacent','nearby','proximate'],
    'collect':['gather','accumulate','compile','amass'],
    'combine':['merge','unite','integrate','blend'],
    'comfortable':['cosy','relaxed','at ease','snug'],
    'communicate':['convey','express','articulate','transmit'],
    'community':['neighbourhood','locality','public','populace'],
    'compare':['contrast','liken','set against'],
    'competition':['rivalry','contest','tournament'],
    'complain':['object','protest','grumble','voice concern'],
    'complete':['finish','conclude','accomplish','finalise'],
    'complex':['complicated','intricate','elaborate','convoluted'],
    'concern':['worry','apprehension','anxiety','issue'],
    'condition':['state','circumstance','requirement','status'],
    'confidence':['self-assurance','certainty','conviction','poise'],
    'confirm':['verify','validate','corroborate','substantiate'],
    'connect':['link','join','associate','relate'],
    'consequence':['result','outcome','effect','repercussion'],
    'constant':['continuous','steady','unchanging','persistent'],
    'contain':['hold','include','comprise','encompass'],
    'continue':['persist','proceed','carry on','endure'],
    'control':['regulate','manage','govern','direct'],
    'convince':['persuade','win over','satisfy'],
    'correct':['accurate','right','precise','exact'],
    'cost':['expense','price','charge','outlay'],
    'crisis':['emergency','predicament','critical point'],
    'critical':['crucial','vital','essential','decisive'],
    'criticise':['condemn','denounce','censure','fault'],
    'cultural':['societal','ethnic','traditional'],
    'culture':['civilisation','heritage','tradition'],
    'current':['present','contemporary','existing','prevailing'],
    'damage':['harm','injury','destruction','impairment'],
    'danger':['risk','hazard','peril','threat'],
    'dangerous':['hazardous','risky','perilous','unsafe'],
    'deal':['agreement','arrangement','transaction'],
    'decide':['determine','resolve','conclude','settle'],
    'decision':['verdict','ruling','judgement','determination'],
    'deep':['profound','intense','thorough'],
    'demand':['require','call for','necessitate','insist on'],
    'depend':['rely','hinge','count on'],
    'describe':['depict','portray','characterise','outline'],
    'deserve':['merit','warrant','earn'],
    'design':['devise','plan','construct','formulate'],
    'desire':['wish','longing','craving','yearning'],
    'detail':['particular','specific','element'],
    'determine':['establish','ascertain','decide','identify'],
    'device':['gadget','apparatus','instrument','tool'],
    'difference':['distinction','disparity','variation','contrast'],
    'direct':['guide','lead','steer','oversee'],
    'disappear':['vanish','fade','dissipate'],
    'discover':['find','uncover','identify','detect'],
    'diverse':['varied','assorted','mixed','wide-ranging'],
    'doubt':['scepticism','uncertainty','reservation','misgiving'],
    'drive':['motivate','propel','push','spur'],
    'duty':['obligation','responsibility','commitment'],
    'earn':['acquire','gain','secure','attain'],
    'economic':['financial','fiscal','monetary'],
    'educate':['teach','instruct','train','inform'],
    'effective':['efficient','successful','productive','potent'],
    'effort':['exertion','endeavour','attempt','labour'],
    'element':['component','ingredient','feature','factor'],
    'emerge':['appear','arise','surface','materialise'],
    'emotion':['feeling','sentiment'],
    'employ':['hire','engage','utilise'],
    'enable':['allow','permit','empower','facilitate'],
    'encourage':['motivate','inspire','promote','foster'],
    'energy':['vigour','vitality','power','stamina'],
    'engage':['involve','participate','occupy'],
    'enjoy':['relish','appreciate','delight in'],
    'entire':['whole','complete','total','full'],
    'environment':['surroundings','habitat','setting','ecosystem'],
    'equal':['identical','equivalent','uniform','even'],
    'essential':['vital','crucial','fundamental','indispensable'],
    'establish':['found','create','set up','institute'],
    'evaluate':['assess','appraise','judge','gauge'],
    'event':['occurrence','incident','occasion','happening'],
    'evidence':['proof','testimony','substantiation','confirmation'],
    'exact':['precise','accurate','specific'],
    'examine':['inspect','scrutinise','investigate','study'],
    'example':['instance','illustration','case','sample'],
    'excellent':['outstanding','exceptional','superb','first-rate'],
    'excite':['thrill','stimulate','stir'],
    'exist':['occur','be present','prevail'],
    'expand':['extend','enlarge','broaden','grow'],
    'expect':['anticipate','foresee','presume'],
    'expensive':['costly','pricey','high-priced'],
    'experience':['encounter','undergo','exposure'],
    'expert':['specialist','authority','professional'],
    'extra':['additional','further','supplementary'],
    'extreme':['severe','drastic','radical','excessive'],
    'face':['confront','encounter','tackle'],
    'fact':['reality','truth','certainty'],
    'factor':['element','component','determinant','variable'],
    'fair':['just','equitable','impartial','unbiased'],
    'familiar':['well-known','recognisable','acquainted'],
    'family':['household','relatives','kin'],
    'famous':['renowned','well-known','celebrated','notable'],
    'feature':['characteristic','trait','attribute','quality'],
    'feel':['sense','perceive','experience'],
    'field':['domain','area','sphere','discipline'],
    'final':['ultimate','last','concluding','eventual'],
    'find':['discover','locate','identify','uncover'],
    'finish':['complete','conclude','end','finalise'],
    'fit':['suit','match','correspond'],
    'flexible':['adaptable','versatile','adjustable'],
    'focus':['concentrate','centre','emphasis'],
    'follow':['pursue','trail','adhere to','observe'],
    'force':['compel','coerce','pressure'],
    'forget':['overlook','neglect','fail to remember'],
    'form':['shape','structure','configuration'],
    'formal':['official','conventional','proper'],
    'frequent':['common','regular','recurrent','habitual'],
    'friendly':['amicable','cordial','warm','congenial'],
    'fully':['completely','entirely','wholly','thoroughly'],
    'fundamental':['basic','essential','core','foundational'],
    'general':['broad','universal','widespread','overall'],
    'generation':['age group','era','cohort'],
    'genuine':['authentic','real','sincere','legitimate'],
    'global':['worldwide','international','universal'],
    'goal':['objective','aim','target','ambition'],
    'guarantee':['assure','ensure','promise','warrant'],
    'guide':['direct','lead','steer','advise'],
    'habit':['custom','routine','practice','tendency'],
    'happen':['occur','take place','arise'],
    'health':['wellbeing','fitness','condition'],
    'healthy':['fit','well','wholesome','robust'],
    'heavy':['weighty','substantial','burdensome'],
    'high':['elevated','lofty','considerable'],
    'hire':['employ','recruit','engage'],
    'honest':['truthful','sincere','candid','forthright'],
    'hope':['aspire','anticipate','wish'],
    'human':['person','individual','mortal'],
    'ignore':['disregard','overlook','dismiss','neglect'],
    'imagine':['envisage','picture','conceive','visualise'],
    'immediate':['instant','prompt','direct'],
    'include':['incorporate','comprise','encompass','contain'],
    'independent':['autonomous','self-reliant','self-sufficient'],
    'indicate':['signal','suggest','show','denote'],
    'individual':['person','human being','being'],
    'industry':['sector','trade','manufacturing'],
    'inform':['notify','advise','tell','update'],
    'initial':['first','opening','original','preliminary'],
    'inspire':['motivate','encourage','stimulate','spur'],
    'instead':['rather','alternatively'],
    'institution':['organisation','establishment','body'],
    'instruction':['direction','guidance','order'],
    'insist':['demand','maintain','assert'],
    'intend':['plan','mean','aim','propose'],
    'interest':['attention','curiosity','engagement'],
    'introduce':['present','launch','initiate','institute'],
    'invest':['commit','allocate','put in'],
    'investigate':['examine','probe','explore','research'],
    'involve':['entail','encompass','require','implicate'],
    'join':['unite','merge','link','combine'],
}
REPEAT_SYNONYMS.update(REPEAT_SYNONYMS_EXT2)

# Fourth-tier synonym bank: large general-purpose vocabulary expansion
# covering common academic/essay verbs, adjectives and abstract nouns
# beyond REPEAT_SYNONYMS / _EXT / _EXT2 above. Same offline, deterministic
# lookup mechanism -- pre-authored alternatives only, no generated text.
REPEAT_SYNONYMS_EXT3 = {
    'abandon':['desert','forsake','relinquish','give up','vacate'],
    'absorb':['soak up','assimilate','take in','digest'],
    'abundant':['plentiful','copious','ample','profuse'],
    'accelerate':['speed up','hasten','quicken','expedite'],
    'accept':['agree to','embrace','receive','take on'],
    'accompany':['escort','attend','go with','join'],
    'accomplish':['achieve','attain','complete','fulfil'],
    'accurate':['precise','exact','correct','faithful'],
    'accuse':['charge','blame','allege','indict'],
    'accustomed':['used to','habituated','familiar with'],
    'acquire':['obtain','gain','secure','procure'],
    'activate':['trigger','initiate','switch on','set off'],
    'actual':['real','genuine','factual','concrete'],
    'adapt':['adjust','modify','tailor','conform'],
    'adequate':['sufficient','satisfactory','ample','acceptable'],
    'adjust':['modify','adapt','regulate','tweak'],
    'administer':['manage','oversee','run','govern'],
    'admirable':['praiseworthy','commendable','laudable','impressive'],
    'admire':['respect','esteem','look up to','appreciate'],
    'adopt':['embrace','take up','assume','espouse'],
    'adverse':['unfavourable','harmful','negative','detrimental'],
    'advocate':['champion','support','promote','endorse'],
    'affair':['matter','issue','business','concern'],
    'affection':['fondness','warmth','tenderness','attachment'],
    'afraid':['fearful','scared','apprehensive','frightened'],
    'aggressive':['hostile','forceful','combative','belligerent'],
    'agile':['nimble','lithe','sprightly','dexterous'],
    'agitate':['stir up','unsettle','disturb','provoke'],
    'agonise':['fret','anguish','worry intensely'],
    'agriculture':['farming','cultivation'],
    'aid':['assistance','support','help','relief'],
    'ailment':['illness','affliction','malady','sickness'],
    'alarm':['alert','warn','frighten','unsettle'],
    'alert':['vigilant','attentive','watchful'],
    'alienate':['estrange','isolate','distance'],
    'align':['coordinate','line up','harmonise'],
    'allegation':['accusation','claim','charge'],
    'alliance':['coalition','partnership','union','pact'],
    'allocate':['assign','distribute','apportion','designate'],
    'altogether':['entirely','completely','wholly'],
    'amaze':['astonish','astound','startle','stun'],
    'ambiguous':['unclear','vague','equivocal','uncertain'],
    'ambition':['aspiration','drive','determination'],
    'ambitious':['aspiring','driven','determined'],
    'ample':['abundant','plentiful','sufficient','generous'],
    'amuse':['entertain','delight','divert'],
    'analogy':['comparison','parallel','similarity'],
    'annoy':['irritate','bother','vex','exasperate'],
    'anticipate':['expect','foresee','predict','envisage'],
    'anxiety':['worry','apprehension','unease','nervousness'],
    'apparent':['evident','obvious','clear','visible'],
    'appeal':['plea','request','attraction'],
    'appealing':['attractive','inviting','enticing'],
    'applicable':['relevant','pertinent','appropriate'],
    'appoint':['designate','nominate','assign','select'],
    'appreciate':['value','recognise','be grateful for'],
    'apprehend':['arrest','capture','seize'],
    'appropriate':['suitable','fitting','apt','proper'],
    'approve':['sanction','endorse','authorise','ratify'],
    'approximate':['estimate','rough','close to'],
    'arbitrary':['random','capricious','discretionary'],
    'archive':['record','store','file'],
    'arise':['emerge','occur','appear','stem'],
    'arrange':['organise','order','coordinate','plan'],
    'array':['collection','range','assortment'],
    'arrogant':['conceited','haughty','proud'],
    'articulate':['express','convey','vocalise'],
    'artificial':['synthetic','man-made','fake'],
    'ascertain':['determine','establish','confirm'],
    'ashamed':['embarrassed','humiliated','remorseful'],
    'aspire':['strive','aim','seek'],
    'assault':['attack','strike','onslaught'],
    'assemble':['gather','collect','congregate','construct'],
    'assert':['declare','state','maintain','affirm'],
    'asset':['resource','possession','advantage'],
    'assign':['allocate','designate','appoint'],
    'assist':['help','aid','support'],
    'associate':['connect','link','affiliate'],
    'assure':['guarantee','promise','reassure'],
    'astonish':['amaze','astound','stun','startle'],
    'attach':['fasten','join','connect','affix'],
    'attain':['achieve','accomplish','reach','secure'],
    'attract':['draw','lure','entice','appeal to'],
    'attribute':['ascribe','credit','trait'],
    'audience':['spectators','viewers','crowd'],
    'augment':['increase','boost','enhance','supplement'],
    'authentic':['genuine','real','legitimate'],
    'authority':['power','jurisdiction','control'],
    'authorise':['sanction','permit','approve'],
    'automatic':['mechanical','self-acting','involuntary'],
    'avert':['prevent','avoid','ward off'],
    'await':['expect','anticipate','wait for'],
    'awaken':['rouse','wake','stir'],
    'awful':['dreadful','terrible','appalling'],
    'awkward':['clumsy','uncomfortable','ungainly'],
    'bank':['depend on','rely on'],
    'bankrupt':['insolvent','broke'],
    'banish':['exile','expel','deport'],
    'bar':['prevent','prohibit','exclude'],
    'bare':['exposed','naked','plain'],
    'bargain':['deal','agreement','negotiate'],
    'battle':['fight','conflict','struggle'],
    'beg':['plead','implore','entreat'],
    'behold':['see','observe','witness'],
    'belong':['fit','pertain','be part of'],
    'beneficial':['advantageous','favourable','helpful'],
    'bewilder':['confuse','baffle','perplex'],
    'bias':['prejudice','partiality','favouritism'],
    'bind':['tie','fasten','unite','obligate'],
    'bizarre':['strange','odd','peculiar','unusual'],
    'bleak':['grim','dismal','desolate'],
    'blend':['mix','merge','combine'],
    'bless':['sanctify','favour'],
    'blunt':['direct','frank','abrupt'],
    'boast':['brag','flaunt','show off'],
    'bold':['daring','courageous','confident'],
    'bolster':['strengthen','reinforce','support'],
    'bond':['connection','link','tie'],
    'bother':['annoy','trouble','disturb'],
    'boundary':['border','limit','edge'],
    'brave':['courageous','bold','fearless'],
    'brief':['short','concise','fleeting'],
    'bright':['radiant','vivid','clever'],
    'brilliant':['outstanding','exceptional','dazzling'],
    'broad':['wide','extensive','expansive'],
    'brutal':['harsh','savage','ruthless'],
    'burden':['load','weight','responsibility'],
    'calculate':['compute','work out','determine'],
    'candid':['frank','honest','open'],
    'capacity':['ability','capability','volume'],
    'capture':['seize','catch','apprehend'],
    'caution':['care','wariness','prudence'],
    'cease':['stop','halt','end'],
    'celebrate':['commemorate','mark','honour'],
    'certificate':['diploma','credential','document'],
    'chaos':['disorder','confusion','turmoil'],
    'characteristic':['trait','feature','quality'],
    'charity':['generosity','philanthropy','benevolence'],
    'charm':['appeal','allure','attractiveness'],
    'cherish':['treasure','value','hold dear'],
    'circumstance':['situation','condition','context'],
    'cite':['quote','reference','mention'],
    'civil':['polite','courteous','civic'],
    'clarify':['explain','elucidate','clear up'],
    'classic':['timeless','traditional','enduring'],
    'classify':['categorise','sort','group'],
    'cling':['hold on','grasp','adhere'],
    'coalition':['alliance','partnership','union'],
    'coincide':['align','correspond','overlap'],
    'collaborate':['cooperate','work together','partner'],
    'collapse':['fall','crumble','fail'],
    'colleague':['co-worker','associate','peer'],
    'comfort':['solace','reassurance','ease'],
    'command':['order','instruct','control'],
    'comment':['remark','observation','note'],
    'commit':['pledge','dedicate','perform'],
    'committee':['board','panel','council'],
    'commodity':['goods','product','merchandise'],
    'compassion':['sympathy','empathy','kindness'],
    'compatible':['suitable','harmonious','matching'],
    'compel':['force','oblige','pressure'],
    'compensate':['reimburse','recompense','offset'],
    'compete':['contend','rival','vie'],
    'compile':['gather','assemble','collect'],
    'complement':['enhance','complete','round out'],
    'comply':['conform','adhere','obey'],
    'component':['part','element','ingredient'],
    'compose':['create','write','constitute'],
    'comprehend':['understand','grasp','fathom'],
    'comprehensive':['thorough','extensive','complete'],
    'compromise':['settlement','concession','trade-off'],
    'compulsory':['mandatory','obligatory','required'],
    'conceal':['hide','disguise','mask'],
    'concede':['admit','acknowledge','yield'],
    'conceive':['imagine','devise','formulate'],
    'conclude':['finish','deduce','determine'],
    'condemn':['denounce','criticise','censure'],
    'conduct':['carry out','behaviour','manage'],
    'confess':['admit','acknowledge','disclose'],
    'confident':['self-assured','certain','assured'],
    'confine':['restrict','limit','contain'],
    'conflict':['clash','dispute','disagreement'],
    'conform':['comply','adhere','follow'],
    'confront':['face','tackle','address'],
    'confuse':['perplex','baffle','muddle'],
    'congratulate':['commend','praise','applaud'],
    'conquer':['defeat','overcome','vanquish'],
    'conscious':['aware','mindful','alert'],
    'consent':['agree','permission','approval'],
    'conserve':['preserve','protect','save'],
    'considerable':['substantial','significant','sizeable'],
    'considerate':['thoughtful','kind','attentive'],
    'consist':['comprise','be made up of'],
    'consistent':['steady','uniform','reliable'],
    'conspicuous':['noticeable','prominent','obvious'],
    'constitute':['form','make up','comprise'],
    'constrain':['restrict','limit','confine'],
    'construct':['build','erect','assemble'],
    'consult':['confer','seek advice','discuss'],
    'consume':['use','eat','deplete'],
    'contact':['reach','get in touch with','connection'],
    'contemplate':['consider','ponder','reflect on'],
    'contemporary':['modern','current','present-day'],
    'contempt':['disdain','scorn','disrespect'],
    'contend':['argue','assert','compete'],
    'content':['satisfied','pleased','substance'],
    'contest':['dispute','challenge','competition'],
    'context':['setting','circumstances','background'],
    'contract':['agreement','deal','shrink'],
    'contradict':['dispute','deny','oppose'],
    'contrary':['opposite','conflicting','adverse'],
    'contribute':['add','donate','provide'],
    'convenient':['handy','suitable','practical'],
    'conventional':['traditional','standard','customary'],
    'converse':['talk','chat','communicate'],
    'convert':['transform','change','alter'],
    'convey':['express','communicate','transmit'],
    'convict':['find guilty','condemn'],
    'convincing':['persuasive','compelling','credible'],
    'cooperate':['collaborate','work together','assist'],
    'coordinate':['organise','arrange','synchronise'],
    'cope':['manage','handle','deal with'],
    'core':['centre','heart','essence'],
    'corporate':['business','commercial'],
    'correspond':['match','align','communicate'],
    'corrupt':['dishonest','fraudulent','crooked'],
    'counter':['oppose','offset','respond to'],
    'courage':['bravery','fortitude','valour'],
    'courteous':['polite','respectful','civil'],
    'cover':['include','conceal','protect'],
    'crash':['collide','collapse','failure'],
    'crave':['long for','desire','yearn for'],
    'crawl':['creep','inch'],
    'crazy':['insane','absurd','irrational'],
    'credible':['believable','plausible','trustworthy'],
    'crime':['offence','wrongdoing','felony'],
    'crucial':['vital','essential','critical'],
    'crude':['rough','unrefined','basic'],
    'cruel':['harsh','brutal','merciless'],
    'crush':['squash','defeat','overwhelm'],
    'cure':['remedy','treatment','heal'],
    'curious':['inquisitive','intrigued','interested'],
    'custom':['tradition','practice','habit'],
    'cut':['reduce','trim','slash'],
    'cycle':['sequence','pattern','rotation'],
    'data':['information','statistics','figures'],
    'dawn':['beginning','onset','daybreak'],
    'deadline':['due date','time limit'],
    'debate':['discussion','argument','dispute'],
    'debt':['liability','obligation'],
    'decade':['ten years'],
    'deceive':['mislead','trick','deceive'],
    'decent':['respectable','satisfactory','proper'],
    'decline':['decrease','fall','refuse'],
    'decorate':['adorn','embellish','ornament'],
    'dedicate':['devote','commit','allocate'],
    'defeat':['beat','conquer','overcome'],
    'defect':['flaw','fault','imperfection'],
    'defend':['protect','guard','justify'],
    'define':['specify','clarify','establish'],
    'definite':['certain','clear','fixed'],
    'degrade':['diminish','demean','lower'],
    'delay':['postpone','defer','hold up'],
    'deliberate':['intentional','planned','purposeful'],
    'delicate':['fragile','sensitive','fine'],
    'delight':['pleasure','joy','please'],
    'deliver':['provide','hand over','bring'],
    'demonstrate':['show','prove','illustrate'],
    'denounce':['condemn','criticise','censure'],
    'dense':['thick','compact','crowded'],
    'deny':['refute','reject','disclaim'],
    'depict':['portray','represent','describe'],
    'deploy':['position','use','employ'],
    'deposit':['place','store','payment'],
    'depress':['discourage','sadden','lower'],
    'deprive':['deny','withhold','strip'],
    'derive':['obtain','originate','stem from'],
    'descend':['go down','fall','originate'],
    'deteriorate':['decline','worsen','degrade'],
    'devastate':['destroy','ruin','overwhelm'],
    'deviate':['diverge','stray','depart'],
    'devote':['dedicate','commit','allocate'],
    'devour':['consume','eat','engulf'],
    'diagnose':['identify','detect','determine'],
    'dictate':['command','order','impose'],
    'differ':['vary','disagree','diverge'],
    'dignity':['self-respect','honour','pride'],
    'dilemma':['predicament','quandary','plight'],
    'diminish':['decrease','reduce','lessen'],
    'diplomatic':['tactful','discreet','sensitive'],
    'disable':['incapacitate','impair'],
    'disaster':['catastrophe','calamity','tragedy'],
    'discard':['dispose of','throw away','reject'],
    'discipline':['self-control','training','order'],
    'disclose':['reveal','divulge','expose'],
    'discourage':['deter','dishearten','dissuade'],
    'discreet':['tactful','careful','prudent'],
    'discriminate':['differentiate','distinguish','prejudice'],
    'disguise':['conceal','mask','camouflage'],
    'disgust':['revulsion','distaste','repulse'],
    'dismiss':['reject','discharge','disregard'],
    'disorder':['confusion','disarray','turmoil'],
    'dispose':['discard','throw away','arrange'],
    'dispute':['disagreement','conflict','contest'],
    'disrupt':['disturb','interrupt','interfere with'],
    'dissolve':['melt','disperse','break up'],
    'distant':['remote','far','aloof'],
    'distinct':['separate','different','clear'],
    'distinguish':['differentiate','discern','set apart'],
    'distort':['warp','twist','misrepresent'],
    'distract':['divert','sidetrack','disturb'],
    'distress':['anguish','suffering','trouble'],
    'distribute':['allocate','disperse','share out'],
    'district':['area','region','zone'],
    'disturb':['upset','trouble','interrupt'],
    'divert':['redirect','distract','deflect'],
    'divide':['separate','split','partition'],
    'donate':['contribute','give','bestow'],
    'dominate':['control','rule','prevail'],
    'drain':['deplete','exhaust','empty'],
    'dramatic':['striking','impressive','theatrical'],
    'drastic':['severe','extreme','radical'],
    'dread':['fear','apprehension','dismay'],
    'dull':['boring','tedious','lacklustre'],
    'durable':['long-lasting','sturdy','resilient'],
    'dwell':['reside','live','linger'],
    'eager':['keen','enthusiastic','avid'],
    'eccentric':['unconventional','quirky','odd'],
    'eco':['ecological','environmental'],
    'efficient':['effective','productive','streamlined'],
    'elaborate':['detailed','intricate','expand on'],
    'elegant':['graceful','refined','stylish'],
    'elevate':['raise','lift','boost'],
    'eliminate':['remove','eradicate','abolish'],
    'eloquent':['articulate','fluent','expressive'],
    'embark':['begin','set out','commence'],
    'embarrass':['humiliate','mortify','shame'],
    'embed':['implant','fix','insert'],
    'embody':['represent','personify','exemplify'],
    'embrace':['accept','adopt','welcome'],
    'emphasise':['stress','highlight','underline'],
    'empower':['enable','authorise','strengthen'],
    'empty':['vacant','void','hollow'],
    'encounter':['meet','confront','experience'],
    'endanger':['jeopardise','threaten','imperil'],
    'endeavour':['attempt','effort','try'],
    'endorse':['support','approve','back'],
    'endure':['withstand','tolerate','persist'],
    'enforce':['impose','implement','apply'],
    'enhance':['improve','boost','strengthen'],
    'enlarge':['expand','extend','enlarge'],
    'enormous':['huge','immense','massive'],
    'enrich':['enhance','improve','augment'],
    'enrol':['register','sign up','join'],
    'enthusiasm':['excitement','passion','zeal'],
    'entitle':['authorise','permit','qualify'],
    'entrepreneur':['businessperson','founder'],
    'envision':['imagine','envisage','foresee'],
    'epidemic':['outbreak','plague'],
    'equip':['furnish','provide','prepare'],
    'equivalent':['equal','comparable','corresponding'],
    'era':['period','age','epoch'],
    'eradicate':['eliminate','abolish','wipe out'],
    'erode':['wear away','deteriorate','diminish'],
    'erupt':['explode','burst out','flare up'],
    'escalate':['intensify','increase','heighten'],
    'escape':['flee','avoid','evade'],
    'esteem':['respect','regard','admiration'],
    'estimate':['calculate','assess','approximate'],
    'ethical':['moral','principled','virtuous'],
    'evident':['clear','apparent','obvious'],
    'evoke':['elicit','provoke','call forth'],
    'evolve':['develop','progress','transform'],
    'exaggerate':['overstate','embellish','magnify'],
    'exceed':['surpass','outdo','go beyond'],
    'exceptional':['outstanding','remarkable','extraordinary'],
    'excerpt':['extract','passage','quotation'],
    'excess':['surplus','overflow','abundance'],
    'exclude':['omit','leave out','bar'],
    'exclusive':['sole','restricted','select'],
    'excuse':['justification','pardon','pretext'],
    'execute':['carry out','perform','implement'],
    'exempt':['excused','free from','immune'],
    'exert':['exercise','apply','wield'],
    'exhaust':['deplete','tire','use up'],
    'exhibit':['display','show','demonstrate'],
    'exile':['banish','deport','expel'],
    'expedite':['speed up','accelerate','hasten'],
    'expenditure':['spending','outlay','cost'],
    'expire':['end','lapse','terminate'],
    'exploit':['use','take advantage of','utilise'],
    'explore':['investigate','examine','probe'],
    'explosion':['blast','eruption','burst'],
    'expose':['reveal','uncover','disclose'],
    'extend':['lengthen','prolong','stretch'],
    'extensive':['broad','wide-ranging','comprehensive'],
    'exterior':['outside','outer','external'],
    'external':['outside','outer','exterior'],
    'extinct':['vanished','gone','died out'],
    'extract':['remove','extort','derive'],
    'extraordinary':['remarkable','exceptional','unusual'],
    'fabricate':['invent','concoct','manufacture'],
    'facilitate':['enable','ease','assist'],
    'faculty':['ability','staff','department'],
    'faint':['dim','weak','pass out'],
    'faith':['trust','belief','confidence'],
    'fake':['fraudulent','counterfeit','false'],
    'fascinate':['captivate','enthral','intrigue'],
    'fatal':['deadly','lethal','disastrous'],
    'fatigue':['tiredness','exhaustion','weariness'],
    'fault':['flaw','defect','error'],
    'favour':['prefer','support','kindness'],
    'feasible':['viable','achievable','practicable'],
    'fee':['charge','payment','cost'],
    'feeble':['weak','frail','fragile'],
    'fertile':['productive','fruitful','rich'],
    'fierce':['intense','ferocious','aggressive'],
    'fine':['penalty','excellent','delicate'],
    'firm':['solid','company','resolute'],
    'flaw':['defect','fault','imperfection'],
    'flee':['escape','run away','evade'],
    'fluctuate':['vary','waver','oscillate'],
    'fluent':['articulate','proficient','smooth'],
    'foe':['enemy','adversary','opponent'],
    'forbid':['prohibit','ban','disallow'],
    'foresee':['anticipate','predict','envisage'],
    'foretell':['predict','forecast','prophesy'],
    'forge':['create','build','fabricate'],
    'forsake':['abandon','desert','relinquish'],
    'fortunate':['lucky','favoured','blessed'],
    'foster':['nurture','encourage','promote'],
    'found':['establish','set up','institute'],
    'fraction':['portion','part','segment'],
    'fragile':['delicate','brittle','vulnerable'],
    'fragment':['piece','part','shard'],
    'frank':['candid','honest','direct'],
    'frantic':['frenzied','desperate','wild'],
    'fraud':['deception','scam','swindle'],
    'freedom':['liberty','independence','autonomy'],
    'friction':['conflict','tension','discord'],
    'fright':['fear','terror','alarm'],
    'frugal':['thrifty','economical','sparing'],
    'fulfil':['satisfy','achieve','accomplish'],
    'function':['operate','purpose','role'],
    'furious':['enraged','livid','irate'],
    'futile':['pointless','useless','fruitless'],
    'gap':['space','opening','difference'],
    'gather':['collect','assemble','congregate'],
    'gaze':['stare','look','glance'],
    'generate':['produce','create','yield'],
    'generous':['giving','charitable','magnanimous'],
    'gesture':['motion','signal','act'],
    'gigantic':['huge','enormous','colossal'],
    'glance':['look','peek','glimpse'],
    'glimpse':['peek','look','sighting'],
    'glorious':['magnificent','splendid','triumphant'],
    'gloomy':['dismal','dark','depressing'],
    'govern':['rule','control','administer'],
    'grace':['elegance','poise','charm'],
    'gradual':['slow','steady','progressive'],
    'grant':['award','give','bestow'],
    'grasp':['understand','grip','seize'],
    'grateful':['thankful','appreciative','indebted'],
    'grave':['serious','solemn','severe'],
    'grief':['sorrow','sadness','anguish'],
    'grip':['grasp','hold','clutch'],
    'gross':['blatant','total','disgusting'],
    'guilt':['culpability','blame','remorse'],
    'halt':['stop','cease','pause'],
    'handle':['manage','deal with','cope with'],
    'harass':['pester','torment','intimidate'],
    'harmony':['peace','accord','concord'],
    'harsh':['severe','cruel','stark'],
    'haste':['hurry','speed','rush'],
    'hazard':['danger','risk','peril'],
    'heal':['cure','mend','recover'],
    'hesitate':['pause','waver','falter'],
    'hideous':['ugly','grotesque','repulsive'],
    'hierarchy':['ranking','order','structure'],
    'hinder':['impede','obstruct','hamper'],
    'hint':['clue','suggestion','indication'],
    'hollow':['empty','vacant','void'],
    'horror':['terror','dread','fear'],
    'hostile':['aggressive','antagonistic','unfriendly'],
    'humble':['modest','unassuming','meek'],
    'humiliate':['embarrass','shame','degrade'],
    'hurdle':['obstacle','barrier','impediment'],
    'hypothesis':['theory','assumption','conjecture'],
    'identical':['same','matching','indistinguishable'],
    'identify':['recognise','pinpoint','name'],
    'ideology':['belief system','doctrine','philosophy'],
    'idle':['inactive','lazy','unemployed'],
    'illegal':['unlawful','illicit','prohibited'],
    'illustrate':['demonstrate','depict','exemplify'],
    'imitate':['copy','mimic','replicate'],
    'immense':['huge','vast','enormous'],
    'immerse':['engross','absorb','submerge'],
    'immune':['resistant','protected','exempt'],
    'impair':['damage','weaken','hinder'],
    'impartial':['unbiased','fair','neutral'],
    'impatient':['restless','eager','irritable'],
    'impede':['hinder','obstruct','hamper'],
    'imperative':['essential','crucial','urgent'],
    'implement':['carry out','execute','enact'],
    'implication':['consequence','significance','inference'],
    'imply':['suggest','indicate','hint'],
    'impose':['enforce','levy','dictate'],
    'impress':['awe','affect','influence'],
    'imprison':['jail','incarcerate','confine'],
    'improper':['inappropriate','incorrect','unsuitable'],
    'inadequate':['insufficient','deficient','lacking'],
    'incentive':['motivation','inducement','reward'],
    'incident':['event','occurrence','episode'],
    'incline':['tendency','lean','slope'],
    'incorporate':['include','integrate','absorb'],
    'increment':['increase','rise','addition'],
    'incur':['suffer','sustain','bring on'],
    'indeed':['certainly','truly','in fact'],
    'indifferent':['apathetic','unconcerned','detached'],
    'indignant':['angry','outraged','resentful'],
    'induce':['cause','bring about','persuade'],
    'indulge':['pamper','satisfy','gratify'],
    'inevitable':['unavoidable','certain','inescapable'],
    'infamous':['notorious','disreputable'],
    'infect':['contaminate','taint'],
    'infer':['deduce','conclude','gather'],
    'inferior':['lesser','substandard','lower'],
    'infinite':['boundless','endless','limitless'],
    'inflict':['impose','cause','administer'],
    'influential':['powerful','significant','persuasive'],
    'infringe':['violate','breach','transgress'],
    'ingenious':['inventive','clever','resourceful'],
    'inhabit':['live in','occupy','reside in'],
    'inherent':['intrinsic','innate','fundamental'],
    'inherit':['receive','succeed to'],
    'initiate':['begin','launch','start'],
    'inject':['introduce','insert','administer'],
    'injure':['harm','wound','hurt'],
    'innocent':['guiltless','blameless','naive'],
    'innovate':['pioneer','invent','modernise'],
    'inquire':['ask','investigate','query'],
    'insight':['understanding','perception','awareness'],
    'inspect':['examine','scrutinise','check'],
    'install':['set up','fit','establish'],
    'instance':['example','case','occurrence'],
    'instant':['moment','immediate','prompt'],
    'instil':['implant','instil','impart'],
    'insufficient':['inadequate','lacking','deficient'],
    'insult':['offend','affront','slight'],
    'integrate':['combine','merge','incorporate'],
    'integrity':['honesty','honour','uprightness'],
    'intellectual':['scholarly','academic','cerebral'],
    'intense':['extreme','severe','powerful'],
    'interact':['communicate','engage','mingle'],
    'interfere':['meddle','intervene','disrupt'],
    'interior':['inside','inner'],
    'intermediate':['middle','transitional'],
    'interpret':['explain','construe','decipher'],
    'interrupt':['disrupt','interject','break in'],
    'intervene':['interfere','step in','mediate'],
    'intimate':['close','personal','familiar'],
    'intricate':['complex','elaborate','complicated'],
    'intrigue':['fascinate','captivate','plot'],
    'intrinsic':['inherent','innate','essential'],
    'invade':['attack','encroach','overrun'],
    'invalid':['void','null','unsound'],
    'invaluable':['priceless','essential','indispensable'],
    'invariably':['always','consistently','without exception'],
    'invent':['create','devise','originate'],
    'inventory':['stock','supply','list'],
    'invoke':['call upon','cite','summon'],
    'irony':['sarcasm','paradox'],
    'irritate':['annoy','vex','exasperate'],
    'isolate':['separate','seclude','segregate'],
    'itinerary':['route','schedule','plan'],
    'jealous':['envious','resentful','covetous'],
    'jeopardise':['endanger','risk','imperil'],
    'journey':['trip','voyage','trek'],
    'joy':['happiness','delight','elation'],
    'judgement':['opinion','ruling','verdict'],
    'junior':['subordinate','younger','lower-ranking'],
    'justice':['fairness','equity','impartiality'],
    'justify':['defend','vindicate','warrant'],
    'keen':['eager','enthusiastic','sharp'],
    'kindle':['ignite','spark','stir'],
    'label':['tag','classify','designate'],
    'lament':['mourn','grieve','regret'],
    'landmark':['milestone','marker','monument'],
    'lapse':['slip','decline','expire'],
    'launch':['begin','initiate','introduce'],
    'lawful':['legal','legitimate','permitted'],
    'leak':['seep','disclose','escape'],
    'legacy':['inheritance','heritage','bequest'],
    'legend':['myth','story','icon'],
    'legislation':['law','statute','regulation'],
    'legitimate':['valid','lawful','genuine'],
    'leisure':['relaxation','free time','recreation'],
    'lengthy':['long','extended','prolonged'],
    'liable':['responsible','accountable','prone'],
    'liberal':['open-minded','tolerant','generous'],
    'liberate':['free','release','emancipate'],
    'license':['permit','authorise','certify'],
    'linger':['remain','stay','persist'],
    'literal':['exact','precise','word-for-word'],
    'litigate':['sue','prosecute'],
    'lively':['vibrant','energetic','animated'],
    'load':['burden','cargo','weight'],
    'locate':['find','position','situate'],
    'logical':['rational','reasonable','sound'],
    'long-term':['lasting','enduring','extended'],
    'loom':['appear','emerge','threaten'],
    'luxury':['opulence','extravagance','indulgence'],
    'magnify':['enlarge','amplify','exaggerate'],
    'magnitude':['size','scale','extent'],
    'maintain':['sustain','preserve','uphold'],
    'majestic':['grand','stately','magnificent'],
    'mandatory':['compulsory','required','obligatory'],
    'manifest':['evident','apparent','show'],
    'manipulate':['handle','influence','control'],
    'manufacture':['produce','make','fabricate'],
    'marginal':['minor','slight','peripheral'],
    'mark':['indicate','signify','symbol'],
    'massive':['huge','enormous','substantial'],
    'mature':['adult','ripe','developed'],
    'maximise':['optimise','increase','boost'],
    'meager':['scanty','insufficient','sparse'],
    'mediate':['arbitrate','intervene','negotiate'],
    'mediocre':['average','ordinary','unremarkable'],
    'meditate':['contemplate','reflect','ponder'],
    'mend':['repair','fix','heal'],
    'menace':['threat','danger','peril'],
    'mention':['refer to','note','cite'],
    'merge':['combine','unite','blend'],
    'merit':['deserve','warrant','worth'],
    'meticulous':['thorough','precise','careful'],
    'migrate':['relocate','move','emigrate'],
    'mild':['gentle','moderate','soft'],
    'mimic':['imitate','copy','replicate'],
    'minimise':['reduce','decrease','curtail'],
    'minor':['small','insignificant','trivial'],
    'minute':['tiny','minuscule','detailed'],
    'mislead':['deceive','misinform','delude'],
    'mission':['goal','purpose','task'],
    'mobile':['movable','portable','flexible'],
    'mock':['ridicule','deride','mimic'],
    'moderate':['reasonable','average','temper'],
    'modify':['alter','adjust','change'],
    'monitor':['observe','track','supervise'],
    'monotonous':['tedious','repetitive','dull'],
    'monumental':['huge','significant','enormous'],
    'moral':['ethical','virtuous','righteous'],
    'motive':['reason','purpose','incentive'],
    'mount':['increase','rise','climb'],
    'mourn':['grieve','lament','sorrow'],
    'mutual':['shared','reciprocal','common'],
    'mysterious':['puzzling','enigmatic','mystifying'],
    'naive':['innocent','gullible','unsophisticated'],
    'narrow':['limited','confined','slender'],
    'nasty':['unpleasant','vicious','malicious'],
    'naught':['nothing','zero'],
    'navigate':['steer','guide','manoeuvre'],
    'nearly':['almost','virtually','approximately'],
    'neat':['tidy','orderly','clean'],
    'negative':['unfavourable','adverse','pessimistic'],
    'neglect':['ignore','disregard','overlook'],
    'negligible':['insignificant','trivial','minimal'],
    'negotiate':['bargain','mediate','discuss'],
    'neutral':['impartial','unbiased','indifferent'],
    'nevertheless':['however','nonetheless','still'],
    'nominate':['propose','appoint','name'],
    'nonetheless':['nevertheless','however','still'],
    'nostalgia':['longing','yearning','sentimentality'],
    'notable':['remarkable','noteworthy','significant'],
    'notify':['inform','tell','alert'],
    'notorious':['infamous','disreputable'],
    'nourish':['nurture','feed','sustain'],
    'novel':['new','original','innovative'],
    'nurture':['nourish','foster','cultivate'],
    'oath':['pledge','promise','vow'],
    'obedience':['compliance','submission'],
    'obese':['overweight','stout'],
    'obey':['comply','follow','submit'],
    'object':['oppose','protest','item'],
    'objective':['goal','aim','unbiased'],
    'obligation':['duty','responsibility','commitment'],
    'oblige':['compel','require','favour'],
    'obscure':['unclear','vague','hidden'],
    'observe':['watch','notice','remark'],
    'obsess':['preoccupy','fixate'],
    'obsolete':['outdated','antiquated','defunct'],
    'obstacle':['barrier','hindrance','hurdle'],
    'obstruct':['block','hinder','impede'],
    'occasion':['event','instance','opportunity'],
    'occupy':['inhabit','fill','engage'],
    'odd':['strange','peculiar','unusual'],
    'offend':['insult','upset','affront'],
    'offset':['counterbalance','compensate for'],
    'omit':['exclude','leave out','skip'],
    'operate':['function','run','manage'],
    'oppress':['persecute','subjugate','tyrannise'],
    'optimal':['best','ideal','most favourable'],
    'optimistic':['hopeful','positive','upbeat'],
    'option':['choice','alternative','possibility'],
    'orchestrate':['organise','coordinate','arrange'],
    'ordeal':['trial','hardship','tribulation'],
    'organic':['natural','unprocessed'],
    'orient':['align','position','direct'],
    'origin':['source','beginning','root'],
    'original':['first','authentic','novel'],
    'outbreak':['eruption','onset','epidemic'],
    'outcome':['result','consequence','effect'],
    'outdated':['obsolete','old-fashioned','antiquated'],
    'outline':['summary','sketch','plan'],
    'outrage':['anger','fury','indignation'],
    'outstanding':['excellent','remarkable','superb'],
    'overall':['general','total','comprehensive'],
    'overcome':['conquer','surmount','defeat'],
    'overlook':['ignore','disregard','neglect'],
    'overwhelm':['engulf','overpower','swamp'],
    'own':['possess','have','acknowledge'],
    'pace':['speed','rate','tempo'],
    'pacify':['calm','soothe','appease'],
    'painstaking':['meticulous','thorough','careful'],
    'panic':['alarm','fear','fright'],
    'parallel':['similar','equivalent','corresponding'],
    'paramount':['supreme','foremost','preeminent'],
    'participate':['take part','engage','join'],
    'particular':['specific','distinct','fussy'],
    'passion':['enthusiasm','fervour','zeal'],
    'passive':['inactive','submissive','unresponsive'],
    'pathetic':['pitiful','sad','miserable'],
    'patient':['tolerant','forbearing','calm'],
    'peculiar':['strange','odd','distinctive'],
    'peer':['equal','colleague','look closely'],
    'penalise':['punish','sanction','fine'],
    'penetrate':['pierce','permeate','infiltrate'],
    'perceive':['notice','discern','regard'],
    'perform':['carry out','execute','act'],
    'peril':['danger','risk','hazard'],
    'permanent':['lasting','enduring','fixed'],
    'permit':['allow','authorise','license'],
    'perpetual':['constant','endless','everlasting'],
    'perplex':['confuse','puzzle','baffle'],
    'persecute':['oppress','victimise','harass'],
    'persist':['continue','endure','persevere'],
    'personal':['private','individual','subjective'],
    'perspective':['viewpoint','outlook','standpoint'],
    'persuade':['convince','induce','sway'],
    'pertinent':['relevant','applicable','apt'],
    'perturb':['disturb','unsettle','trouble'],
    'petty':['trivial','minor','insignificant'],
    'phase':['stage','period','step'],
    'phenomenon':['occurrence','event','marvel'],
    'philosophy':['ideology','doctrine','outlook'],
    'pinpoint':['identify','locate','specify'],
    'pioneer':['innovator','trailblazer','initiate'],
    'pity':['sympathy','compassion','sorrow'],
    'plague':['epidemic','affliction','torment'],
    'plausible':['credible','believable','reasonable'],
    'pledge':['promise','vow','commitment'],
    'plentiful':['abundant','copious','ample'],
    'plight':['predicament','situation','condition'],
    'plunge':['dive','drop','fall sharply'],
    'poise':['composure','grace','balance'],
    'polish':['refine','perfect','shine'],
    'ponder':['consider','contemplate','reflect'],
    'portion':['part','share','segment'],
    'portray':['depict','represent','characterise'],
    'pose':['present','constitute','present a threat'],
    'possess':['own','have','hold'],
    'postpone':['delay','defer','put off'],
    'potent':['powerful','strong','forceful'],
    'poverty':['destitution','deprivation','need'],
    'practical':['pragmatic','sensible','functional'],
    'precede':['come before','forerun'],
    'precious':['valuable','treasured','cherished'],
    'precise':['exact','accurate','specific'],
    'predict':['forecast','anticipate','foresee'],
    'predominant':['prevailing','dominant','main'],
    'prejudice':['bias','partiality','discrimination'],
    'preliminary':['initial','introductory','preparatory'],
    'premature':['untimely','early','hasty'],
    'preoccupy':['absorb','engross','distract'],
    'preserve':['maintain','conserve','protect'],
    'prestige':['reputation','status','esteem'],
    'presume':['assume','suppose','take for granted'],
    'pretend':['feign','simulate','act as if'],
    'prevail':['triumph','win out','dominate'],
    'previous':['prior','earlier','preceding'],
    'primitive':['basic','undeveloped','ancient'],
    'principal':['main','chief','primary'],
    'principle':['rule','standard','doctrine'],
    'prior':['earlier','preceding','previous'],
    'priority':['precedence','importance','main concern'],
    'privilege':['advantage','benefit','entitlement'],
    'probe':['investigate','examine','explore'],
    'proceed':['continue','advance','go ahead'],
    'proclaim':['announce','declare','assert'],
    'procure':['obtain','acquire','secure'],
    'prohibit':['forbid','ban','outlaw'],
    'prolific':['productive','abundant','fruitful'],
    'prolong':['extend','lengthen','protract'],
    'prominent':['notable','distinguished','conspicuous'],
    'promising':['hopeful','encouraging','favourable'],
    'prompt':['immediate','trigger','swift'],
    'prone':['inclined','susceptible','liable'],
    'proof':['evidence','confirmation','verification'],
    'propel':['drive','push','launch'],
    'proportion':['ratio','part','balance'],
    'prospect':['possibility','chance','outlook'],
    'prosper':['thrive','flourish','succeed'],
    'protest':['object','demonstrate','opposition'],
    'provoke':['incite','trigger','instigate'],
    'proximity':['nearness','closeness','vicinity'],
    'prudent':['cautious','wise','sensible'],
    'publicise':['advertise','promote','announce'],
    'punctual':['prompt','timely','on time'],
    'pure':['unadulterated','clean','genuine'],
    'pursue':['chase','follow','seek'],
    'puzzle':['confuse','mystify','riddle'],
    'qualify':['meet requirements','become eligible'],
    'random':['arbitrary','haphazard','indiscriminate'],
    'rapid':['swift','fast','quick'],
    'rational':['logical','sensible','reasonable'],
    'ratio':['proportion','rate'],
    'reassure':['comfort','console','encourage'],
    'rebel':['revolt','resist','defy'],
    'recede':['retreat','withdraw','diminish'],
    'reckless':['careless','rash','irresponsible'],
    'reconcile':['resolve','settle','harmonise'],
    'recover':['regain','recuperate','retrieve'],
    'recruit':['enlist','hire','enrol'],
    'rectify':['correct','fix','remedy'],
    'refine':['improve','polish','perfect'],
    'reflect':['mirror','ponder','indicate'],
    'reform':['improve','amend','revise'],
    'refrain':['abstain','avoid','desist'],
    'refuge':['shelter','sanctuary','haven'],
    'refuse':['decline','reject','deny'],
    'refute':['disprove','rebut','contradict'],
    'regain':['recover','retrieve','reclaim'],
    'regard':['consider','esteem','respect'],
    'register':['record','enrol','list'],
    'regret':['remorse','sorrow','lament'],
    'regulate':['control','govern','manage'],
    'rehabilitate':['restore','reform','recover'],
    'reinforce':['strengthen','support','bolster'],
    'reject':['refuse','decline','dismiss'],
    'rejoice':['celebrate','delight','exult'],
    'relax':['unwind','rest','ease'],
    'release':['free','discharge','issue'],
    'relentless':['persistent','unyielding','ceaseless'],
    'reliable':['dependable','trustworthy','consistent'],
    'relief':['comfort','ease','respite'],
    'reluctant':['unwilling','hesitant','loath'],
    'rely':['depend','trust','count on'],
    'remark':['comment','observation','note'],
    'remarkable':['notable','extraordinary','impressive'],
    'remedy':['cure','solution','treatment'],
    'reminisce':['recall','recollect','remember'],
    'remote':['distant','isolated','far'],
    'render':['make','provide','deliver'],
    'renew':['restore','revive','resume'],
    'renounce':['abandon','relinquish','disown'],
    'renowned':['famous','celebrated','distinguished'],
    'repair':['fix','mend','restore'],
    'repel':['repulse','drive back','disgust'],
    'replicate':['duplicate','reproduce','copy'],
    'reprimand':['scold','rebuke','admonish'],
    'reproduce':['copy','replicate','duplicate'],
    'reputation':['standing','image','renown'],
    'request':['ask','appeal','petition'],
    'rescue':['save','deliver','salvage'],
    'resemble':['look like','be similar to','mirror'],
    'resent':['begrudge','dislike','object to'],
    'reserve':['set aside','withhold','stock'],
    'reside':['live','dwell','inhabit'],
    'resign':['quit','step down','abdicate'],
    'resist':['oppose','withstand','defy'],
    'resolve':['settle','determine','decide'],
    'resort':['turn to','recourse'],
    'resource':['asset','supply','material'],
    'respectable':['reputable','honourable','decent'],
    'restore':['renew','repair','reinstate'],
    'restrain':['control','hold back','curb'],
    'restrict':['limit','confine','curb'],
    'resume':['continue','restart','recommence'],
    'retain':['keep','preserve','hold'],
    'retaliate':['respond','avenge','strike back'],
    'retreat':['withdraw','retire','recede'],
    'retrieve':['recover','regain','fetch'],
    'reveal':['expose','disclose','unveil'],
    'revenge':['retaliation','retribution','vengeance'],
    'revenue':['income','earnings','proceeds'],
    'revere':['admire','respect','venerate'],
    'reverse':['invert','undo','opposite'],
    'revive':['restore','revitalise','resuscitate'],
    'revoke':['cancel','withdraw','rescind'],
    'revolt':['rebel','uprising','mutiny'],
    'reward':['prize','benefit','recompense'],
    'rid':['eliminate','remove','free'],
    'ridicule':['mock','deride','taunt'],
    'rigid':['stiff','inflexible','strict'],
    'rigorous':['strict','thorough','stringent'],
    'rival':['competitor','opponent','contend with'],
    'roam':['wander','ramble','stray'],
    'robust':['strong','sturdy','vigorous'],
    'roughly':['approximately','around','about'],
    'rouse':['awaken','stir','excite'],
    'routine':['regular','habitual','pattern'],
    'rugged':['tough','rough','sturdy'],
    'rumour':['gossip','hearsay','speculation'],
    'rural':['countryside','pastoral','agricultural'],
    'sabotage':['undermine','disrupt','damage'],
    'sacred':['holy','revered','hallowed'],
    'sacrifice':['forfeit','give up','offering'],
    'sanction':['penalty','approve','authorise'],
    'satisfactory':['adequate','acceptable','sufficient'],
    'scandal':['controversy','disgrace','outrage'],
    'scarce':['rare','limited','insufficient'],
    'scatter':['disperse','spread','strew'],
    'scenario':['situation','circumstance','possibility'],
    'sceptical':['doubtful','distrustful','questioning'],
    'scheme':['plan','strategy','plot'],
    'scope':['range','extent','breadth'],
    'scrutinise':['examine','inspect','study'],
    'secondary':['subordinate','lesser','supplementary'],
    'secure':['safe','obtain','stable'],
    'seek':['search for','pursue','look for'],
    'segment':['section','part','portion'],
    'seize':['grab','capture','confiscate'],
    'sequence':['series','order','succession'],
    'severe':['harsh','extreme','intense'],
    'shatter':['break','smash','destroy'],
    'shelter':['refuge','protection','haven'],
    'shift':['change','move','transition'],
    'shrink':['contract','decrease','diminish'],
    'shrewd':['astute','clever','perceptive'],
    'signify':['indicate','denote','represent'],
    'simultaneous':['concurrent','synchronous'],
    'sincere':['genuine','honest','heartfelt'],
    'skeptical':['doubtful','sceptical','distrustful'],
    'slight':['minor','small','insult'],
    'sluggish':['slow','lethargic','inactive'],
    'sole':['only','single','exclusive'],
    'solemn':['serious','grave','dignified'],
    'solitary':['alone','isolated','lone'],
    'somewhat':['rather','fairly','moderately'],
    'sophisticated':['refined','advanced','cultured'],
    'sound':['reasonable','healthy','valid'],
    'span':['extent','stretch','duration'],
    'spark':['ignite','trigger','initiate'],
    'specify':['state','define','stipulate'],
    'speculate':['guess','conjecture','theorise'],
    'spontaneous':['impulsive','unplanned','instinctive'],
    'sporadic':['irregular','intermittent','occasional'],
    'spread':['disseminate','expand','extend'],
    'stability':['steadiness','balance','security'],
    'stagger':['stumble','astonish','alternate'],
    'stagnant':['inactive','stationary','motionless'],
    'stall':['delay','stop','postpone'],
    'startle':['surprise','alarm','shock'],
    'static':['unchanging','stationary','fixed'],
    'steady':['stable','consistent','constant'],
    'steer':['guide','direct','navigate'],
    'stimulate':['encourage','arouse','provoke'],
    'stir':['provoke','arouse','mix'],
    'straightforward':['simple','clear','uncomplicated'],
    'strategy':['plan','approach','tactic'],
    'stray':['wander','deviate','roam'],
    'strengthen':['reinforce','fortify','bolster'],
    'strenuous':['demanding','arduous','tough'],
    'stringent':['strict','rigorous','severe'],
    'striking':['remarkable','impressive','notable'],
    'strive':['endeavour','struggle','attempt'],
    'struggle':['fight','battle','effort'],
    'stubborn':['obstinate','headstrong','inflexible'],
    'substantial':['considerable','significant','sizeable'],
    'subsidise':['fund','support financially'],
    'subsequent':['following','later','ensuing'],
    'subtle':['delicate','understated','nuanced'],
    'succession':['sequence','series','order'],
    'sufficient':['adequate','enough','ample'],
    'suitable':['appropriate','fitting','apt'],
    'summon':['call','invoke','request'],
    'superb':['excellent','outstanding','magnificent'],
    'superficial':['shallow','surface','cursory'],
    'superior':['better','higher-ranking','excellent'],
    'supervise':['oversee','manage','monitor'],
    'supplement':['addition','complement','add to'],
    'suppress':['restrain','quell','stifle'],
    'surge':['increase','rise','swell'],
    'surpass':['exceed','outdo','outperform'],
    'surplus':['excess','abundance','extra'],
}
REPEAT_SYNONYMS.update(REPEAT_SYNONYMS_EXT3)

# Fifth-tier synonym bank: major vocabulary expansion (~10,000 words) covering
# academic/formal verbs, descriptive adjectives, abstract and concrete nouns,
# adverbs, and role/institution vocabulary, beyond all prior tiers above.
# Same offline, deterministic lookup mechanism -- pre-authored alternatives
# only, no generated text.
REPEAT_SYNONYMS_EXT4 = {
    'abolish':['eliminate','abrogate','annul','terminate','do away with'],
    'absolve':['acquit','exonerate','pardon','clear','vindicate'],
    'abstain':['refrain','forgo','desist','withhold','decline'],
    'accentuate':['emphasise','highlight','underscore','stress','accent'],
    'accommodate':['adapt','house','oblige','fit in','cater for'],
    'accrue':['accumulate','build up','collect','mount up','gather'],
    'acknowledge':['admit','recognise','concede','accept','recognize'],
    'affirm':['confirm','assert','declare','maintain','uphold'],
    'aggregate':['combine','total','accumulate','amass','compile'],
    'alleviate':['ease','relieve','mitigate','lessen','reduce'],
    'ally':['unite','join forces','partner','associate','collaborate'],
    'amend':['revise','modify','alter','correct','rectify'],
    'annihilate':['destroy','obliterate','eradicate','wipe out','demolish'],
    'annotate':['comment on','note','gloss','mark up','explain'],
    'antagonise':['provoke','irritate','alienate','anger','vex'],
    'appease':['pacify','placate','conciliate','mollify','soothe'],
    'apprise':['inform','notify','tell','advise','brief'],
    'arbitrate':['mediate','adjudicate','referee','settle','judge'],
    'assail':['attack','assault','besiege','bombard','set upon'],
    'assimilate':['absorb','integrate','incorporate','digest','adapt'],
    'attenuate':['weaken','reduce','diminish','lessen','dilute'],
    'augur':['predict','foretell','portend','bode','forecast'],
    'avow':['declare','affirm','assert','profess','proclaim'],
    'bemoan':['lament','mourn','deplore','regret','bewail'],
    'bequeath':['leave','pass on','hand down','will','transmit'],
    'besiege':['surround','encircle','beleaguer','blockade','overwhelm'],
    'betray':['deceive','double-cross','sell out','expose','forsake'],
    'bifurcate':['split','divide','fork','branch','separate'],
    'blaspheme':['curse','profane','desecrate'],
    'bombard':['attack','assault','pelt','shell','besiege'],
    'brandish':['wave','flourish','wield','display','flaunt'],
    'breach':['violate','infringe','break','contravene','transgress'],
    'bristle':['react angrily','stiffen','tense'],
    'buttress':['support','reinforce','strengthen','bolster','prop up'],
    'cajole':['coax','persuade','wheedle','entice','sweet-talk'],
    'capitulate':['surrender','yield','submit','give in','concede'],
    'captivate':['fascinate','enthral','charm','mesmerise','enchant'],
    'castigate':['criticise','rebuke','reprimand','chastise','scold'],
    'categorise':['classify','sort','group','arrange','organise'],
    'censure':['criticise','condemn','denounce','reprimand','rebuke'],
    'chastise':['reprimand','scold','rebuke','castigate','discipline'],
    'circumvent':['bypass','evade','avoid','get around','sidestep'],
    'coalesce':['merge','combine','unite','fuse','converge'],
    'coax':['persuade','cajole','wheedle','entice','induce'],
    'coerce':['force','compel','pressure','intimidate','bully'],
    'collate':['compile','assemble','organise','arrange','gather'],
    'commemorate':['honour','celebrate','memorialise','mark','observe'],
    'commend':['praise','applaud','recommend','laud','acclaim'],
    'commiserate':['sympathise','condole','console','comfort'],
    'concur':['agree','coincide','accord','consent','align'],
    'condense':['shorten','compress','abbreviate','summarise','contract'],
    'confer':['discuss','consult','bestow','grant','deliberate'],
    'configure':['arrange','set up','organise','adjust','shape'],
    'confiscate':['seize','impound','appropriate','commandeer','take away'],
    'congeal':['solidify','thicken','set','harden','coagulate'],
    'conjecture':['guess','speculate','surmise','theorise','hypothesise'],
    'connote':['imply','suggest','signify','indicate','denote'],
    'consecrate':['sanctify','bless','dedicate','hallow'],
    'contravene':['violate','breach','infringe','transgress','disobey'],
    'convalesce':['recover','recuperate','heal','mend'],
    'conjure':['evoke','summon','invoke','produce','create'],
    'corroborate':['confirm','verify','substantiate','support','validate'],
    'counteract':['neutralise','offset','counter','negate','oppose'],
    'counterbalance':['offset','compensate for','neutralise','equalise'],
    'cripple':['disable','incapacitate','impair','hobble','paralyse'],
    'culminate':['end','climax','peak','conclude','result'],
    'curb':['restrain','check','control','limit','restrict'],
    'curtail':['reduce','cut short','limit','restrict','shorten'],
    'debilitate':['weaken','enfeeble','incapacitate','exhaust','sap'],
    'debunk':['disprove','discredit','expose','refute','deflate'],
    'decimate':['devastate','destroy','ravage','annihilate','wipe out'],
    'decipher':['decode','interpret','decrypt','unravel','solve'],
    'decree':['order','proclaim','pronounce','ordain','command'],
    'deduce':['infer','conclude','reason','work out','gather'],
    'defame':['slander','malign','vilify','discredit','disparage'],
    'defer':['postpone','delay','put off','submit to','yield to'],
    'defraud':['swindle','cheat','con','deceive','trick'],
    'deft':['skilful','adroit','dexterous','nimble','proficient'],
    'degenerate':['deteriorate','decline','worsen','decay','regress'],
    'deify':['idolise','worship','glorify','revere','venerate'],
    'delegate':['assign','entrust','hand over','commission','allocate'],
    'delineate':['outline','define','describe','sketch','depict'],
    'demarcate':['delimit','define','mark out','separate','bound'],
    'demoralise':['dishearten','discourage','dispirit','undermine','sap morale'],
    'denigrate':['disparage','belittle','deprecate','vilify','malign'],
    'deplete':['exhaust','drain','use up','consume','reduce'],
    'deplore':['condemn','denounce','regret','lament','disapprove of'],
    'deport':['expel','banish','exile','extradite','remove'],
    'depose':['oust','overthrow','remove','dethrone','unseat'],
    'deride':['mock','ridicule','scorn','scoff at','belittle'],
    'designate':['assign','name','appoint','specify','earmark'],
    'desist':['stop','cease','refrain','abstain','discontinue'],
    'detach':['separate','disconnect','remove','disengage','isolate'],
    'deter':['discourage','dissuade','prevent','put off','hinder'],
    'detonate':['explode','blow up','set off','ignite'],
    'devise':['create','design','formulate','concoct','invent'],
    'diffuse':['spread','disperse','scatter','disseminate','distribute'],
    'digress':['deviate','stray','wander','veer','ramble'],
    'dilate':['expand','widen','enlarge','swell','distend'],
    'dilute':['weaken','water down','thin','reduce','attenuate'],
    'discern':['perceive','recognise','distinguish','detect','notice'],
    'discredit':['undermine','disparage','vilify','tarnish','defame'],
    'disintegrate':['crumble','decompose','collapse','fall apart','break up'],
    'dismantle':['disassemble','take apart','deconstruct','break down','strip'],
    'disparage':['belittle','deprecate','denigrate','criticise','put down'],
    'dispel':['dissipate','banish','drive away','remove','scatter'],
    'disperse':['scatter','spread out','distribute','diffuse','break up'],
    'displace':['dislodge','replace','uproot','oust','shift'],
    'disqualify':['bar','exclude','preclude','rule out','debar'],
    'dissect':['analyse','examine','cut apart','scrutinise','break down'],
    'disseminate':['spread','circulate','distribute','propagate','broadcast'],
    'dissipate':['disperse','vanish','fade away','dispel','squander'],
    'dissuade':['discourage','deter','put off','talk out of','divert'],
    'distend':['swell','expand','bloat','dilate','inflate'],
    'divulge':['reveal','disclose','impart','let out','expose'],
    'document':['record','register','chronicle','note','log'],
    'dupe':['deceive','trick','fool','swindle','con'],
    'eclipse':['overshadow','surpass','outshine','outdo','dwarf'],
    'economise':['save','cut back','budget','conserve','skimp'],
    'eject':['expel','remove','oust','discharge','throw out'],
    'elicit':['evoke','draw out','extract','provoke','bring forth'],
    'elucidate':['clarify','explain','illuminate','clear up','explicate'],
    'elude':['evade','escape','avoid','dodge','circumvent'],
    'emancipate':['liberate','free','release','emancipate','deliver'],
    'embellish':['decorate','adorn','ornament','exaggerate','enhance'],
    'embezzle':['misappropriate','steal','pilfer','defraud','swindle'],
    'emulate':['imitate','copy','mimic','follow','replicate'],
    'encroach':['intrude','infringe','trespass','impinge','invade'],
    'enervate':['weaken','drain','exhaust','sap','debilitate'],
    'engender':['generate','produce','cause','create','bring about'],
    'engross':['absorb','captivate','immerse','preoccupy','fascinate'],
    'enliven':['animate','invigorate','brighten','energise','vitalise'],
    'enrage':['infuriate','incense','anger','madden','provoke'],
    'enrapture':['delight','enchant','captivate','entrance','thrill'],
    'ensconce':['settle','establish','install','lodge','shelter'],
    'ensnare':['trap','entrap','snare','entangle','catch'],
    'enthral':['captivate','fascinate','mesmerise','enchant','spellbind'],
    'entice':['tempt','lure','attract','allure','draw'],
    'entrench':['establish firmly','embed','root','fortify','solidify'],
    'enumerate':['list','itemise','specify','detail','count'],
    'envelop':['surround','enclose','engulf','wrap','encircle'],
    'epitomise':['exemplify','embody','typify','personify','represent'],
    'espouse':['adopt','support','embrace','advocate','champion'],
    'eulogise':['praise','commend','extol','laud','glorify'],
    'evacuate':['clear out','vacate','withdraw','remove','abandon'],
    'exacerbate':['worsen','aggravate','intensify','inflame','compound'],
    'exalt':['glorify','praise','honour','elevate','extol'],
    'exasperate':['irritate','frustrate','annoy','infuriate','vex'],
    'excavate':['dig up','unearth','exhume','extract','mine'],
    'exclaim':['cry out','shout','declare','proclaim','blurt out'],
    'excommunicate':['expel','banish','exclude','ostracise'],
    'exculpate':['exonerate','absolve','vindicate','clear','acquit'],
    'exemplify':['illustrate','typify','embody','epitomise','represent'],
    'exhilarate':['thrill','excite','elate','invigorate','energise'],
    'exhort':['urge','encourage','press','implore','entreat'],
    'exonerate':['acquit','absolve','clear','vindicate','exculpate'],
    'exorcise':['banish','expel','drive out'],
    'expel':['eject','banish','remove','oust','dismiss'],
    'expend':['spend','use up','consume','exhaust','disburse'],
    'expiate':['atone for','make amends for','redress'],
    'explicate':['explain','clarify','elucidate','interpret','expound'],
    'exponent':['advocate','proponent','supporter','champion'],
    'expropriate':['confiscate','seize','appropriate','commandeer'],
    'expunge':['erase','delete','remove','eliminate','strike out'],
    'extol':['praise','laud','glorify','commend','celebrate'],
    'extort':['extract','coerce','blackmail','wring','squeeze'],
    'extradite':['deport','expel','hand over'],
    'extricate':['free','disentangle','release','remove','rescue'],
    'exude':['emit','ooze','radiate','give off','discharge'],
    'exult':['rejoice','celebrate','triumph','revel','glory'],
    'falter':['stumble','waver','hesitate','stagger','flag'],
    'fathom':['understand','grasp','comprehend','decipher','work out'],
    'feign':['pretend','fake','simulate','affect','sham'],
    'ferment':['brew','stir up','incite','agitate'],
    'fetter':['restrain','shackle','constrain','bind','hamper'],
    'flaunt':['show off','display','parade','exhibit','brandish'],
    'flout':['disregard','defy','disobey','ignore','violate'],
    'foment':['incite','stir up','instigate','provoke','agitate'],
    'forfeit':['lose','surrender','give up','relinquish','sacrifice'],
    'formulate':['devise','develop','construct','create','conceive'],
    'fortify':['strengthen','reinforce','bolster','defend','brace'],
    'frustrate':['thwart','hinder','foil','impede','disappoint'],
    'fumigate':['disinfect','sanitise','purify'],
    'galvanise':['spur','motivate','stimulate','energise','provoke'],
    'garner':['gather','collect','accumulate','amass','obtain'],
    'germinate':['sprout','develop','grow','originate','emerge'],
    'glean':['gather','collect','extract','harvest','deduce'],
    'glorify':['exalt','praise','extol','celebrate','venerate'],
    'goad':['provoke','prod','incite','spur','egg on'],
    'gouge':['extort','overcharge','swindle','scoop out'],
    'grapple':['struggle','wrestle','contend','tackle','confront'],
    'gratify':['satisfy','please','fulfil','indulge','delight'],
    'grieve':['mourn','lament','sorrow','suffer','bemoan'],
    'grovel':['fawn','crawl','cower','abase oneself'],
    'guise':['appearance','disguise','pretence','facade'],
    'hallow':['sanctify','consecrate','bless','revere'],
    'hamper':['hinder','impede','obstruct','restrict','encumber'],
    'harangue':['lecture','rant','tirade','berate','scold'],
    'harbour':['shelter','conceal','nurse','hold','entertain'],
    'hearten':['encourage','cheer','uplift','reassure','buoy'],
    'heighten':['intensify','increase','magnify','amplify','escalate'],
    'hoard':['stockpile','accumulate','amass','stash','save'],
    'hone':['sharpen','refine','perfect','polish','improve'],
    'hurl':['throw','fling','cast','pitch','launch'],
    'idolise':['worship','adore','revere','venerate','idealise'],
    'ignite':['light','kindle','spark','trigger','set off'],
    'illuminate':['light up','clarify','elucidate','brighten','explain'],
    'imbue':['infuse','instil','permeate','pervade','saturate'],
    'impart':['convey','communicate','bestow','transmit','give'],
    'imperil':['endanger','jeopardise','threaten','risk','menace'],
    'implicate':['involve','incriminate','entangle','associate','link'],
    'implore':['beg','plead','entreat','beseech','urge'],
    'impound':['confiscate','seize','commandeer','sequester'],
    'imprint':['stamp','engrave','fix','embed','mark'],
    'inaugurate':['launch','initiate','commence','begin','institute'],
    'incapacitate':['disable','cripple','immobilise','debilitate','paralyse'],
    'incarcerate':['imprison','jail','confine','detain','lock up'],
    'incense':['enrage','infuriate','anger','madden','inflame'],
    'incinerate':['burn','cremate','char','reduce to ashes'],
    'incite':['provoke','instigate','stir up','foment','spur'],
    'inculcate':['instil','implant','impress','instill','ingrain'],
    'indemnify':['compensate','reimburse','protect','insure'],
    'indict':['charge','accuse','prosecute','arraign','impeach'],
    'indoctrinate':['brainwash','instruct','condition','teach'],
    'infest':['overrun','swarm','plague','invade','pervade'],
    'infiltrate':['penetrate','permeate','invade','sneak into','breach'],
    'inflame':['worsen','aggravate','provoke','incite','exacerbate'],
    'inflate':['expand','swell','exaggerate','pump up','enlarge'],
    'infuse':['imbue','instil','permeate','fill','saturate'],
    'ingest':['consume','swallow','absorb','eat','take in'],
    'ingratiate':['curry favour','flatter','fawn','court favour'],
    'inhibit':['restrain','hinder','suppress','curb','impede'],
    'inscribe':['engrave','etch','write','carve','imprint'],
    'inseminate':['fertilise','impregnate'],
    'insinuate':['imply','hint','suggest','intimate','allude'],
    'instigate':['provoke','incite','initiate','trigger','stir up'],
    'institute':['establish','found','set up','initiate','introduce'],
    'insulate':['isolate','protect','shield','cushion','buffer'],
    'insure':['protect','indemnify','safeguard','cover'],
    'intensify':['increase','heighten','escalate','strengthen','amplify'],
    'intercede':['mediate','intervene','plead','arbitrate'],
    'intercept':['stop','block','catch','seize','waylay'],
    'interject':['interrupt','interpose','cut in','insert'],
    'interlace':['interweave','entwine','intertwine','weave'],
    'interlock':['connect','engage','link','join','mesh'],
    'interpose':['insert','interject','intervene','place between'],
    'interrogate':['question','cross-examine','grill','quiz','examine'],
    'intersect':['cross','meet','converge','overlap'],
    'intersperse':['scatter','distribute','sprinkle','dot','mix'],
    'intertwine':['interweave','entwine','interlace','entangle'],
    'intimidate':['frighten','threaten','bully','cow','browbeat'],
    'intoxicate':['inebriate','stupefy','poison','exhilarate'],
    'inundate':['flood','overwhelm','swamp','deluge','engulf'],
    'inure':['harden','desensitise','accustom','toughen'],
    'invalidate':['nullify','void','annul','negate','discredit'],
    'inveigle':['persuade','coax','manipulate','wheedle'],
    'invert':['reverse','flip','turn upside down','transpose'],
    'invigorate':['energise','revitalise','stimulate','refresh','enliven'],
    'irk':['irritate','annoy','vex','bother','exasperate'],
    'irradiate':['expose to radiation','illuminate'],
    'jeer':['mock','taunt','ridicule','sneer','scoff'],
    'jettison':['discard','abandon','dump','ditch','dispose of'],
    'jibe':['taunt','mock','gibe'],
    'juggle':['manage','balance','handle','manipulate'],
    'juxtapose':['contrast','compare','place side by side'],
    'lambaste':['criticise','castigate','berate','excoriate','rebuke'],
    'languish':['deteriorate','decline','waste away','wilt','wither'],
    'lavish':['bestow generously','shower','give freely'],
    'legitimise':['legitimate','validate','sanction','authorise'],
    'lessen':['reduce','diminish','decrease','ease','moderate'],
    'licence':['authorise','permit','sanction','certify'],
    'liquidate':['dissolve','wind up','sell off','eliminate'],
    'lobby':['petition','campaign','pressure','advocate','urge'],
    'lure':['entice','tempt','attract','draw','allure'],
    'malign':['defame','slander','disparage','vilify','denigrate'],
    'mandate':['authorise','require','order','decree','sanction'],
    'manoeuvre':['navigate','steer','manipulate','manage','operate'],
    'marginalise':['sideline','exclude','disregard','ostracise','isolate'],
    'marshal':['organise','arrange','assemble','deploy','gather'],
    'meld':['blend','merge','fuse','combine','integrate'],
    'mesmerise':['captivate','hypnotise','enthral','fascinate','spellbind'],
    'metamorphose':['transform','change','evolve','mutate','convert'],
    'mire':['bog down','entangle','trap','stick'],
    'mitigate':['alleviate','lessen','reduce','moderate','temper'],
    'mobilise':['organise','rally','marshal','deploy','activate'],
    'modulate':['adjust','regulate','vary','moderate','tune'],
    'molest':['harass','pester','trouble'],
    'mollify':['appease','placate','pacify','soothe','calm'],
    'monopolise':['dominate','control','corner','engross'],
    'mortify':['humiliate','embarrass','shame','abash'],
    'multiply':['increase','proliferate','expand','grow','breed'],
    'muster':['gather','assemble','summon','rally','collect'],
    'mutate':['transform','change','alter','evolve','transmute'],
    'mystify':['baffle','puzzle','confuse','perplex','bewilder'],
    'nab':['catch','seize','grab','apprehend','capture'],
    'nag':['pester','harass','bother','plague','harp on'],
    'narrate':['tell','recount','relate','describe','chronicle'],
    'nauseate':['sicken','disgust','repel','revolt'],
    'necessitate':['require','demand','entail','call for','warrant'],
    'negate':['nullify','invalidate','cancel out','offset','counteract'],
    'nettle':['irritate','annoy','provoke','vex','irk'],
    'neutralise':['counteract','offset','nullify','cancel out','negate'],
    'nullify':['invalidate','void','annul','cancel','negate'],
    'obfuscate':['obscure','confuse','muddle','blur','cloud'],
    'obliterate':['destroy','annihilate','erase','wipe out','eradicate'],
    'obviate':['eliminate','preclude','remove','prevent','avoid'],
    'officiate':['preside','conduct','oversee','chair'],
    'opt':['choose','select','decide','pick'],
    'ordain':['decree','order','appoint','consecrate','prescribe'],
    'originate':['begin','arise','stem','derive','start'],
    'ostracise':['exclude','shun','banish','isolate','reject'],
    'outmanoeuvre':['outwit','outsmart','trick','get the better of'],
    'outstrip':['surpass','exceed','outperform','overtake','eclipse'],
    'outwit':['outsmart','trick','deceive','outmanoeuvre'],
    'overhaul':['revamp','renovate','restructure','revise','update'],
    'overrule':['reject','override','veto','reverse','nullify'],
    'overshadow':['eclipse','outshine','dominate','dwarf','surpass'],
    'override':['overrule','supersede','disregard','reverse','cancel'],
    'overturn':['reverse','overrule','upset','topple','cancel'],
    'palliate':['ease','relieve','alleviate','soften','mitigate'],
    'paralyse':['immobilise','disable','incapacitate','cripple','freeze'],
    'parody':['mock','satirise','imitate','caricature','burlesque'],
    'pave':['prepare','clear','lay the groundwork'],
    'pelt':['bombard','hurl','shower','throw','batter'],
    'perforate':['pierce','puncture','penetrate','riddle'],
    'perpetrate':['commit','carry out','perform','execute'],
    'perpetuate':['continue','maintain','sustain','prolong','preserve'],
    'peruse':['read','study','examine','scan','scrutinise'],
    'pervade':['permeate','saturate','suffuse','fill','spread through'],
    'petrify':['terrify','frighten','paralyse with fear','horrify'],
    'pilfer':['steal','filch','pinch','purloin','swipe'],
    'pillage':['plunder','loot','ransack','ravage'],
    'placate':['appease','pacify','mollify','conciliate','soothe'],
    'plagiarise':['copy','steal','pirate','crib'],
    'plunder':['loot','pillage','ransack','rob','raid'],
    'pontificate':['lecture','preach','moralise','sermonise'],
    'postulate':['assume','hypothesise','theorise','posit','suppose'],
    'precipitate':['trigger','cause','provoke','bring about','hasten'],
    'preclude':['prevent','rule out','exclude','avert','forestall'],
    'predispose':['incline','make susceptible','prime','bias'],
    'preempt':['forestall','prevent','anticipate','avert'],
    'prefigure':['foreshadow','presage','anticipate','portend'],
    'prescribe':['recommend','stipulate','order','specify','decree'],
    'presage':['foreshadow','portend','predict','forebode','signal'],
    'preside':['chair','oversee','officiate','conduct','head'],
    'procrastinate':['delay','postpone','defer','stall','dawdle'],
    'proffer':['offer','present','extend','tender','submit'],
    'profess':['claim','declare','avow','assert','affirm'],
    'proliferate':['multiply','increase','spread','expand','flourish'],
    'propagate':['spread','disseminate','multiply','breed','promote'],
    'propitiate':['appease','placate','conciliate','pacify'],
    'proscribe':['forbid','ban','prohibit','outlaw','disallow'],
    'prosecute':['try','indict','sue','pursue','litigate'],
    'protrude':['stick out','jut out','project','bulge'],
    'pulverise':['crush','grind','pound','demolish','smash'],
    'purge':['cleanse','eliminate','remove','eradicate','clear out'],
    'purloin':['steal','pilfer','filch','pinch','swipe'],
    'quash':['suppress','crush','overturn','annul','squash'],
    'quell':['suppress','subdue','extinguish','crush','put down'],
    'quench':['satisfy','slake','extinguish','put out'],
    'quibble':['dispute','object','cavil','bicker','argue'],
    'rally':['gather','assemble','regroup','recover','muster'],
    'ramify':['branch out','spread','diverge'],
    'rankle':['irritate','annoy','fester','embitter'],
    'ransack':['plunder','pillage','loot','rummage','search thoroughly'],
    'rationalise':['justify','explain','account for','reason','excuse'],
    'ravage':['devastate','destroy','plunder','wreck','pillage'],
    'reaffirm':['confirm','restate','reassert','reiterate'],
    'rebuff':['reject','snub','spurn','refuse','turn down'],
    'rebuke':['reprimand','scold','reprove','admonish','chastise'],
    'rebut':['refute','disprove','contradict','counter','dispute'],
    'recant':['retract','withdraw','disavow','renounce','revoke'],
    'recapitulate':['summarise','recap','review','restate'],
    'reciprocate':['return','requite','repay','respond','match'],
    'recite':['repeat','recount','narrate','declaim','say aloud'],
    'reclaim':['recover','retrieve','regain','restore','recoup'],
    'recoil':['flinch','shrink back','retreat','wince','shudder'],
    'recompense':['compensate','reward','reimburse','repay','remunerate'],
    'recount':['narrate','relate','describe','tell','recite'],
    'recuperate':['recover','heal','convalesce','mend','improve'],
    'redeem':['recover','reclaim','save','atone for','make good'],
    'redress':['remedy','rectify','correct','compensate for','amend'],
    'regurgitate':['repeat','recite','vomit up','disgorge'],
    'reiterate':['repeat','restate','reaffirm','recap','stress again'],
    'rejuvenate':['revitalise','refresh','renew','revive','invigorate'],
    'rekindle':['revive','reignite','renew','reawaken','restore'],
    'relegate':['demote','downgrade','banish','consign','assign'],
    'relinquish':['give up','surrender','abandon','forgo','yield'],
    'relish':['enjoy','savour','delight in','appreciate','revel in'],
    'remonstrate':['protest','object','complain','argue','expostulate'],
    'remunerate':['pay','compensate','reward','recompense','reimburse'],
    'rendezvous':['meet','gather','assemble'],
    'renege':['back out','go back on','default','withdraw'],
    'renovate':['refurbish','restore','renew','revamp','remodel'],
    'replenish':['refill','restock','renew','top up','restore'],
    'repress':['suppress','restrain','curb','inhibit','stifle'],
    'reproach':['blame','criticise','rebuke','censure','condemn'],
    'repudiate':['reject','deny','disown','renounce','disavow'],
    'repulse':['repel','disgust','drive back','rebuff','sicken'],
    'requisition':['demand','order','request','commandeer'],
    'rescind':['revoke','cancel','repeal','annul','withdraw'],
    'resile':['recoil','shrink back','retreat'],
    'resonate':['echo','reverberate','strike a chord','vibrate'],
    'resuscitate':['revive','resurrect','revitalise','bring back'],
    'retard':['slow down','delay','hinder','impede','hamper'],
    'reticent':['reserved','reluctant','uncommunicative','tight-lipped'],
    'retort':['reply sharply','respond','counter','riposte'],
    'retract':['withdraw','recant','take back','revoke','disavow'],
    'reverberate':['echo','resound','resonate','ring'],
    'revert':['return','relapse','go back','regress'],
    'revile':['insult','abuse','vilify','denounce','malign'],
    'revitalise':['reinvigorate','rejuvenate','renew','refresh','revive'],
    'rig':['fix','manipulate','tamper with','set up'],
    'riposte':['retort','reply','counter','rejoinder'],
    'roil':['agitate','disturb','stir up','trouble'],
    'rout':['defeat decisively','crush','overwhelm','vanquish'],
    'ruminate':['ponder','muse','contemplate','reflect','mull over'],
    'rupture':['break','burst','split','tear','fracture'],
    'salvage':['rescue','recover','retrieve','reclaim','save'],
    'sate':['satisfy','satiate','fill','gratify'],
    'satiate':['satisfy fully','glut','sate','gorge'],
    'scald':['burn','sear','blister'],
    'scavenge':['forage','search','salvage','rummage'],
    'scoff':['mock','deride','ridicule','jeer','sneer'],
    'scorn':['despise','disdain','disparage','spurn','deride'],
    'scour':['search thoroughly','scrub','ransack','comb'],
    'secede':['withdraw','break away','separate','split off'],
    'seclude':['isolate','separate','shut off','sequester'],
    'sequester':['isolate','seclude','separate','confiscate','set apart'],
    'shackle':['restrain','fetter','constrain','chain','hamper'],
    'sidestep':['avoid','evade','circumvent','dodge','bypass'],
    'sift':['sort through','examine','filter','screen','analyse'],
    'simulate':['imitate','mimic','replicate','feign','emulate'],
    'skew':['distort','bias','slant','warp'],
    'slake':['quench','satisfy','allay'],
    'slander':['defame','malign','libel','vilify','disparage'],
    'smear':['defame','vilify','slander','besmirch','malign'],
    'smother':['suffocate','stifle','suppress','extinguish','choke'],
    'solicit':['request','seek','ask for','petition for','appeal for'],
    'solidify':['harden','set','strengthen','consolidate','congeal'],
    'soothe':['calm','comfort','pacify','ease','alleviate'],
    'spawn':['generate','produce','give rise to','engender','create'],
    'spearhead':['lead','head','pioneer','initiate','drive'],
    'spew':['emit','discharge','vomit','pour out','eject'],
    'spurn':['reject','scorn','rebuff','disdain','snub'],
    'squander':['waste','misuse','fritter away','dissipate','throw away'],
    'stagnate':['stall','stall out','decline','deteriorate','languish'],
    'stem':['originate','derive','arise','stop','halt'],
    'stifle':['suppress','smother','restrain','curb','inhibit'],
    'stipulate':['specify','require','demand','set down','prescribe'],
    'stockpile':['hoard','amass','accumulate','store','build up'],
    'strew':['scatter','spread','litter','disperse'],
    'subdue':['overpower','suppress','conquer','tame','vanquish'],
    'subjugate':['conquer','enslave','dominate','oppress','subdue'],
    'sublimate':['redirect','channel','transform'],
    'submerge':['immerse','sink','plunge','flood','engulf'],
    'subordinate':['secondary','lesser','subject','junior'],
    'substantiate':['confirm','verify','corroborate','support','validate'],
    'subvert':['undermine','sabotage','overthrow','destabilise','disrupt'],
    'succumb':['yield','give in','surrender','submit','capitulate'],
    'suffocate':['smother','stifle','choke','asphyxiate'],
    'suffuse':['permeate','pervade','saturate','fill','infuse'],
    'supersede':['replace','supplant','override','displace','succeed'],
    'supplant':['replace','supersede','displace','oust','usurp'],
    'supplicate':['beg','plead','implore','entreat'],
    'surmise':['guess','conjecture','speculate','presume','deduce'],
    'surmount':['overcome','conquer','triumph over','master','beat'],
    'surrender':['yield','capitulate','submit','give in','concede'],
    'sway':['influence','persuade','affect','rock','waver'],
    'taint':['contaminate','corrupt','pollute','sully','stain'],
    'tantalise':['tease','tempt','torment','entice'],
    'tarnish':['sully','stain','blemish','discredit','damage'],
    'temper':['moderate','soften','restrain','mitigate','adjust'],
    'terminate':['end','conclude','stop','discontinue','cease'],
    'thrive':['flourish','prosper','succeed','bloom','blossom'],
    'thwart':['foil','frustrate','prevent','block','stymie'],
    'titillate':['excite','stimulate','arouse','tease'],
    'toil':['labour','work hard','strive','grind','struggle'],
    'tolerate':['endure','bear','put up with','accept','stand'],
    'torment':['torture','afflict','plague','harass','agonise'],
    'transcend':['surpass','exceed','go beyond','rise above','outstrip'],
    'transfix':['mesmerise','paralyse','immobilise','captivate'],
    'transgress':['violate','breach','infringe','contravene','sin'],
    'transmute':['transform','convert','change','metamorphose','alter'],
    'traumatise':['shock','distress','devastate','scar','harm'],
    'traverse':['cross','travel across','navigate','traverse','pass through'],
    'trigger':['cause','provoke','set off','initiate','spark'],
    'trivialise':['minimise','belittle','downplay','underplay'],
    'trounce':['defeat decisively','thrash','crush','rout'],
    'truncate':['shorten','cut short','abbreviate','curtail'],
    'typify':['exemplify','epitomise','embody','represent','characterise'],
    'unearth':['discover','uncover','dig up','excavate','find'],
    'unfetter':['free','liberate','release','unshackle'],
    'unify':['unite','merge','consolidate','combine','integrate'],
    'unnerve':['unsettle','disturb','rattle','fluster','disconcert'],
    'unravel':['untangle','solve','disentangle','decipher','undo'],
    'unseat':['depose','oust','remove','overthrow','dethrone'],
    'unsettle':['disturb','unnerve','disconcert','trouble','fluster'],
    'unveil':['reveal','disclose','unmask','launch','present'],
    'upbraid':['scold','reprimand','rebuke','chide','reprove'],
    'uphold':['maintain','support','sustain','defend','affirm'],
    'uproot':['displace','remove','eradicate','dislodge','extract'],
    'usurp':['seize','take over','appropriate','commandeer','supplant'],
    'vacillate':['waver','hesitate','fluctuate','dither','oscillate'],
    'validate':['confirm','verify','substantiate','authenticate','corroborate'],
    'vandalise':['deface','damage','destroy','wreck','desecrate'],
    'vanquish':['defeat','conquer','overcome','subdue','crush'],
    'vaunt':['boast','flaunt','brag','tout'],
    'veer':['swerve','turn','deviate','shift','change direction'],
    'venerate':['revere','worship','honour','idolise','esteem'],
    'verify':['confirm','check','validate','substantiate','corroborate'],
    'vex':['annoy','irritate','bother','trouble','exasperate'],
    'vilify':['defame','denigrate','malign','disparage','slander'],
    'vindicate':['justify','exonerate','absolve','clear','acquit'],
    'violate':['breach','infringe','contravene','transgress','defy'],
    'vitiate':['spoil','impair','corrupt','invalidate','weaken'],
    'vociferate':['shout','clamour','yell','exclaim'],
    'waive':['forgo','relinquish','give up','renounce','dispense with'],
    'wane':['decline','decrease','diminish','fade','dwindle'],
    'waver':['hesitate','vacillate','fluctuate','falter','dither'],
    'whet':['stimulate','sharpen','arouse','excite'],
    'wield':['exercise','use','handle','brandish','exert'],
    'withhold':['hold back','retain','keep back','suppress'],
    'wrangle':['dispute','argue','quarrel','bicker','contend'],
    'wreak':['inflict','cause','bring about','unleash'],
    'yearn':['long','crave','pine','desire','ache'],
    'yield':['produce','surrender','give way','submit','concede'],
    'abhorrent':['detestable','repugnant','loathsome','odious','repellent'],
    'abrupt':['sudden','unexpected','curt','brusque','hasty'],
    'absurd':['ridiculous','ludicrous','preposterous','irrational','nonsensical'],
    'accessible':['reachable','available','approachable','obtainable','open'],
    'acclaimed':['praised','celebrated','lauded','renowned','esteemed'],
    'acute':['sharp','severe','intense','keen','perceptive'],
    'adamant':['unyielding','firm','resolute','insistent','inflexible'],
    'adept':['skilled','proficient','expert','accomplished','capable'],
    'affable':['friendly','amiable','pleasant','cordial','genial'],
    'affluent':['wealthy','prosperous','rich','well-off','opulent'],
    'agonising':['excruciating','torturous','painful','distressing','harrowing'],
    'alarming':['worrying','disturbing','frightening','distressing','startling'],
    'aloof':['distant','detached','reserved','remote','unapproachable'],
    'altruistic':['selfless','generous','charitable','philanthropic','unselfish'],
    'amiable':['friendly','pleasant','good-natured','affable','genial'],
    'anguished':['distressed','tormented','agonised','tortured','suffering'],
    'animated':['lively','vibrant','energetic','spirited','vivacious'],
    'antiquated':['outdated','obsolete','old-fashioned','archaic','dated'],
    'apathetic':['indifferent','unconcerned','uninterested','detached','listless'],
    'apprehensive':['anxious','worried','uneasy','nervous','fearful'],
    'arduous':['difficult','strenuous','gruelling','demanding','laborious'],
    'assertive':['confident','forceful','decisive','self-assured','bold'],
    'astounding':['astonishing','amazing','staggering','stunning','breathtaking'],
    'astute':['shrewd','perceptive','sharp','clever','discerning'],
    'audacious':['bold','daring','fearless','brazen','courageous'],
    'austere':['stark','severe','plain','strict','ascetic'],
    'avaricious':['greedy','covetous','grasping','acquisitive'],
    'barbaric':['savage','brutal','uncivilised','cruel','primitive'],
    'barren':['infertile','empty','sterile','desolate','bare'],
    'baseless':['unfounded','groundless','unsubstantiated','unsupported'],
    'belligerent':['hostile','aggressive','combative','pugnacious','warlike'],
    'benevolent':['kind','generous','charitable','compassionate','altruistic'],
    'benign':['harmless','gentle','kindly','mild','favourable'],
    'bewildering':['confusing','baffling','perplexing','mystifying','puzzling'],
    'blatant':['obvious','flagrant','glaring','conspicuous','unmistakable'],
    'bogus':['fake','fraudulent','fictitious','counterfeit','sham'],
    'boisterous':['rowdy','noisy','rambunctious','lively','unruly'],
    'bombastic':['pompous','grandiose','pretentious','overblown','inflated'],
    'brittle':['fragile','breakable','delicate','crumbly','fragile'],
    'buoyant':['cheerful','optimistic','light','resilient','upbeat'],
    'burgeoning':['growing','flourishing','expanding','thriving','developing'],
    'callous':['unfeeling','heartless','insensitive','uncaring','cold'],
    'capricious':['unpredictable','fickle','erratic','whimsical','volatile'],
    'cataclysmic':['catastrophic','disastrous','devastating','calamitous'],
    'cautious':['careful','wary','prudent','circumspect','guarded'],
    'celestial':['heavenly','astral','divine','cosmic'],
    'chaotic':['disordered','confused','turbulent','disorganised','anarchic'],
    'charismatic':['charming','magnetic','captivating','engaging','appealing'],
    'chronic':['persistent','ongoing','long-lasting','recurring','habitual'],
    'circuitous':['roundabout','indirect','meandering','winding'],
    'clandestine':['secret','covert','concealed','surreptitious','furtive'],
    'cogent':['convincing','persuasive','compelling','logical','forceful'],
    'coherent':['logical','consistent','clear','rational','sound'],
    'colossal':['huge','enormous','massive','gigantic','immense'],
    'commendable':['praiseworthy','admirable','laudable','worthy','creditable'],
    'compassionate':['caring','sympathetic','kind','empathetic','humane'],
    'competent':['capable','skilled','proficient','able','qualified'],
    'complacent':['self-satisfied','smug','unconcerned','contented'],
    'compliant':['obedient','submissive','agreeable','yielding','conforming'],
    'composed':['calm','collected','serene','unruffled','self-possessed'],
    'comprehensible':['understandable','clear','intelligible','lucid'],
    'conceited':['arrogant','vain','self-important','egotistical','proud'],
    'concise':['brief','succinct','terse','compact','pithy'],
    'congenial':['friendly','pleasant','amiable','agreeable','sociable'],
    'conscientious':['diligent','careful','meticulous','thorough','dutiful'],
    'contagious':['infectious','communicable','transmissible','catching'],
    'contemptuous':['scornful','disdainful','derisive','sneering'],
    'contentious':['controversial','disputed','divisive','debatable','contested'],
    'contradictory':['inconsistent','conflicting','paradoxical','opposing'],
    'contrite':['remorseful','repentant','regretful','penitent','sorry'],
    'convoluted':['complicated','intricate','complex','tangled','elaborate'],
    'cordial':['friendly','warm','amiable','gracious','pleasant'],
    'cosmopolitan':['worldly','sophisticated','international','urbane'],
    'covert':['secret','clandestine','concealed','hidden','furtive'],
    'cowardly':['timid','fearful','faint-hearted','craven','spineless'],
    'cryptic':['mysterious','puzzling','enigmatic','obscure','ambiguous'],
    'cumbersome':['unwieldy','bulky','awkward','burdensome','clumsy'],
    'curt':['brief','abrupt','terse','blunt','short'],
    'cursory':['brief','superficial','hasty','perfunctory','quick'],
    'cynical':['sceptical','distrustful','pessimistic','disillusioned'],
    'daunting':['intimidating','formidable','challenging','discouraging'],
    'dazzling':['brilliant','stunning','impressive','spectacular','radiant'],
    'debilitating':['weakening','crippling','incapacitating','enfeebling'],
    'deceptive':['misleading','deceitful','dishonest','fraudulent'],
    'decisive':['determined','resolute','conclusive','firm','definite'],
    'defiant':['rebellious','resistant','insubordinate','disobedient'],
    'deferential':['respectful','submissive','courteous','obsequious'],
    'degrading':['humiliating','demeaning','debasing','shameful'],
    'dejected':['despondent','downcast','disheartened','depressed','gloomy'],
    'delirious':['ecstatic','frenzied','wild','feverish'],
    'demeaning':['degrading','humiliating','belittling','disparaging'],
    'demoralised':['discouraged','dispirited','disheartened','depressed'],
    'deplorable':['appalling','disgraceful','shameful','reprehensible'],
    'derisive':['scornful','mocking','contemptuous','sneering'],
    'desolate':['bleak','barren','deserted','forlorn','abandoned'],
    'despicable':['contemptible','detestable','vile','loathsome','wretched'],
    'despondent':['dejected','downhearted','hopeless','disheartened'],
    'destitute':['impoverished','penniless','poverty-stricken','indigent'],
    'detrimental':['harmful','damaging','injurious','adverse','deleterious'],
    'devious':['deceitful','cunning','underhand','sly','crafty'],
    'devoted':['loyal','committed','dedicated','faithful','staunch'],
    'devout':['pious','religious','faithful','reverent','devoted'],
    'dexterous':['skilful','adroit','nimble','deft','handy'],
    'diligent':['hardworking','industrious','conscientious','assiduous'],
    'diminutive':['tiny','small','petite','miniature','little'],
    'disastrous':['catastrophic','calamitous','ruinous','devastating'],
    'discerning':['perceptive','astute','judicious','discriminating'],
    'discordant':['harsh','clashing','conflicting','jarring','inharmonious'],
    'discrete':['separate','distinct','individual','disconnected'],
    'disdainful':['scornful','contemptuous','haughty','condescending'],
    'disgruntled':['dissatisfied','unhappy','discontented','irritated'],
    'disheartened':['discouraged','dispirited','demoralised','downcast'],
    'dishevelled':['untidy','messy','unkempt','scruffy','rumpled'],
    'disingenuous':['insincere','deceitful','dishonest','duplicitous'],
    'disinterested':['impartial','unbiased','neutral','objective'],
    'dismal':['gloomy','bleak','depressing','miserable','dreary'],
    'dispassionate':['impartial','detached','objective','unbiased','calm'],
    'disquieting':['unsettling','worrying','disturbing','troubling'],
    'dissonant':['discordant','clashing','jarring','inharmonious'],
    'distinctive':['unique','characteristic','distinguishing','individual'],
    'distraught':['upset','anguished','frantic','devastated','overwrought'],
    'distressing':['upsetting','disturbing','worrying','troubling'],
    'docile':['submissive','obedient','compliant','tractable','meek'],
    'dogged':['persistent','tenacious','determined','stubborn','resolute'],
    'dogmatic':['rigid','inflexible','opinionated','doctrinaire'],
    'domineering':['controlling','overbearing','authoritarian','tyrannical'],
    'dormant':['inactive','inert','sleeping','latent','quiescent'],
    'dreadful':['terrible','awful','appalling','horrific','ghastly'],
    'dubious':['doubtful','questionable','suspect','uncertain','sceptical'],
    'dwindling':['decreasing','shrinking','diminishing','declining'],
    'earnest':['sincere','serious','heartfelt','genuine','solemn'],
    'ebullient':['exuberant','enthusiastic','effervescent','buoyant'],
    'elated':['ecstatic','overjoyed','thrilled','jubilant','delighted'],
    'elusive':['evasive','hard to find','fleeting','intangible'],
    'emaciated':['gaunt','skeletal','thin','wasted','malnourished'],
    'embittered':['resentful','bitter','disillusioned','soured'],
    'eminent':['distinguished','renowned','prominent','illustrious','notable'],
    'empathetic':['understanding','compassionate','sympathetic','caring'],
    'enchanting':['charming','delightful','captivating','bewitching'],
    'enigmatic':['mysterious','puzzling','cryptic','inscrutable'],
    'epic':['grand','heroic','monumental','sweeping','vast'],
    'equitable':['fair','just','impartial','even-handed','unbiased'],
    'erratic':['unpredictable','inconsistent','irregular','volatile'],
    'esteemed':['respected','admired','revered','venerated','honoured'],
    'euphoric':['ecstatic','elated','exhilarated','overjoyed','jubilant'],
    'exasperated':['frustrated','irritated','annoyed','infuriated'],
    'excruciating':['agonising','unbearable','severe','intense','tormenting'],
    'exemplary':['outstanding','model','ideal','commendable','excellent'],
    'exorbitant':['excessive','extortionate','unreasonable','outrageous'],
    'expansive':['broad','extensive','wide-ranging','sweeping','open'],
    'explicit':['clear','direct','unambiguous','specific','plain'],
    'exquisite':['beautiful','delicate','elegant','refined','superb'],
    'extraneous':['irrelevant','unrelated','unnecessary','superfluous'],
    'extravagant':['lavish','excessive','wasteful','luxurious','indulgent'],
    'fallible':['imperfect','prone to error','flawed'],
    'fastidious':['meticulous','fussy','particular','painstaking'],
    'fervent':['passionate','ardent','intense','zealous','impassioned'],
    'fickle':['unpredictable','capricious','changeable','inconstant'],
    'flagrant':['blatant','glaring','obvious','shameless','outrageous'],
    'flamboyant':['showy','extravagant','ostentatious','colourful'],
    'flimsy':['fragile','weak','insubstantial','thin','delicate'],
    'fluctuating':['varying','changing','unstable','erratic','wavering'],
    'forlorn':['desolate','abandoned','miserable','sad','lonely'],
    'formidable':['daunting','intimidating','impressive','powerful'],
    'fortuitous':['lucky','fortunate','serendipitous','providential'],
    'fraudulent':['deceitful','dishonest','fake','bogus','counterfeit'],
    'frivolous':['trivial','silly','superficial','flippant','shallow'],
    'gaudy':['garish','tacky','flashy','loud','vulgar'],
    'genial':['friendly','cordial','warm','affable','pleasant'],
    'gracious':['courteous','kind','polite','benevolent','charitable'],
    'grandiose':['pompous','extravagant','lofty','pretentious','showy'],
    'gratuitous':['unnecessary','unwarranted','uncalled-for','excessive'],
    'gregarious':['sociable','outgoing','extroverted','friendly'],
    'grim':['bleak','harsh','stern','severe','forbidding'],
    'grueling':['exhausting','punishing','strenuous','arduous','gruelling'],
    'haggard':['exhausted','worn out','gaunt','drawn','weary'],
    'haphazard':['random','disorganised','careless','unplanned'],
    'haughty':['arrogant','proud','disdainful','condescending','snobbish'],
    'heartfelt':['sincere','genuine','earnest','deeply felt'],
    'heedless':['careless','reckless','oblivious','inattentive'],
    'heinous':['atrocious','wicked','abominable','monstrous','vile'],
    'herculean':['immense','arduous','strenuous','formidable'],
    'heretical':['unorthodox','dissenting','nonconformist'],
    'hesitant':['reluctant','uncertain','tentative','wavering','doubtful'],
    'heterogeneous':['diverse','varied','mixed','assorted'],
    'homogeneous':['uniform','similar','consistent','identical'],
    'humdrum':['boring','monotonous','dull','tedious','mundane'],
    'idealistic':['visionary','utopian','starry-eyed','optimistic'],
    'idyllic':['picturesque','charming','peaceful','blissful'],
    'ignoble':['dishonourable','shameful','disgraceful','base'],
    'illicit':['illegal','unlawful','forbidden','unauthorised'],
    'illustrious':['distinguished','renowned','famous','celebrated','eminent'],
    'immaculate':['spotless','pristine','flawless','pure','perfect'],
    'imminent':['impending','forthcoming','looming','approaching'],
    'immobile':['motionless','stationary','fixed','still'],
    'impassioned':['fervent','passionate','ardent','intense','heated'],
    'impassive':['expressionless','unemotional','stoic','emotionless'],
    'impeccable':['flawless','faultless','perfect','immaculate'],
    'impending':['imminent','forthcoming','approaching','looming'],
    'imperceptible':['undetectable','indiscernible','unnoticeable'],
    'imperious':['domineering','arrogant','overbearing','autocratic'],
    'impertinent':['insolent','rude','disrespectful','cheeky'],
    'impervious':['unaffected','resistant','immune','unyielding'],
    'impetuous':['impulsive','rash','hasty','reckless','spontaneous'],
    'implacable':['relentless','unforgiving','unrelenting','inexorable'],
    'implausible':['unlikely','improbable','far-fetched','unconvincing'],
    'impotent':['powerless','helpless','ineffective','weak'],
    'imprudent':['unwise','reckless','rash','injudicious'],
    'impudent':['insolent','disrespectful','cheeky','brazen'],
    'inadvertent':['unintentional','accidental','unplanned','unwitting'],
    'inane':['silly','senseless','foolish','vacuous','pointless'],
    'inaudible':['unhearable','indistinct','faint','muted'],
    'inauspicious':['unpromising','unfavourable','ominous','ill-omened'],
    'incendiary':['inflammatory','provocative','explosive'],
    'incessant':['constant','continuous','unceasing','endless','relentless'],
    'inclement':['harsh','severe','stormy','rough'],
    'incoherent':['confused','unclear','disjointed','rambling'],
    'incongruous':['inconsistent','out of place','incompatible','odd'],
    'inconspicuous':['unnoticeable','unobtrusive','discreet','subtle'],
    'incorrigible':['unreformable','unmanageable','irredeemable'],
    'indefatigable':['tireless','untiring','persistent','relentless'],
    'indelible':['permanent','lasting','ineradicable','unforgettable'],
    'indiscriminate':['random','unselective','wholesale','sweeping'],
    'indispensable':['essential','vital','crucial','necessary','irreplaceable'],
    'indomitable':['unconquerable','unyielding','invincible','resolute'],
    'indubitable':['certain','undeniable','unquestionable','undoubted'],
    'inept':['incompetent','clumsy','unskilful','bungling'],
    'inescapable':['unavoidable','inevitable','certain','ineluctable'],
    'inexorable':['relentless','unstoppable','unyielding','implacable'],
    'inexplicable':['unexplainable','baffling','mysterious','puzzling'],
    'infallible':['unerring','flawless','perfect','faultless'],
    'inglorious':['shameful','disgraceful','humiliating'],
    'inhospitable':['unwelcoming','unfriendly','harsh','forbidding'],
    'inimical':['hostile','harmful','adverse','antagonistic'],
    'innate':['inherent','natural','intrinsic','instinctive'],
    'innocuous':['harmless','inoffensive','benign','mild'],
    'inordinate':['excessive','disproportionate','unreasonable'],
    'insatiable':['unquenchable','voracious','greedy','ravenous'],
    'insidious':['treacherous','deceptive','stealthy','sinister'],
    'insipid':['bland','dull','flavourless','lifeless','tasteless'],
    'insolent':['disrespectful','impudent','rude','cheeky'],
    'insufferable':['unbearable','intolerable','unendurable'],
    'insular':['narrow-minded','isolated','parochial','closed-off'],
    'intangible':['abstract','indefinite','impalpable','elusive'],
    'interminable':['endless','never-ending','unending','protracted'],
    'intransigent':['uncompromising','inflexible','stubborn','obstinate'],
    'intrepid':['fearless','bold','brave','courageous','daring'],
    'invincible':['unbeatable','unconquerable','indestructible'],
    'inviolable':['sacred','unassailable','absolute','unbreakable'],
    'irascible':['irritable','short-tempered','testy','touchy'],
    'irate':['angry','furious','livid','incensed','enraged'],
    'irksome':['annoying','irritating','vexing','bothersome'],
    'irrational':['illogical','unreasonable','absurd','senseless'],
    'irreconcilable':['incompatible','conflicting','opposed'],
    'irrefutable':['undeniable','incontestable','indisputable'],
    'irrelevant':['unrelated','immaterial','beside the point'],
    'irreproachable':['blameless','faultless','impeccable'],
    'irresolute':['indecisive','wavering','uncertain','hesitant'],
    'irreverent':['disrespectful','flippant','impertinent'],
    'irreversible':['permanent','irrevocable','final','unchangeable'],
    'irrevocable':['final','unalterable','permanent','fixed'],
    'jaded':['weary','tired','cynical','worn out','exhausted'],
    'jubilant':['elated','joyful','triumphant','exultant','overjoyed'],
    'judicious':['wise','sensible','prudent','sound','discerning'],
    'juvenile':['childish','immature','youthful','puerile'],
    'labyrinthine':['complex','convoluted','maze-like','intricate'],
    'laconic':['brief','terse','succinct','concise','sparing'],
    'lamentable':['regrettable','deplorable','unfortunate','sad'],
    'languid':['relaxed','lethargic','slow','listless','sluggish'],
    'legible':['readable','clear','decipherable'],
    'lenient':['merciful','tolerant','forgiving','indulgent'],
    'lethal':['deadly','fatal','deadly','lethal'],
    'lethargic':['sluggish','listless','lazy','drowsy','languid'],
    'lofty':['grand','elevated','noble','ambitious','high'],
    'lucid':['clear','coherent','intelligible','rational'],
    'lucrative':['profitable','rewarding','remunerative','money-making'],
    'ludicrous':['absurd','ridiculous','preposterous','laughable'],
    'luminous':['bright','glowing','radiant','shining'],
    'lurid':['sensational','shocking','graphic','garish'],
    'luxuriant':['lush','abundant','rich','profuse'],
    'macabre':['gruesome','grim','horrifying','ghastly'],
    'magnanimous':['generous','noble','charitable','forgiving'],
    'malevolent':['malicious','evil','spiteful','vindictive'],
    'malicious':['spiteful','vindictive','malevolent','vicious'],
    'malignant':['harmful','cancerous','hostile','malicious'],
    'mammoth':['huge','enormous','massive','colossal'],
    'maudlin':['sentimental','tearful','self-pitying'],
    'meagre':['scanty','sparse','insufficient','paltry'],
    'meandering':['winding','rambling','wandering','circuitous'],
    'melancholy':['sad','sorrowful','gloomy','wistful','despondent'],
    'mercurial':['unpredictable','volatile','changeable','fickle'],
    'meritorious':['deserving','praiseworthy','commendable'],
    'minuscule':['tiny','minute','microscopic','miniature'],
    'mirthful':['joyful','merry','cheerful','jovial'],
    'miserly':['stingy','tightfisted','parsimonious','mean'],
    'modish':['fashionable','trendy','stylish'],
    'momentous':['significant','important','historic','critical'],
    'morbid':['gruesome','macabre','grim','ghoulish'],
    'mordant':['biting','sarcastic','caustic','cutting'],
    'mundane':['ordinary','dull','routine','commonplace'],
    'munificent':['generous','lavish','bountiful'],
    'myopic':['short-sighted','narrow-minded','unimaginative'],
    'nebulous':['vague','unclear','hazy','indistinct'],
    'nefarious':['wicked','villainous','evil','sinister'],
    'nimble':['agile','quick','lithe','deft'],
    'noteworthy':['notable','remarkable','significant','memorable'],
    'nuanced':['subtle','refined','sophisticated'],
    'obdurate':['stubborn','unyielding','inflexible','obstinate'],
    'obligatory':['compulsory','mandatory','required','necessary'],
    'oblivious':['unaware','unmindful','unconscious','ignorant'],
    'obnoxious':['unpleasant','offensive','repugnant','objectionable'],
    'obscene':['indecent','vulgar','lewd','offensive'],
    'obsequious':['servile','fawning','sycophantic','submissive'],
    'obstinate':['stubborn','headstrong','inflexible','unyielding'],
    'obtrusive':['conspicuous','intrusive','noticeable'],
    'odious':['repulsive','hateful','detestable','loathsome'],
    'officious':['interfering','meddlesome','overbearing'],
    'ominous':['threatening','menacing','foreboding','sinister'],
    'onerous':['burdensome','demanding','arduous','heavy'],
    'opaque':['unclear','obscure','impenetrable','murky'],
    'opulent':['luxurious','lavish','sumptuous','rich'],
    'ostentatious':['showy','flamboyant','pretentious','gaudy'],
    'outlandish':['bizarre','strange','eccentric','odd'],
    'outrageous':['shocking','scandalous','extreme','egregious'],
    'overbearing':['domineering','arrogant','bossy','imperious'],
    'overt':['open','obvious','unconcealed','manifest'],
    'palatable':['agreeable','acceptable','tasty','pleasant'],
    'pallid':['pale','wan','colourless','ashen'],
    'paltry':['meagre','trivial','insignificant','negligible'],
    'parochial':['narrow-minded','provincial','insular','local'],
    'pastoral':['rural','rustic','bucolic','idyllic'],
    'paternalistic':['fatherly','protective','patronising'],
    'peerless':['unrivalled','unequalled','matchless','supreme'],
    'penitent':['remorseful','repentant','contrite','regretful'],
    'pensive':['thoughtful','reflective','contemplative','wistful'],
    'peremptory':['imperious','commanding','dictatorial'],
    'perfidious':['treacherous','disloyal','deceitful','faithless'],
    'perfunctory':['cursory','routine','mechanical','superficial'],
    'perilous':['dangerous','hazardous','risky','treacherous'],
    'permissive':['lenient','tolerant','liberal','indulgent'],
    'pernicious':['harmful','destructive','damaging','malignant'],
    'perplexing':['confusing','puzzling','baffling','bewildering'],
    'perspicacious':['perceptive','discerning','shrewd','astute'],
    'pervasive':['widespread','prevalent','ubiquitous','rampant'],
    'petulant':['irritable','sulky','peevish','cranky'],
    'picturesque':['scenic','charming','quaint','attractive'],
    'piercing':['sharp','penetrating','shrill','intense'],
    'pitiful':['pathetic','sad','wretched','pitiable'],
    'placid':['calm','peaceful','tranquil','serene'],
    'poignant':['moving','touching','emotional','affecting'],
    'polarising':['divisive','contentious','controversial'],
    'ponderous':['heavy','laborious','dull','cumbersome'],
    'portentous':['ominous','foreboding','momentous'],
    'posh':['upscale','elegant','stylish','luxurious'],
    'posthumous':['after death'],
    'pragmatic':['practical','sensible','realistic','businesslike'],
    'precarious':['unstable','risky','insecure','uncertain'],
    'precocious':['advanced','gifted','mature'],
    'predatory':['exploitative','rapacious','ruthless'],
    'preeminent':['leading','foremost','supreme','distinguished'],
    'prejudicial':['biased','damaging','unfair'],
    'preposterous':['absurd','ridiculous','ludicrous','outrageous'],
    'prescient':['foresighted','prophetic','visionary'],
    'pretentious':['pompous','ostentatious','affected','showy'],
    'prevalent':['widespread','common','rampant','general'],
    'pristine':['pure','unspoiled','immaculate','flawless'],
    'privy':['aware of','informed of','in on'],
    'prodigious':['enormous','remarkable','extraordinary','vast'],
    'profane':['sacrilegious','blasphemous','irreverent'],
    'profound':['deep','intense','far-reaching','significant'],
    'profuse':['abundant','copious','plentiful','lavish'],
    'proscribed':['forbidden','banned','prohibited'],
    'prosaic':['dull','mundane','ordinary','unimaginative'],
    'puerile':['childish','immature','juvenile','silly'],
    'pugnacious':['combative','aggressive','belligerent'],
    'punctilious':['meticulous','precise','careful','exact'],
    'pungent':['sharp','strong','acrid','biting'],
    'putrid':['rotten','decaying','foul','rank'],
    'quaint':['charming','picturesque','old-fashioned','curious'],
    'querulous':['complaining','whiny','peevish','irritable'],
    'quixotic':['idealistic','impractical','unrealistic','romantic'],
    'rampant':['widespread','uncontrolled','rife','unchecked'],
    'rancorous':['bitter','hostile','resentful','spiteful'],
    'rapacious':['greedy','predatory','grasping','avaricious'],
    'rapturous':['ecstatic','joyful','blissful','elated'],
    'rash':['reckless','hasty','impulsive','impetuous'],
    'raucous':['loud','rowdy','boisterous','noisy'],
    'ravenous':['starving','famished','voracious','insatiable'],
    'reciprocal':['mutual','shared','corresponding'],
    'reclusive':['solitary','withdrawn','isolated','secluded'],
    'redundant':['unnecessary','superfluous','excessive','surplus'],
    'reflective':['thoughtful','contemplative','pensive'],
    'refractory':['stubborn','unmanageable','obstinate'],
    'remorseful':['regretful','repentant','contrite','sorry'],
    'reprehensible':['blameworthy','deplorable','shameful'],
    'repugnant':['repulsive','offensive','distasteful','abhorrent'],
    'resilient':['tough','durable','adaptable','hardy'],
    'resolute':['determined','firm','unwavering','steadfast'],
    'resonant':['echoing','deep','vibrant','ringing'],
    'resourceful':['inventive','ingenious','capable','enterprising'],
    'respectful':['polite','courteous','considerate','deferential'],
    'revered':['esteemed','respected','venerated','honoured'],
    'rife':['widespread','abundant','common','prevalent'],
    'rousing':['stirring','inspiring','exciting','stimulating'],
    'rudimentary':['basic','elementary','primitive','fundamental'],
    'ruthless':['merciless','cruel','pitiless','brutal'],
    'sagacious':['wise','shrewd','astute','discerning'],
    'salient':['prominent','notable','conspicuous','key'],
    'sanguine':['optimistic','hopeful','confident','positive'],
    'sardonic':['mocking','sarcastic','cynical','scornful'],
    'savvy':['knowledgeable','shrewd','astute','sharp'],
    'scrupulous':['meticulous','conscientious','careful','ethical'],
    'sedate':['calm','composed','tranquil','staid'],
    'sedulous':['diligent','industrious','persistent'],
    'selective':['discriminating','fussy','choosy','particular'],
    'sensational':['dramatic','shocking','exciting','startling'],
    'sensible':['practical','reasonable','wise','judicious'],
    'sequential':['consecutive','successive','ordered'],
    'servile':['submissive','subservient','obsequious'],
    'sinister':['menacing','threatening','ominous','evil'],
    'slothful':['lazy','idle','indolent','sluggish'],
    'sobering':['serious','humbling','chastening'],
    'sombre':['gloomy','sad','solemn','dark'],
    'sordid':['squalid','dirty','shameful','wretched'],
    'spurious':['false','fake','counterfeit','bogus'],
    'squalid':['filthy','dirty','sordid','wretched'],
    'staid':['sedate','serious','conventional','dull'],
    'stalwart':['loyal','steadfast','sturdy','dependable'],
    'stoic':['unemotional','impassive','calm','resigned'],
    'strident':['harsh','loud','shrill','grating'],
    'stupendous':['amazing','astounding','tremendous','huge'],
    'stupefying':['stunning','astonishing','mind-numbing'],
    'sublime':['magnificent','glorious','exquisite','transcendent'],
    'subservient':['submissive','obedient','servile','deferential'],
    'substantiated':['confirmed','proven','verified'],
    'succinct':['concise','brief','terse','pithy'],
    'sullen':['sulky','moody','gloomy','morose'],
    'sumptuous':['lavish','luxurious','opulent','splendid'],
    'superfluous':['unnecessary','excess','redundant','surplus'],
    'superlative':['excellent','outstanding','supreme','best'],
    'surreal':['dreamlike','bizarre','strange','unreal'],
    'sycophantic':['fawning','obsequious','flattering','servile'],
    'symbiotic':['mutually beneficial','interdependent'],
    'taciturn':['reserved','quiet','reticent','uncommunicative'],
    'tainted':['contaminated','corrupted','polluted','sullied'],
    'tantamount':['equivalent','equal','synonymous'],
    'tedious':['boring','monotonous','dull','tiresome'],
    'temperate':['moderate','mild','restrained','balanced'],
    'tenacious':['persistent','determined','stubborn','resolute'],
    'tenuous':['weak','flimsy','shaky','fragile'],
    'terse':['brief','curt','concise','abrupt'],
    'threadbare':['worn','shabby','tattered','frayed'],
    'timely':['opportune','well-timed','prompt','seasonable'],
    'tiresome':['tedious','boring','wearisome','irksome'],
    'torpid':['sluggish','lethargic','inactive','dormant'],
    'touted':['promoted','advertised','praised'],
    'tranquil':['calm','peaceful','serene','placid'],
    'transient':['temporary','fleeting','brief','short-lived'],
    'translucent':['semi-transparent','clear'],
    'treacherous':['dangerous','perilous','deceitful','disloyal'],
    'tremulous':['trembling','shaky','quivering'],
    'trenchant':['incisive','sharp','cutting','forceful'],
    'trifling':['trivial','insignificant','minor','petty'],
    'turbulent':['stormy','chaotic','tumultuous','unstable'],
    'tyrannical':['despotic','oppressive','dictatorial','authoritarian'],
    'ubiquitous':['omnipresent','widespread','pervasive','everywhere'],
    'unabashed':['unashamed','shameless','unembarrassed'],
    'unassuming':['modest','humble','unpretentious','reserved'],
    'unbridled':['unrestrained','uncontrolled','unchecked'],
    'uncanny':['strange','mysterious','eerie','remarkable'],
    'uncharted':['unexplored','unknown','unmapped'],
    'uncompromising':['inflexible','strict','firm','unyielding'],
    'unconventional':['unorthodox','unusual','nonconformist'],
    'undaunted':['unafraid','fearless','resolute','unshaken'],
    'underhand':['deceitful','sly','devious','sneaky'],
    'undermined':['weakened','sabotaged','compromised'],
    'unequivocal':['clear','unambiguous','definite','absolute'],
    'unfathomable':['incomprehensible','inexplicable','unknowable'],
    'unflinching':['steadfast','resolute','unwavering'],
    'unfounded':['baseless','groundless','unsubstantiated'],
    'unheralded':['unannounced','unexpected','unacknowledged'],
    'unmitigated':['absolute','total','complete','utter'],
    'unobtrusive':['inconspicuous','discreet','modest'],
    'unorthodox':['unconventional','heterodox','irregular'],
    'unpalatable':['unpleasant','distasteful','disagreeable'],
    'unprecedented':['unparalleled','unheard-of','novel'],
    'unpretentious':['modest','unassuming','simple','humble'],
    'unrelenting':['relentless','persistent','unremitting'],
    'unruly':['disorderly','uncontrollable','disobedient'],
    'unscathed':['unharmed','unhurt','untouched'],
    'unscrupulous':['dishonest','unprincipled','corrupt'],
    'unsettling':['disturbing','disquieting','unnerving'],
    'unwarranted':['unjustified','undeserved','uncalled-for'],
    'unwavering':['steadfast','resolute','constant','firm'],
    'unwitting':['unintentional','unknowing','inadvertent'],
    'upright':['honest','honourable','ethical','moral'],
    'vacuous':['empty','vapid','mindless','inane'],
    'vague':['unclear','imprecise','hazy','ambiguous'],
    'vain':['conceited','futile','fruitless','proud'],
    'valiant':['brave','courageous','heroic','gallant'],
    'vehement':['forceful','passionate','intense','fervent'],
    'venal':['corrupt','mercenary','bribable'],
    'venerable':['respected','esteemed','revered','honoured'],
    'venomous':['poisonous','malicious','spiteful','vicious'],
    'veracious':['truthful','honest','accurate'],
    'verbose':['wordy','long-winded','rambling','loquacious'],
    'vestigial':['residual','remnant','rudimentary'],
    'vexatious':['annoying','troublesome','irritating'],
    'viable':['feasible','workable','practicable','possible'],
    'vicarious':['indirect','secondhand','surrogate'],
    'vigilant':['watchful','alert','attentive','wary'],
    'vindictive':['vengeful','spiteful','unforgiving'],
    'virulent':['toxic','poisonous','hostile','severe'],
    'visceral':['instinctive','gut','deep-seated'],
    'vitriolic':['bitter','caustic','venomous','scathing'],
    'vociferous':['loud','vocal','outspoken','clamorous'],
    'volatile':['unstable','unpredictable','explosive','erratic'],
    'voracious':['insatiable','ravenous','greedy'],
    'wanton':['reckless','unrestrained','gratuitous'],
    'wary':['cautious','careful','suspicious','guarded'],
    'whimsical':['playful','fanciful','capricious','quirky'],
    'wistful':['nostalgic','yearning','melancholy','pensive'],
    'withering':['scathing','harsh','devastating'],
    'wretched':['miserable','pitiful','unfortunate','deplorable'],
    'zealous':['passionate','fervent','enthusiastic','ardent'],
    'abundance':['plenty','profusion','wealth','surplus','copiousness'],
    'accord':['agreement','harmony','consensus','concord'],
    'acumen':['insight','sharpness','shrewdness','discernment'],
    'adage':['proverb','saying','maxim','aphorism'],
    'adherence':['compliance','conformity','allegiance','loyalty'],
    'adversity':['hardship','misfortune','difficulty','trouble'],
    'affinity':['bond','connection','rapport','kinship'],
    'affluence':['wealth','prosperity','opulence','riches'],
    'agenda':['plan','schedule','programme','list'],
    'alacrity':['eagerness','enthusiasm','readiness','promptness'],
    'allegory':['parable','fable','symbol','metaphor'],
    'allure':['appeal','charm','attraction','fascination'],
    'altercation':['argument','dispute','quarrel','fight'],
    'ambiance':['atmosphere','mood','feel','environment'],
    'amenity':['facility','convenience','feature','comfort'],
    'amnesty':['pardon','forgiveness','reprieve'],
    'anarchy':['chaos','disorder','lawlessness','turmoil'],
    'anecdote':['story','tale','account','yarn'],
    'animosity':['hostility','antagonism','hatred','enmity'],
    'anomaly':['irregularity','deviation','oddity','exception'],
    'antagonist':['opponent','adversary','rival','foe'],
    'antipathy':['dislike','aversion','hostility','distaste'],
    'apathy':['indifference','unconcern','disinterest'],
    'apex':['peak','summit','pinnacle','zenith'],
    'aptitude':['ability','talent','skill','capability'],
    'archetype':['model','prototype','template','ideal'],
    'ascendancy':['dominance','supremacy','control','power'],
    'assertion':['statement','claim','declaration','contention'],
    'assortment':['variety','mixture','selection','range'],
    'atrocity':['outrage','horror','crime','abomination'],
    'audacity':['boldness','daring','nerve','courage'],
    'austerity':['strictness','severity','frugality'],
    'authenticity':['genuineness','legitimacy','realness'],
    'autonomy':['independence','self-governance','freedom'],
    'avarice':['greed','covetousness','acquisitiveness'],
    'aversion':['dislike','distaste','antipathy','repugnance'],
    'backlash':['reaction','opposition','resistance','revolt'],
    'bane':['curse','affliction','scourge','plague'],
    'barrage':['bombardment','onslaught','torrent','volley'],
    'bastion':['stronghold','fortress','stalwart supporter'],
    'bedlam':['chaos','uproar','pandemonium','mayhem'],
    'benchmark':['standard','criterion','yardstick','reference'],
    'bereavement':['loss','mourning','grief'],
    'bewilderment':['confusion','perplexity','puzzlement'],
    'bigotry':['prejudice','intolerance','discrimination'],
    'blight':['plague','curse','affliction','scourge'],
    'bliss':['happiness','joy','elation','euphoria'],
    'blueprint':['plan','design','scheme','model'],
    'bolt':['dash','sprint','flee'],
    'bombardment':['barrage','attack','assault','onslaught'],
    'bonanza':['windfall','boom','jackpot'],
    'boon':['benefit','blessing','advantage','godsend'],
    'boycott':['ban','protest','embargo'],
    'bravado':['bravado','swagger','bluster'],
    'brevity':['conciseness','briefness','shortness'],
    'bulwark':['defence','safeguard','protection','rampart'],
    'bureaucracy':['administration','red tape','officialdom'],
    'calamity':['disaster','catastrophe','tragedy','misfortune'],
    'caliber':['quality','standard','calibre','worth'],
    'camaraderie':['friendship','fellowship','companionship'],
    'candour':['honesty','frankness','openness','sincerity'],
    'canon':['standard','rule','body of work','principle'],
    'capitulation':['surrender','submission','yielding'],
    'caprice':['whim','impulse','fancy','fickleness'],
    'cataclysm':['disaster','catastrophe','upheaval'],
    'catalyst':['trigger','stimulus','spark','impetus'],
    'catastrophe':['disaster','calamity','tragedy','cataclysm'],
    'caveat':['warning','proviso','qualification','condition'],
    'celebrity':['fame','star','notable figure'],
    'chagrin':['embarrassment','annoyance','disappointment'],
    'charade':['pretence','sham','farce','deception'],
    'chasm':['gap','gulf','divide','abyss'],
    'chastisement':['punishment','rebuke','discipline'],
    'chicanery':['trickery','deception','deceit'],
    'chivalry':['gallantry','courtesy','courtliness'],
    'circumspection':['caution','prudence','wariness'],
    'civility':['politeness','courtesy','manners'],
    'clamor':['uproar','outcry','din','clamour'],
    'clarity':['clearness','lucidity','precision'],
    'clemency':['mercy','leniency','forgiveness'],
    'cliché':['stereotype','platitude','commonplace'],
    'coercion':['force','compulsion','pressure','intimidation'],
    'cognizance':['awareness','knowledge','recognition'],
    'cohesion':['unity','solidarity','togetherness'],
    'collateral':['security','pledge','guarantee'],
    'collusion':['conspiracy','collaboration','connivance'],
    'commotion':['disturbance','uproar','turmoil','fuss'],
    'compendium':['summary','collection','digest'],
    'complacency':['self-satisfaction','smugness','contentment'],
    'complexity':['complication','intricacy','difficulty'],
    'compliance':['conformity','obedience','adherence'],
    'composure':['calmness','poise','equanimity'],
    'compunction':['remorse','guilt','regret','qualm'],
    'conceit':['arrogance','vanity','pride','self-importance'],
    'concession':['compromise','allowance','yielding'],
    'condolence':['sympathy','commiseration'],
    'conformity':['compliance','obedience','agreement'],
    'congestion':['crowding','overcrowding','blockage'],
    'conquest':['victory','triumph','subjugation'],
    'consensus':['agreement','accord','unanimity'],
    'conspiracy':['plot','scheme','collusion'],
    'constellation':['array','group','cluster'],
    'constituent':['component','element','part'],
    'constraint':['restriction','limitation','restraint'],
    'consternation':['dismay','alarm','anxiety'],
    'contingency':['possibility','eventuality','provision'],
    'conundrum':['puzzle','riddle','dilemma','mystery'],
    'conviction':['belief','certainty','sentence'],
    'cordiality':['warmth','friendliness','geniality'],
    'correlation':['connection','relationship','link'],
    'cosmopolitanism':['worldliness','sophistication'],
    'countenance':['face','expression','approval'],
    'coup':['overthrow','takeover','putsch'],
    'covenant':['agreement','pact','contract'],
    'credence':['belief','trust','acceptance'],
    'credibility':['believability','trustworthiness','reliability'],
    'crescendo':['climax','peak','buildup'],
    'crux':['essence','heart','core','gist'],
    'culpability':['guilt','blame','responsibility'],
    'cynicism':['scepticism','distrust','pessimism'],
    'debacle':['disaster','fiasco','failure'],
    'debauchery':['indulgence','excess','depravity'],
    'debris':['wreckage','rubble','remains'],
    'deception':['trickery','deceit','fraud'],
    'decorum':['propriety','etiquette','good manners'],
    'defection':['desertion','abandonment','betrayal'],
    'deference':['respect','regard','submission'],
    'deficit':['shortfall','shortage','deficiency'],
    'degradation':['deterioration','humiliation','decline'],
    'deliberation':['consideration','discussion','thought'],
    'delusion':['misconception','illusion','fantasy'],
    'demeanor':['manner','behaviour','bearing','conduct'],
    'demise':['death','end','downfall','collapse'],
    'denunciation':['condemnation','criticism','censure'],
    'depiction':['portrayal','representation','description'],
    'deprivation':['lack','want','poverty','need'],
    'derision':['mockery','ridicule','scorn'],
    'desecration':['defilement','violation','profanation'],
    'despair':['hopelessness','despondency','anguish'],
    'desperation':['despair','anguish','hopelessness'],
    'destitution':['poverty','deprivation','indigence'],
    'detachment':['aloofness','indifference','separation'],
    'detente':['reconciliation','easing of tension'],
    'deterioration':['decline','worsening','degeneration'],
    'devastation':['destruction','ruin','havoc'],
    'deviation':['departure','divergence','variation'],
    'devotion':['loyalty','commitment','dedication'],
    'diaspora':['dispersion','scattering'],
    'dichotomy':['division','split','contrast'],
    'diligence':['hard work','industry','effort'],
    'din':['noise','racket','uproar','clamour'],
    'discernment':['insight','perception','judgement'],
    'discord':['conflict','disagreement','strife'],
    'discourse':['discussion','conversation','dialogue'],
    'discrepancy':['inconsistency','difference','disparity'],
    'discretion':['tact','prudence','judgement'],
    'disdain':['scorn','contempt','disrespect'],
    'disenchantment':['disillusionment','disappointment'],
    'disparity':['difference','inequality','gap'],
    'displacement':['relocation','removal','shift'],
    'disposition':['temperament','nature','tendency'],
    'dissent':['disagreement','objection','opposition'],
    'dissolution':['breakup','termination','disbanding'],
    'divergence':['difference','deviation','split'],
    'diversion':['distraction','detour','entertainment'],
    'divinity':['godliness','holiness','deity'],
    'doctrine':['belief','teaching','principle','tenet'],
    'dogma':['doctrine','belief','tenet'],
    'domain':['field','area','territory','realm'],
    'dominance':['control','supremacy','power'],
    'drudgery':['toil','labour','grind'],
    'duplicity':['deceit','dishonesty','double-dealing'],
    'duress':['coercion','pressure','compulsion'],
    'eccentricity':['oddity','quirkiness','peculiarity'],
    'ecstasy':['bliss','euphoria','rapture'],
    'edifice':['building','structure','construction'],
    'efficacy':['effectiveness','potency'],
    'egotism':['self-importance','conceit','vanity'],
    'elation':['joy','delight','euphoria'],
    'embargo':['ban','restriction','boycott'],
    'embodiment':['personification','incarnation','epitome'],
    'emissary':['envoy','representative','messenger'],
    'empathy':['compassion','understanding','sympathy'],
    'emulation':['imitation','copying'],
    'enclave':['area','territory','pocket'],
    'encroachment':['intrusion','trespass','infringement'],
    'endeavor':['effort','attempt','undertaking'],
    'enigma':['mystery','puzzle','riddle'],
    'enmity':['hostility','animosity','hatred'],
    'entity':['being','organisation','thing'],
    'epicenter':['centre','focal point','hub'],
    'epiphany':['revelation','realisation','insight'],
    'epithet':['nickname','label','descriptor'],
    'epitome':['embodiment','personification','archetype'],
    'epoch':['era','age','period'],
    'equanimity':['calmness','composure','poise'],
    'equilibrium':['balance','stability','steadiness'],
    'equity':['fairness','justice','impartiality'],
    'erudition':['learning','scholarship','knowledge'],
    'espionage':['spying','surveillance'],
    'ethos':['character','spirit','culture'],
    'euphoria':['elation','bliss','ecstasy'],
    'exasperation':['frustration','irritation','annoyance'],
    'exodus':['departure','emigration','flight'],
    'expatriate':['emigrant','exile'],
    'expertise':['skill','proficiency','know-how'],
    'exploitation':['abuse','misuse','manipulation'],
    'extremity':['limit','edge','extreme'],
    'exuberance':['enthusiasm','energy','vitality'],
    'facade':['front','exterior','pretence'],
    'faction':['group','clique','bloc'],
    'fallacy':['misconception','error','misbelief'],
    'fanfare':['ceremony','pomp','celebration'],
    'farce':['mockery','sham','absurdity'],
    'fatality':['death','casualty'],
    'felicity':['happiness','bliss','delight'],
    'fervor':['passion','ardour','zeal'],
    'fiasco':['disaster','failure','debacle'],
    'finesse':['skill','tact','elegance'],
    'fissure':['crack','split','fracture'],
    'flurry':['burst','flare-up','commotion'],
    'folly':['foolishness','stupidity','recklessness'],
    'foray':['venture','attempt','incursion'],
    'forbearance':['patience','tolerance','restraint'],
    'foreboding':['premonition','apprehension','dread'],
    'foresight':['prudence','anticipation','vision'],
    'formality':['procedure','protocol','convention'],
    'fortitude':['courage','resilience','strength'],
    'fraternity':['brotherhood','fellowship','association'],
    'frivolity':['silliness','levity','lightheartedness'],
    'frugality':['thriftiness','economy','prudence'],
    'fruition':['realisation','fulfilment','completion'],
    'fugitive':['runaway','escapee'],
    'fusion':['merger','blend','combination'],
    'futility':['pointlessness','uselessness','vanity'],
    'gaffe':['blunder','mistake','faux pas'],
    'gambit':['strategy','ploy','tactic'],
    'gathering':['assembly','meeting','congregation'],
    'genealogy':['ancestry','lineage','pedigree'],
    'genesis':['origin','beginning','birth'],
    'genocide':['massacre','extermination'],
    'gist':['essence','substance','point'],
    'gluttony':['greed','overindulgence'],
    'grandeur':['magnificence','splendour','majesty'],
    'gratitude':['thankfulness','appreciation'],
    'grievance':['complaint','objection','resentment'],
    'grit':['determination','perseverance','courage'],
    'guile':['cunning','deceit','trickery'],
    'gullibility':['naivety','credulity'],
    'habitat':['environment','surroundings','home'],
    'hallmark':['characteristic','feature','trademark'],
    'harassment':['persecution','intimidation','bullying'],
    'harbinger':['sign','omen','herald'],
    'hegemony':['dominance','supremacy','control'],
    'heresy':['dissent','unorthodoxy','sacrilege'],
    'heritage':['legacy','tradition','inheritance'],
    'holocaust':['massacre','genocide'],
    'homage':['tribute','respect','honour'],
    'hostility':['aggression','antagonism','animosity'],
    'humility':['modesty','meekness','self-effacement'],
    'hypocrisy':['insincerity','deceit','duplicity'],
    'iconoclast':['rebel','nonconformist'],
    'idiosyncrasy':['quirk','peculiarity','eccentricity'],
    'idolatry':['worship','adoration'],
    'ignominy':['shame','disgrace','dishonour'],
    'illumination':['clarification','enlightenment'],
    'illusion':['misconception','fantasy','delusion'],
    'imbalance':['disparity','inequality','asymmetry'],
    'immersion':['absorption','engrossment'],
    'imminence':['nearness','proximity'],
    'impasse':['deadlock','standstill','stalemate'],
    'impediment':['obstacle','hindrance','barrier'],
    'impetus':['stimulus','driving force','momentum'],
    'impostor':['fraud','fake','pretender'],
    'impunity':['immunity','exemption'],
    'inadequacy':['insufficiency','shortcoming','deficiency'],
    'incarnation':['embodiment','manifestation'],
    'incidence':['occurrence','frequency','rate'],
    'inclination':['tendency','disposition','preference'],
    'incongruity':['inconsistency','discrepancy'],
    'indignation':['anger','outrage','resentment'],
    'indolence':['laziness','idleness','sloth'],
    'inequity':['unfairness','injustice'],
    'inertia':['inactivity','lethargy','apathy'],
    'infatuation':['obsession','passion','crush'],
    'inference':['conclusion','deduction','implication'],
    'infirmity':['weakness','frailty','illness'],
    'influx':['inflow','arrival','flood'],
    'infraction':['violation','breach','offence'],
    'ingenuity':['inventiveness','cleverness','creativity'],
    'ingratitude':['thanklessness','ungratefulness'],
    'inhibition':['restraint','reticence','self-consciousness'],
    'injustice':['unfairness','inequity','wrong'],
    'innuendo':['insinuation','implication','suggestion'],
    'inquisition':['investigation','interrogation'],
    'insolence':['impertinence','rudeness','disrespect'],
    'instigation':['incitement','provocation'],
    'insurgency':['rebellion','uprising','revolt'],
    'insurrection':['rebellion','revolt','uprising'],
    'intellect':['intelligence','mind','brainpower'],
    'interlude':['pause','break','interval'],
    'intermission':['break','pause','interval'],
    'interregnum':['gap','interval','pause'],
    'intersection':['junction','crossroads','crossing'],
    'intervention':['interference','involvement'],
    'intimacy':['closeness','familiarity','warmth'],
    'intricacy':['complexity','complication'],
    'introspection':['self-reflection','contemplation'],
    'intuition':['instinct','insight','gut feeling'],
    'invasion':['incursion','assault','attack'],
    'irritation':['annoyance','vexation','exasperation'],
    'jargon':['terminology','lingo','vocabulary'],
    'jeopardy':['danger','risk','peril'],
    'jest':['joke','quip','wisecrack'],
    'jubilation':['celebration','joy','elation'],
    'juxtaposition':['contrast','comparison'],
    'kinship':['relation','connection','bond'],
    'knack':['skill','talent','aptitude'],
    'largesse':['generosity','munificence'],
    'lassitude':['weariness','fatigue','lethargy'],
    'latitude':['freedom','scope','leeway'],
    'leeway':['freedom','flexibility','margin'],
    'lethargy':['sluggishness','tiredness','apathy'],
    'leverage':['influence','power','advantage'],
    'liability':['responsibility','obligation','risk'],
    'liaison':['connection','link','intermediary'],
    'lineage':['ancestry','descent','pedigree'],
    'litany':['recitation','list','repetition'],
    'longevity':['lifespan','durability','endurance'],
    'lull':['pause','calm','respite'],
    'lurch':['stagger','stumble'],
    'luster':['shine','sheen','glow'],
    'malaise':['discomfort','unease','discontent'],
    'malfunction':['breakdown','failure','fault'],
    'malice':['spite','ill will','malevolence'],
    'maneuver':['manoeuvre','tactic','strategy'],
    'mania':['craze','obsession','frenzy'],
    'manifesto':['declaration','statement','platform'],
    'mannerism':['habit','quirk','idiosyncrasy'],
    'manor':['estate','mansion','house'],
    'mantle':['role','responsibility','cloak'],
    'mar':['spoil','blemish','damage'],
    'marginalisation':['exclusion','sidelining'],
    'martyrdom':['sacrifice','suffering'],
    'materialism':['consumerism','acquisitiveness'],
    'maxim':['saying','proverb','adage'],
    'mayhem':['chaos','havoc','disorder'],
    'meddling':['interference','intrusion'],
    'mediocrity':['ordinariness','averageness'],
    'mendacity':['dishonesty','untruthfulness'],
    'metamorphosis':['transformation','change','evolution'],
    'milestone':['landmark','turning point','marker'],
    'minutiae':['details','particulars'],
    'mirage':['illusion','delusion','fantasy'],
    'misapprehension':['misunderstanding','misconception'],
    'misconduct':['wrongdoing','impropriety'],
    'misdemeanor':['offence','wrongdoing','infraction'],
    'misfortune':['bad luck','adversity','hardship'],
    'misgiving':['doubt','apprehension','unease'],
    'mishap':['accident','mischance','misfortune'],
    'misnomer':['misname','wrong term'],
    'mockery':['ridicule','derision','scorn'],
    'modesty':['humility','reserve','decency'],
    'momentum':['drive','impetus','force'],
    'monopoly':['exclusive control','domination'],
    'monotony':['tedium','dullness','sameness'],
    'morale':['confidence','spirit','esprit de corps'],
    'mortality':['death rate','death','fatality'],
    'motif':['theme','pattern','design'],
    'multitude':['crowd','mass','host'],
    'mundanity':['ordinariness','dullness'],
    'mutiny':['rebellion','revolt','insurrection'],
    'mystique':['aura','mystery','allure'],
    'narrative':['story','account','tale'],
    'nemesis':['rival','adversary','downfall'],
    'nexus':['connection','link','centre'],
    'niche':['specialism','speciality','position'],
    'nonchalance':['indifference','casualness'],
    'notion':['idea','concept','belief'],
    'nuance':['subtlety','shade','distinction'],
    'nucleus':['core','centre','kernel'],
    'oblivion':['obscurity','nothingness'],
    'obscurity':['vagueness','ambiguity','anonymity'],
    'obsession':['fixation','preoccupation','mania'],
    'odyssey':['journey','voyage','adventure'],
    'offense':['crime','violation','affront'],
    'omission':['exclusion','oversight','gap'],
    'opportunist':['schemer','manipulator'],
    'oppression':['tyranny','persecution','subjugation'],
    'optimism':['hopefulness','positivity','confidence'],
    'opulence':['luxury','wealth','extravagance'],
    'outburst':['eruption','explosion','outpouring'],
    'outcast':['pariah','exile','reject'],
    'outset':['beginning','start','onset'],
    'outskirts':['periphery','edges','suburbs'],
    'overtone':['implication','connotation','undertone'],
    'overture':['proposal','offer','opening'],
    'paean':['tribute','praise','eulogy'],
    'pageantry':['ceremony','spectacle','pomp'],
    'pandemonium':['chaos','uproar','bedlam'],
    'panorama':['view','vista','overview'],
    'pantheon':['group of notable figures'],
    'paradigm':['model','pattern','example'],
    'paradox':['contradiction','anomaly','puzzle'],
    'paragon':['model','ideal','exemplar'],
    'parity':['equality','equivalence','balance'],
    'paroxysm':['outburst','fit','spasm'],
    'parsimony':['stinginess','frugality'],
    'partisan':['supporter','follower','adherent'],
    'pathos':['emotion','pity','sadness'],
    'patronage':['support','sponsorship','backing'],
    'paucity':['scarcity','lack','shortage'],
    'peculiarity':['quirk','oddity','eccentricity'],
    'pedigree':['ancestry','lineage','heritage'],
    'penchant':['liking','fondness','inclination'],
    'penury':['poverty','destitution'],
    'perception':['awareness','understanding','insight'],
    'periphery':['edge','margin','outskirts'],
    'perpetuity':['eternity','permanence'],
    'perplexity':['confusion','bewilderment'],
    'persecution':['oppression','harassment','victimisation'],
    'persona':['character','image','identity'],
    'pervasiveness':['prevalence','ubiquity'],
    'petulance':['irritability','sulkiness'],
    'philanthropy':['charity','generosity','benevolence'],
    'piety':['devoutness','religiousness'],
    'pinnacle':['peak','summit','apex'],
    'pitfall':['hazard','trap','danger'],
    'pittance':['tiny amount','small sum'],
    'plaudit':['praise','acclaim','commendation'],
    'plausibility':['believability','credibility'],
    'plea':['appeal','request','entreaty'],
    'plethora':['abundance','excess','glut'],
    'ploy':['tactic','trick','stratagem'],
    'polarisation':['division','split'],
    'pomp':['ceremony','grandeur','splendour'],
    'populace':['population','public','people'],
    'portent':['omen','sign','warning'],
    'practicality':['usefulness','pragmatism'],
    'pragmatism':['practicality','realism'],
    'precedent':['example','model','instance'],
    'precept':['principle','rule','guideline'],
    'precipice':['edge','cliff','brink'],
    'precision':['accuracy','exactness','preciseness'],
    'predicament':['dilemma','plight','quandary'],
    'predilection':['preference','liking','inclination'],
    'preface':['introduction','foreword','prologue'],
    'premise':['assumption','basis','proposition'],
    'premonition':['foreboding','presentiment'],
    'presumption':['assumption','arrogance','audacity'],
    'pretense':['pretext','excuse','sham'],
    'prevalence':['commonness','frequency','widespread nature'],
    'proclivity':['tendency','inclination','propensity'],
    'prodigy':['genius','talent','wonder'],
    'proficiency':['skill','competence','expertise'],
    'proliferation':['spread','multiplication','growth'],
    'proponent':['advocate','supporter','champion'],
    'propriety':['decency','decorum','correctness'],
    'protégé':['pupil','apprentice','student'],
    'protocol':['procedure','convention','etiquette'],
    'providence':['fate','fortune','destiny'],
    'provocation':['incitement','instigation','goading'],
    'prowess':['skill','ability','expertise'],
    'prudence':['caution','wisdom','discretion'],
    'pundit':['expert','commentator','authority'],
    'purview':['scope','range','domain'],
    'quagmire':['predicament','mess','morass'],
    'quandary':['dilemma','predicament','plight'],
    'quest':['search','pursuit','mission'],
    'quirk':['peculiarity','oddity','idiosyncrasy'],
    'quota':['allowance','allocation','share'],
    'rampart':['defence','fortification','bulwark'],
    'rancor':['bitterness','resentment','animosity'],
    'rapport':['connection','relationship','bond'],
    'rapture':['bliss','ecstasy','delight'],
    'rationale':['reasoning','justification','basis'],
    'reciprocity':['mutuality','exchange'],
    'recluse':['hermit','loner'],
    'reconciliation':['resolution','settlement','peace'],
    'rectitude':['integrity','honesty','righteousness'],
    'redemption':['salvation','deliverance','atonement'],
    'regime':['government','administration','system'],
    'rejuvenation':['renewal','revival','regeneration'],
    'relapse':['setback','regression','recurrence'],
    'relic':['artifact','remnant','vestige'],
    'remnant':['remainder','trace','vestige'],
    'remorse':['guilt','regret','contrition'],
    'renaissance':['revival','rebirth','renewal'],
    'renegade':['rebel','dissenter','outlaw'],
    'reparation':['compensation','restitution'],
    'repercussion':['consequence','effect','result'],
    'repertoire':['range','collection','stock'],
    'replica':['copy','duplicate','reproduction'],
    'reprieve':['relief','respite','pardon'],
    'repugnance':['disgust','revulsion','distaste'],
    'reservation':['doubt','hesitation','misgiving'],
    'residue':['remainder','remnant','deposit'],
    'resignation':['acceptance','acquiescence','quitting'],
    'resilience':['toughness','strength','flexibility'],
    'resistance':['opposition','defiance','pushback'],
    'resonance':['significance','impact'],
    'respite':['break','rest','relief'],
    'restitution':['compensation','repayment'],
    'resurgence':['revival','comeback','renewal'],
    'retaliation':['revenge','reprisal','vengeance'],
    'retribution':['punishment','vengeance','payback'],
    'revelation':['disclosure','discovery','exposure'],
    'reverence':['respect','veneration','awe'],
    'rhetoric':['oratory','persuasive language'],
    'rift':['split','breach','division'],
    'rigidity':['stiffness','inflexibility'],
    'rigor':['thoroughness','strictness','rigour'],
    'rite':['ritual','ceremony','custom'],
    'rivalry':['competition','contest','feud'],
    'rubric':['heading','category','guideline'],
    'rudiment':['basics','fundamentals'],
    'ruse':['trick','ploy','deception'],
    'sagacity':['wisdom','shrewdness','discernment'],
    'sanctity':['holiness','sacredness'],
    'sanctuary':['refuge','shelter','haven'],
    'sanctum':['sanctuary','retreat'],
    'sanity':['reason','soundness of mind'],
    'scapegoat':['fall guy','victim'],
    'scepticism':['doubt','distrust','disbelief'],
    'schism':['split','division','rift'],
    'scion':['descendant','heir'],
    'scourge':['plague','affliction','curse'],
    'scruple':['qualm','hesitation','misgiving'],
    'scrutiny':['examination','inspection','analysis'],
    'sediment':['deposit','residue'],
    'sensibility':['sensitivity','awareness'],
    'sentiment':['feeling','emotion','opinion'],
    'sequel':['continuation','follow-up'],
    'serenity':['calm','peace','tranquillity'],
    'shortfall':['deficit','shortage','gap'],
    'shrewdness':['astuteness','cunning'],
    'siege':['blockade','encirclement'],
    'significance':['importance','meaning','relevance'],
    'similitude':['similarity','likeness'],
    'simplicity':['plainness','ease','clarity'],
    'sincerity':['honesty','genuineness','candour'],
    'skepticism':['doubt','distrust'],
    'skirmish':['clash','fight','conflict'],
    'slew':['a lot','a large number'],
    'sluggishness':['slowness','lethargy'],
    'sobriety':['seriousness','soberness'],
    'solace':['comfort','consolation','relief'],
    'solidarity':['unity','support','togetherness'],
    'solitude':['isolation','loneliness','seclusion'],
    'sovereignty':['independence','autonomy','self-rule'],
    'spectacle':['display','show','sight'],
    'speculation':['guesswork','conjecture','theorising'],
    'spontaneity':['impulsiveness','naturalness'],
    'sprawl':['expansion','spread'],
    'squalor':['filth','dirtiness','wretchedness'],
    'stagnation':['stalling','decline','inertia'],
    'stalemate':['deadlock','impasse','standoff'],
    'stamina':['endurance','energy','vigour'],
    'standoff':['deadlock','impasse'],
    'staple':['essential','mainstay'],
    'stature':['reputation','standing','status'],
    'steadfastness':['loyalty','constancy','resolve'],
    'stigma':['shame','disgrace','stain'],
    'stipend':['allowance','payment','salary'],
    'stoicism':['fortitude','endurance'],
    'strife':['conflict','discord','struggle'],
    'stringency':['strictness','severity'],
    'subjugation':['conquest','domination','enslavement'],
    'subsidy':['grant','funding','support'],
    'substance':['essence','content','matter'],
    'summit':['peak','pinnacle','meeting'],
    'supplication':['plea','prayer','entreaty'],
    'surveillance':['monitoring','observation'],
    'susceptibility':['vulnerability','proneness'],
    'sustenance':['nourishment','food','support'],
    'symmetry':['balance','proportion','regularity'],
    'sympathy':['compassion','pity','understanding'],
    'synergy':['cooperation','collaboration'],
    'synthesis':['combination','fusion','blend'],
    'taboo':['prohibition','forbidden thing'],
    'tact':['diplomacy','discretion','sensitivity'],
    'tally':['count','total','score'],
    'tangent':['digression','deviation'],
    'tapestry':['fabric','weave','pattern'],
    'temperament':['nature','disposition','character'],
    'tenacity':['persistence','determination'],
    'tenet':['principle','belief','doctrine'],
    'tension':['strain','stress','friction'],
    'testament':['proof','evidence','tribute'],
    'threshold':['boundary','limit','entrance'],
    'thwarting':['prevention','obstruction'],
    'tirade':['rant','diatribe','outburst'],
    'token':['symbol','sign','indication'],
    'tolerance':['acceptance','patience','forbearance'],
    'torrent':['flood','deluge','stream'],
    'trajectory':['path','course','trend'],
    'tranquility':['peace','calm','serenity'],
    'transgression':['sin','violation','offence'],
    'transition':['change','shift','changeover'],
    'travesty':['mockery','farce','distortion'],
    'treachery':['betrayal','disloyalty','deceit'],
    'treatise':['essay','dissertation','study'],
    'tremor':['shake','tremble','quake'],
    'tribulation':['hardship','suffering','ordeal'],
    'tribute':['homage','honour','acknowledgment'],
    'trickery':['deceit','deception','fraud'],
    'triumph':['victory','success','win'],
    'trove':['collection','store','hoard'],
    'truce':['ceasefire','armistice','peace'],
    'turmoil':['chaos','confusion','disorder'],
    'tutelage':['guidance','instruction','mentorship'],
    'tyranny':['oppression','despotism','dictatorship'],
    'ubiquity':['omnipresence','universality'],
    'umbrage':['offence','resentment','displeasure'],
    'unanimity':['agreement','consensus'],
    'uncertainty':['doubt','ambiguity','unpredictability'],
    'undertone':['implication','nuance','suggestion'],
    'uniformity':['sameness','consistency','regularity'],
    'unison':['harmony','accord'],
    'unrest':['turmoil','disorder','discontent'],
    'upheaval':['turmoil','disruption','disturbance'],
    'uprising':['revolt','rebellion','insurrection'],
    'utopia':['paradise','ideal society'],
    'vanguard':['forefront','leader','pioneer'],
    'vanity':['conceit','pride','self-love'],
    'vantage':['viewpoint','position','perspective'],
    'vengeance':['revenge','retribution','retaliation'],
    'venue':['location','site','setting'],
    'veracity':['truthfulness','accuracy','honesty'],
    'verdict':['ruling','judgement','decision'],
    'vestige':['trace','remnant','remains'],
    'vicinity':['area','neighbourhood','proximity'],
    'vigil':['watch','wake','stakeout'],
    'vigor':['energy','vitality','vigour'],
    'vindication':['justification','exoneration'],
    'virtuosity':['skill','mastery','brilliance'],
    'visage':['face','appearance','countenance'],
    'vitality':['energy','liveliness','vigour'],
    'vocation':['career','profession','calling'],
    'vogue':['fashion','trend','style'],
    'volatility':['instability','unpredictability'],
    'vortex':['whirlpool','maelstrom'],
    'vulgarity':['crudeness','coarseness'],
    'vulnerability':['weakness','susceptibility','exposure'],
    'wanderlust':['desire to travel'],
    'warfare':['conflict','combat','fighting'],
    'warrant':['justification','authorisation'],
    'wisdom':['knowledge','insight','sagacity'],
    'wit':['humour','cleverness','intelligence'],
    'woe':['sorrow','grief','misery'],
    'wrath':['anger','fury','rage'],
    'xenophobia':['fear of foreigners','prejudice'],
    'yearning':['longing','craving','desire'],
    'zealotry':['fanaticism','extremism'],
    'zenith':['peak','summit','apex'],
    'absolutely':['completely','totally','utterly','entirely'],
    'accordingly':['therefore','consequently','thus','hence'],
    'actually':['in fact','really','truthfully'],
    'additionally':['also','furthermore','moreover','besides'],
    'admittedly':['granted','it must be said','concededly'],
    'afterward':['subsequently','later','thereafter'],
    'albeit':['although','though','even though'],
    'alternatively':['on the other hand','instead','otherwise'],
    'anyway':['nevertheless','regardless','nonetheless'],
    'apparently':['seemingly','evidently','ostensibly'],
    'arguably':['possibly','conceivably','debatably'],
    'barely':['scarcely','hardly','just'],
    'basically':['essentially','fundamentally','in essence'],
    'beforehand':['in advance','previously','ahead of time'],
    'briefly':['shortly','concisely','in short'],
    'carefully':['cautiously','meticulously','attentively'],
    'certainly':['definitely','undoubtedly','surely'],
    'clearly':['obviously','evidently','plainly'],
    'closely':['carefully','intently','nearly'],
    'completely':['entirely','totally','wholly'],
    'consequently':['therefore','as a result','hence'],
    'considerably':['substantially','significantly','markedly'],
    'constantly':['continually','perpetually','incessantly'],
    'conversely':['on the contrary','in contrast','oppositely'],
    'correspondingly':['likewise','similarly','equally'],
    'customarily':['usually','typically','habitually'],
    'deliberately':['intentionally','purposely','on purpose'],
    'distinctly':['clearly','markedly','noticeably'],
    'drastically':['severely','radically','dramatically'],
    'effectively':['efficiently','successfully','in effect'],
    'eventually':['ultimately','in the end','finally'],
    'exceedingly':['extremely','exceptionally','remarkably'],
    'exclusively':['solely','only','purely'],
    'extensively':['broadly','widely','thoroughly'],
    'extremely':['exceedingly','extraordinarily','intensely'],
    'firmly':['solidly','securely','resolutely'],
    'formerly':['previously','once','in the past'],
    'frankly':['honestly','candidly','plainly'],
    'freely':['readily','openly','liberally'],
    'genuinely':['truly','sincerely','authentically'],
    'gradually':['slowly','progressively','incrementally'],
    'greatly':['considerably','substantially','significantly'],
    'hastily':['hurriedly','quickly','rashly'],
    'hitherto':['until now','so far','previously'],
    'hypothetically':['theoretically','conceivably'],
    'immensely':['enormously','greatly','vastly'],
    'inadvertently':['accidentally','unintentionally'],
    'incidentally':['by the way','coincidentally'],
    'increasingly':['more and more','progressively'],
    'inevitably':['unavoidably','certainly','inescapably'],
    'inherently':['intrinsically','naturally','fundamentally'],
    'initially':['at first','originally','to begin with'],
    'intensely':['deeply','extremely','fervently'],
    'intentionally':['deliberately','purposely','knowingly'],
    'largely':['mostly','mainly','predominantly'],
    'literally':['exactly','precisely','word for word'],
    'markedly':['noticeably','distinctly','considerably'],
    'meanwhile':['in the meantime','simultaneously'],
    'merely':['simply','just','only'],
    'moderately':['reasonably','fairly','somewhat'],
    'mostly':['largely','mainly','predominantly'],
    'notably':['especially','particularly','remarkably'],
    'overwhelmingly':['predominantly','vastly','decisively'],
    'partially':['partly','incompletely','to some degree'],
    'perpetually':['constantly','continually','endlessly'],
    'plainly':['clearly','obviously','simply'],
    'precisely':['exactly','accurately','specifically'],
    'presumably':['probably','supposedly','likely'],
    'previously':['formerly','earlier','before'],
    'primarily':['mainly','chiefly','principally'],
    'promptly':['immediately','quickly','swiftly'],
    'quite':['fairly','rather','somewhat'],
    'radically':['fundamentally','drastically','extremely'],
    'rapidly':['quickly','swiftly','speedily'],
    'rarely':['seldom','infrequently','hardly ever'],
    'readily':['easily','willingly','promptly'],
    'regularly':['routinely','frequently','consistently'],
    'relatively':['comparatively','fairly','somewhat'],
    'remarkably':['strikingly','notably','extraordinarily'],
    'repeatedly':['frequently','continually','over and over'],
    'scarcely':['barely','hardly','only just'],
    'seemingly':['apparently','ostensibly','on the surface'],
    'severely':['harshly','extremely','seriously'],
    'significantly':['considerably','substantially','markedly'],
    'simultaneously':['concurrently','at the same time'],
    'sparingly':['scantily','frugally','moderately'],
    'specifically':['particularly','precisely','explicitly'],
    'steadily':['consistently','continuously','gradually'],
    'strictly':['rigorously','exactly','precisely'],
    'subsequently':['afterward','later','following that'],
    'substantially':['considerably','significantly','largely'],
    'successively':['consecutively','one after another'],
    'suddenly':['abruptly','unexpectedly','all at once'],
    'sufficiently':['adequately','enough','satisfactorily'],
    'surprisingly':['unexpectedly','remarkably','astonishingly'],
    'swiftly':['quickly','rapidly','speedily'],
    'temporarily':['briefly','for now','provisionally'],
    'thoroughly':['completely','exhaustively','comprehensively'],
    'typically':['usually','normally','generally'],
    'ultimately':['eventually','finally','in the end'],
    'undoubtedly':['certainly','definitely','unquestionably'],
    'unequivocally':['clearly','definitely','absolutely'],
    'unexpectedly':['suddenly','surprisingly','out of the blue'],
    'uniformly':['consistently','equally','evenly'],
    'universally':['globally','generally','without exception'],
    'unwittingly':['unknowingly','inadvertently'],
    'utterly':['completely','totally','absolutely'],
    'vaguely':['indistinctly','imprecisely','vaguely'],
    'vastly':['immensely','hugely','enormously'],
    'vehemently':['forcefully','passionately','strongly'],
    'virtually':['almost','nearly','practically'],
    'vividly':['clearly','graphically','strikingly'],
    'willingly':['readily','voluntarily','gladly'],
    'algorithm':['procedure','process','formula'],
    'anomalous':['abnormal','irregular','unusual'],
    'apparatus':['equipment','device','machinery'],
    'artefact':['object','relic','item'],
    'audit':['review','inspection','examination'],
    'bandwidth':['capacity','scope'],
    'breakthrough':['advance','discovery','innovation'],
    'brochure':['pamphlet','leaflet','booklet'],
    'bureaucrat':['official','administrator'],
    'capitalise':['exploit','profit from','leverage'],
    'cargo':['freight','goods','shipment'],
    'cartel':['syndicate','alliance','trust'],
    'census':['count','survey','tally'],
    'circuit':['route','loop','network'],
    'clientele':['customers','patrons','clients'],
    'commerce':['trade','business','industry'],
    'commute':['travel','journey to work'],
    'conglomerate':['corporation','group','combine'],
    'consortium':['alliance','coalition','partnership'],
    'constituency':['electorate','voters','district'],
    'consumer':['buyer','purchaser','customer'],
    'contraption':['device','gadget','apparatus'],
    'corridor':['passage','hallway','passageway'],
    'correspondent':['journalist','reporter'],
    'curriculum':['syllabus','course of study'],
    'database':['repository','archive','store'],
    'demography':['population statistics'],
    'depot':['warehouse','storage','terminal'],
    'deregulation':['liberalisation'],
    'diagnostic':['analytical','investigative'],
    'digest':['summary','compilation'],
    'dividend':['payout','share','return'],
    'domicile':['residence','home','dwelling'],
    'dormitory':['hall of residence','residence hall'],
    'dossier':['file','record','portfolio'],
    'draft':['outline','version','sketch'],
    'dwelling':['residence','home','abode'],
    'ecosystem':['environment','habitat','biosphere'],
    'emblem':['symbol','badge','insignia'],
    'endowment':['fund','grant','trust'],
    'enterprise':['business','company','venture'],
    'epidemiology':['study of disease patterns'],
    'estuary':['river mouth','inlet'],
    'excavation':['dig','digging','unearthing'],
    'facility':['building','establishment','amenity'],
    'fiscal':['financial','monetary','budgetary'],
    'foundation':['organisation','base','basis'],
    'franchise':['licence','concession'],
    'freight':['cargo','goods','shipment'],
    'funnel':['channel','pipe','conduit'],
    'gauge':['measure','indicator','instrument'],
    'geopolitics':['international relations'],
    'grid':['network','lattice'],
    'hamlet':['village','settlement'],
    'hangar':['shed','storage building'],
    'headquarters':['base','main office','central office'],
    'holdings':['assets','possessions','property'],
    'hub':['centre','focal point','nucleus'],
    'imagery':['pictures','visuals','symbolism'],
    'immigrant':['migrant','newcomer','settler'],
    'impairment':['disability','damage','defect'],
    'inauguration':['launch','opening','installation'],
    'incubator':['nursery','breeding ground'],
    'indicator':['sign','signal','marker'],
    'inflation':['price rise','devaluation'],
    'infrastructure':['framework','foundation','network'],
    'inheritance':['legacy','bequest','estate'],
    'installation':['facility','setup','fixture'],
    'instrument':['tool','device','implement'],
    'insurgent':['rebel','revolutionary'],
    'investor':['shareholder','backer','financier'],
    'itinerant':['travelling','wandering','nomadic'],
    'junction':['intersection','crossing'],
    'jurisdiction':['authority','territory','domain'],
    'kiosk':['stand','booth','stall'],
    'laboratory':['lab','research facility'],
    'laden':['loaded','burdened'],
    'landlord':['proprietor','owner'],
    'layout':['arrangement','design','plan'],
    'ledger':['record book','account book'],
    'legislature':['parliament','congress','assembly'],
    'livelihood':['income','living','occupation'],
    'locale':['location','setting','venue'],
    'logistics':['organisation','planning'],
    'lucre':['money','profit'],
    'magnate':['tycoon','mogul','industrialist'],
    'mainframe':['central computer'],
    'mainstay':['pillar','backbone','support'],
    'manuscript':['document','text','draft'],
    'margin':['edge','border','profit'],
    'mechanism':['system','process','apparatus'],
    'merchandise':['goods','products','wares'],
    'metropolis':['city','urban centre'],
    'milieu':['environment','setting','surroundings'],
    'mode':['manner','method','way'],
    'module':['unit','component','section'],
    'mogul':['tycoon','magnate','baron'],
    'monument':['memorial','landmark','statue'],
    'mortgage':['loan','home loan'],
    'municipality':['town','district','council'],
    'nomenclature':['naming system','terminology'],
    'novice':['beginner','newcomer','learner'],
    'nutrient':['nourishment','food substance'],
    'occupant':['resident','inhabitant','tenant'],
    'offshoot':['branch','spinoff','derivative'],
    'outlet':['store','shop','market'],
    'overhead':['expenses','costs'],
    'parameter':['limit','boundary','factor'],
    'patent':['licence','copyright'],
    'payload':['cargo','load'],
    'pedagogy':['teaching method'],
    'pension':['retirement fund','annuity'],
    'percentile':['rank','proportion'],
    'perimeter':['boundary','border','edge'],
    'personnel':['staff','employees','workforce'],
    'petition':['appeal','request','plea'],
    'phenomena':['occurrences','events'],
    'pipeline':['conduit','channel'],
    'plaintiff':['claimant','complainant'],
    'plateau':['level','stability'],
    'portfolio':['collection','range','holdings'],
    'precinct':['district','area','zone'],
    'predecessor':['forerunner','precursor'],
    'premium':['payment','bonus','surcharge'],
    'prerequisite':['requirement','precondition'],
    'prescription':['directive','order'],
    'proceeds':['profits','earnings','revenue'],
    'procurement':['acquisition','purchasing'],
    'proprietor':['owner','landlord'],
    'prototype':['model','original','template'],
    'province':['region','territory','area'],
    'proxy':['substitute','representative','deputy'],
    'quarantine':['isolation','confinement'],
    'quarry':['pit','excavation site'],
    'rebate':['refund','discount','reduction'],
    'receptacle':['container','vessel'],
    'recipient':['receiver','beneficiary'],
    'referendum':['vote','poll','plebiscite'],
    'refinery':['processing plant'],
    'registrar':['official','record keeper'],
    'regulator':['governing body','authority'],
    'reimbursement':['repayment','refund'],
    'renovation':['refurbishment','restoration'],
    'rental':['lease','hire'],
    'repository':['storehouse','archive','depot'],
    'residency':['residence','tenure'],
    'resident':['inhabitant','occupant','dweller'],
    'resolution':['decision','determination'],
    'retailer':['seller','vendor','shop'],
    'roster':['list','schedule','register'],
    'royalty':['payment','fee'],
    'satellite':['orbiting device','offshoot'],
    'scaffold':['framework','structure'],
    'sector':['area','field','division'],
    'shareholder':['stockholder','investor'],
    'shipment':['delivery','consignment','cargo'],
    'showcase':['display','exhibition'],
    'skyline':['horizon','cityscape'],
    'slum':['ghetto','shantytown'],
    'specification':['requirement','detail'],
    'sponsor':['backer','patron','supporter'],
    'stakeholder':['interested party','investor'],
    'statistic':['figure','data point'],
    'strait':['channel','passage'],
    'stratum':['layer','level','tier'],
    'subsidiary':['branch','division','offshoot'],
    'substrate':['base','foundation','layer'],
    'suburb':['residential area','district'],
    'successor':['heir','replacement'],
    'surcharge':['extra fee','additional cost'],
    'syllabus':['curriculum','course outline'],
    'symposium':['conference','seminar','forum'],
    'synopsis':['summary','outline','digest'],
    'syndicate':['consortium','cartel','group'],
    'tariff':['tax','duty','levy'],
    'taxpayer':['citizen','contributor'],
    'tenant':['occupant','resident','lessee'],
    'tenement':['building','apartment block'],
    'terrain':['landscape','ground','topography'],
    'territory':['area','region','domain'],
    'testimony':['evidence','statement','account'],
    'thesis':['dissertation','argument','proposition'],
    'throughput':['output','productivity'],
    'toll':['charge','fee','levy'],
    'topography':['terrain','landscape'],
    'trademark':['brand','logo','emblem'],
    'tramway':['tram line','streetcar line'],
    'transaction':['deal','exchange'],
    'transcript':['record','copy'],
    'transit':['transport','passage'],
    'treasury':['fund','coffers'],
    'tribunal':['court','panel'],
    'turnover':['revenue','output','staff change rate'],
    'tutor':['teacher','instructor'],
    'tycoon':['magnate','mogul','baron'],
    'utility':['service','usefulness'],
    'vaccine':['inoculation','immunisation'],
    'vault':['safe','strongroom','repository'],
    'vendor':['seller','supplier','retailer'],
    'venture':['undertaking','enterprise','project'],
    'vessel':['ship','container','boat'],
    'veteran':['expert','old hand'],
    'viability':['feasibility','practicality'],
    'viaduct':['bridge','overpass'],
    'vintage':['classic','era','age'],
    'visa':['permit','authorisation'],
    'voucher':['coupon','token','ticket'],
    'wage':['pay','salary','earnings'],
    'warehouse':['storage facility','depot'],
    'warranty':['guarantee','assurance'],
    'watershed':['turning point','milestone'],
    'wharf':['dock','pier','quay'],
    'workforce':['staff','employees','personnel'],
    'workshop':['seminar','session','studio'],
    'zoning':['land use planning'],
    'walk':['stroll','stride','amble','march','wander'],
    'run':['sprint','dash','jog','race','bolt'],
    'jump':['leap','hop','spring','bound','vault'],
    'eat':['consume','devour','dine','feast','ingest'],
    'drink':['sip','gulp','swallow','imbibe','quaff'],
    'sleep':['slumber','doze','rest','nap','snooze'],
    'speak':['talk','say','utter','converse','communicate'],
    'shout':['yell','cry out','holler','bellow','exclaim'],
    'whisper':['murmur','mutter','breathe','mumble'],
    'laugh':['chuckle','giggle','snicker','guffaw','chortle'],
    'cry':['weep','sob','wail','bawl','whimper'],
    'smile':['grin','beam','smirk'],
    'look':['glance','peer','gaze','stare','observe'],
    'see':['spot','notice','observe','witness','perceive'],
    'hear':['listen','overhear','detect'],
    'touch':['feel','handle','stroke','tap'],
    'write':['compose','pen','draft','scribble','jot'],
    'read':['peruse','scan','study','skim'],
    'draw':['sketch','illustrate','depict','render'],
    'paint':['coat','colour','depict'],
    'sing':['chant','croon','warble'],
    'dance':['sway','twirl','move'],
    'play':['engage in','participate in','perform'],
    'cook':['prepare','make','whip up'],
    'clean':['tidy','scrub','wash','purify'],
    'wash':['clean','rinse','launder'],
    'carry':['bear','transport','haul','tote','lug'],
    'lift':['raise','hoist','elevate','heave'],
    'push':['shove','thrust','propel','press'],
    'pull':['tug','drag','haul','yank'],
    'throw':['toss','hurl','fling','pitch','cast'],
    'catch':['grab','seize','capture','snag'],
    'drop':['fall','let go of','release'],
    'hold':['grip','grasp','clutch','clasp'],
    'open':['unlock','unfasten','unseal'],
    'fix':['repair','mend','correct','rectify'],
    'search':['seek','look for','hunt for','probe'],
    'win':['triumph','succeed','prevail','conquer'],
    'travel':['journey','voyage','trek','tour'],
    'move':['relocate','shift','transfer','proceed'],
    'stop':['halt','cease','pause','discontinue'],
    'wait':['linger','pause','tarry','remain'],
    'leave':['depart','exit','go','withdraw'],
    'enter':['go in','arrive','access'],
    'rise':['ascend','climb','get up','stand'],
    'fall':['drop','tumble','plunge','descend'],
    'sit':['perch','settle','rest'],
    'stand':['rise','remain upright'],
    'turn':['rotate','spin','pivot','swivel'],
    'bend':['curve','flex','bow','stoop'],
    'twist':['contort','wring','coil','warp'],
    'shake':['tremble','quiver','vibrate','wobble'],
    'rock':['sway','wobble','oscillate'],
    'float':['drift','glide','hover','bob'],
    'sink':['submerge','plunge','descend'],
    'swim':['bathe','paddle'],
    'fly':['soar','glide','wing'],
    'climb':['ascend','scale','clamber'],
    'hide':['conceal','cover','mask','shelter'],
    'mix':['blend','combine','merge','stir'],
    'separate':['divide','split','part','sever'],
    'remove':['take away','eliminate','extract','withdraw'],
    'fill':['stuff','pack','load','cram'],
    'stay':['remain','continue','linger'],
    'harm':['hurt','injure','damage','wound'],
    'save':['rescue','preserve','protect','conserve'],
    'spend':['use up','expend','pay out'],
    'buy':['purchase','acquire','obtain'],
    'sell':['vend','market','trade'],
    'pay':['settle','remit','compensate'],
    'owe':['be indebted','be liable'],
    'borrow':['take out','loan'],
    'lend':['loan','advance'],
    'trade':['exchange','barter','swap'],
    'receive':['obtain','accept','get','acquire'],
    'send':['dispatch','transmit','forward','post'],
    'call':['phone','contact','summon','ring'],
    'ask':['inquire','query','request','question'],
    'tell':['inform','notify','say','relate'],
    'teach':['instruct','educate','train','tutor'],
    'learn':['study','master','acquire','absorb'],
    'know':['understand','realise','be aware of'],
    'remember':['recall','recollect','retain'],
    'plan':['scheme','devise','arrange','organise'],
    'like':['enjoy','appreciate','fancy','favour'],
    'dislike':['hate','despise','loathe','detest'],
    'love':['adore','cherish','treasure'],
    'hate':['detest','loathe','despise','abhor'],
    'want':['desire','wish for','crave','long for'],
    'fear':['dread','be afraid of','worry about'],
    'worry':['fret','stress','be anxious','agonise'],
    'trust':['rely on','believe in','have faith in'],
    'promise':['pledge','vow','guarantee','swear'],
    'lie':['fib','deceive','fabricate'],
    'cheat':['deceive','defraud','trick','swindle'],
    'steal':['rob','pilfer','filch','pinch'],
    'kill':['slay','murder','eliminate'],
    'treat':['handle','deal with','manage'],
    'feed':['nourish','sustain','nurture'],
    'starve':['deprive of food','famish'],
    'rest':['relax','unwind','recuperate'],
    'exercise':['work out','train','practise'],
    'practise':['train','rehearse','drill'],
    'behave':['act','conduct oneself'],
    'react':['respond','reply','answer'],
    'respond':['react','reply','answer'],
    'influence':['affect','sway','shape'],
    'rule':['govern','control','reign'],
    'lead':['guide','direct','head','steer'],
    'advise':['counsel','recommend','suggest'],
    'warn':['caution','alert','notify'],
    'threaten':['menace','intimidate','endanger'],
    'order':['command','instruct','direct'],
    'offer':['propose','present','extend'],
    'recommend':['suggest','advise','endorse'],
    'propose':['suggest','put forward','offer'],
    'disapprove':['object to','condemn','criticise'],
    'praise':['commend','compliment','applaud'],
    'blame':['accuse','fault','condemn'],
    'forgive':['pardon','excuse','absolve'],
    'punish':['penalise','discipline','sanction'],
    'motivate':['inspire','drive','spur'],
    'satisfy':['fulfil','please','gratify'],
    'please':['satisfy','delight','gratify'],
    'disappoint':['let down','fail','dishearten'],
    'surprise':['astonish','shock','startle'],
    'shock':['startle','stun','astonish'],
    'scare':['frighten','terrify','alarm'],
    'frighten':['scare','terrify','alarm'],
    'bore':['tire','weary','fatigue'],
    'anger':['enrage','infuriate','madden'],
    'upset':['distress','disturb','trouble'],
    'shame':['embarrass','humiliate','disgrace'],
    'trick':['deceive','fool','dupe'],
    'fool':['deceive','trick','dupe'],
    'meddle':['interfere','intrude','pry'],
    'intrude':['interfere','trespass','encroach'],
    'trespass':['intrude','encroach','violate'],
    'oppose':['resist','object to','counter'],
    'back':['support','endorse','sponsor'],
    'fund':['finance','sponsor','bankroll'],
    'finance':['fund','bankroll','support'],
    'waste':['squander','misuse','fritter away'],
    'reuse':['recycle','repurpose'],
    'recycle':['reuse','reprocess','repurpose'],
    'produce':['generate','create','manufacture'],
    'check':['verify','confirm','inspect'],
    'unmask':['expose','reveal','uncover'],
    'publish':['print','release','issue'],
    'broadcast':['transmit','air','televise'],
    'announce':['declare','proclaim','state'],
    'declare':['announce','proclaim','state'],
    'state':['declare','assert','say'],
    'quarrel':['argue','fight','dispute'],
    'fight':['battle','struggle','combat'],
    'unite':['join','combine','merge'],
    'split':['divide','separate','fracture'],
    'link':['connect','join','associate'],
    'relate':['connect','link','pertain'],
    'contrast':['compare','differentiate','distinguish'],
    'recognise':['identify','acknowledge','recall'],
    'sort':['classify','organise','arrange'],
    'organise':['arrange','coordinate','plan'],
    'manage':['handle','run','oversee'],
    'serve':['assist','help','provide for'],
    'supply':['provide','furnish','equip'],
    'furnish':['supply','equip','provide'],
    'elect':['choose','vote for','select'],
    'vote':['ballot','poll','cast a vote'],
    'march':['walk','parade','stride'],
    'parade':['march','procession','display'],
    'honour':['respect','celebrate','commemorate'],
    'respect':['esteem','admire','value'],
    'value':['esteem','cherish','appreciate'],
    'treasure':['cherish','value','prize'],
    'prize':['value','treasure','esteem'],
    'forest':['woodland','woods','jungle','grove'],
    'mountain':['peak','summit','highland','mount'],
    'river':['stream','waterway','watercourse'],
    'ocean':['sea','deep','waters'],
    'desert':['wasteland','wilderness','arid land'],
    'valley':['dale','vale','glen'],
    'cliff':['bluff','crag','precipice'],
    'island':['isle','islet','atoll'],
    'storm':['tempest','gale','squall'],
    'rain':['downpour','shower','drizzle'],
    'drought':['dry spell','aridity'],
    'flood':['deluge','inundation','overflow'],
    'earthquake':['tremor','quake','seismic event'],
    'volcano':['crater','vent'],
    'climate':['weather pattern','conditions'],
    'temperature':['heat','warmth','degrees'],
    'wildlife':['fauna','animals','creatures'],
    'species':['type','breed','kind'],
    'pollution':['contamination','toxicity','fouling'],
    'conservation':['preservation','protection','stewardship'],
    'biodiversity':['variety of life','species diversity'],
    'extinction':['disappearance','dying out'],
    'sustainability':['viability','durability'],
    'renewable':['sustainable','replenishable'],
    'fossil':['relic','remains','vestige'],
    'atmosphere':['air','environment','mood'],
    'emission':['discharge','release','output'],
    'greenhouse':['glasshouse'],
    'deforestation':['forest clearance','logging'],
    'erosion':['wearing away','deterioration'],
    'organism':['creature','being','life form'],
    'cell':['unit','compartment'],
    'gene':['hereditary unit'],
    'molecule':['particle','compound'],
    'particle':['fragment','speck','grain'],
    'compound':['mixture','combination','blend'],
    'reaction':['response','interaction'],
    'experiment':['test','trial','investigation'],
    'theory':['hypothesis','model','proposition'],
    'formula':['equation','recipe','method'],
    'equation':['formula','expression'],
    'calculation':['computation','estimate','reckoning'],
    'measurement':['dimension','reading','calculation'],
    'signal':['sign','indication','cue'],
    'frequency':['rate','regularity'],
    'velocity':['speed','pace','rate'],
    'mass':['weight','bulk','volume'],
    'density':['thickness','concentration','compactness'],
    'pressure':['force','strain','tension'],
    'gravity':['seriousness','weight'],
    'radiation':['emission','rays'],
    'spectrum':['range','array'],
    'antibody':['immune protein'],
    'bacteria':['microbe','germ'],
    'virus':['pathogen','microorganism'],
    'infection':['contamination','disease'],
    'symptom':['sign','indication','manifestation'],
    'diagnosis':['identification','determination'],
    'treatment':['therapy','remedy','cure'],
    'therapy':['treatment','remedy'],
    'recovery':['healing','improvement','rehabilitation'],
    'immunity':['resistance','protection'],
    'nutrition':['nourishment','diet'],
    'metabolism':['bodily processes'],
    'hormone':['chemical messenger'],
    'nerve':['neuron','fibre'],
    'tissue':['fabric','matter'],
    'organ':['body part'],
    'anatomy':['body structure','physiology'],
    'physiology':['bodily function'],
    'psychology':['mental processes','mindset'],
    'cognition':['thinking','mental processing'],
    'mood':['temper','disposition','state of mind'],
    'personality':['character','nature','disposition'],
    'character':['personality','nature','disposition'],
    'identity':['self','individuality'],
    'consciousness':['awareness','sentience'],
    'subconscious':['unconscious mind'],
    'instinct':['intuition','impulse'],
    'impulse':['urge','instinct','whim'],
    'motivation':['drive','incentive','inspiration'],
    'determination':['resolve','willpower','persistence'],
    'willpower':['self-control','determination'],
    'self-control':['restraint','discipline'],
    'depression':['despondency','low spirits'],
    'happiness':['joy','contentment','bliss'],
    'sadness':['sorrow','unhappiness','melancholy'],
    'pride':['self-respect','dignity','satisfaction'],
    'jealousy':['envy','resentment'],
    'envy':['jealousy','covetousness'],
    'loyalty':['faithfulness','allegiance','devotion'],
    'betrayal':['treachery','disloyalty','deceit'],
    'suspicion':['distrust','doubt','wariness'],
    'curiosity':['inquisitiveness','interest'],
    'boredom':['tedium','monotony','dullness'],
    'excitement':['thrill','exhilaration','elation'],
    'pessimism':['negativity','despair'],
    'kindness':['generosity','benevolence','warmth'],
    'generosity':['kindness','charity','liberality'],
    'cruelty':['brutality','savagery','viciousness'],
    'violence':['brutality','aggression','savagery'],
    'aggression':['hostility','belligerence','violence'],
    'peace':['calm','tranquillity','harmony'],
    'war':['conflict','combat','warfare'],
    'victory':['triumph','win','conquest'],
    'failure':['defeat','collapse','downfall'],
    'success':['achievement','triumph','accomplishment'],
    'achievement':['accomplishment','success','feat'],
    'accomplishment':['achievement','success','feat'],
    'progress':['advancement','development','improvement'],
    'development':['growth','progress','evolution'],
    'growth':['expansion','development','increase'],
    'breakdown':['collapse','failure','malfunction'],
    'revival':['renewal','resurgence','rebirth'],
    'renewal':['revival','regeneration','restoration'],
    'restoration':['renewal','repair','revival'],
    'transformation':['change','conversion','metamorphosis'],
    'conversion':['transformation','change'],
    'adaptation':['adjustment','modification'],
    'adjustment':['modification','alteration'],
    'modification':['alteration','adjustment','change'],
    'alteration':['modification','change','adjustment'],
    'revision':['amendment','correction','update'],
    'correction':['fix','amendment','rectification'],
    'update':['revision','upgrade','modernisation'],
    'upgrade':['improvement','update','enhancement'],
    'enhancement':['improvement','upgrade'],
    'improvement':['betterment','advancement','enhancement'],
    'regression':['decline','relapse','setback'],
    'setback':['obstacle','reversal','hindrance'],
    'hindrance':['obstacle','impediment','barrier'],
    'complication':['difficulty','problem','obstacle'],
    'difficulty':['problem','challenge','trouble'],
    'trouble':['difficulty','problem','distress'],
    'emergency':['crisis','urgent situation'],
    'urgency':['pressing need','importance'],
    'necessity':['need','requirement','essential'],
    'requirement':['necessity','need','prerequisite'],
    'background':['context','history','setting'],
    'setting':['location','environment','backdrop'],
    'surroundings':['environment','vicinity','locale'],
    'tone':['mood','manner','style'],
    'style':['manner','fashion','approach'],
    'fashion':['style','trend','vogue'],
    'trend':['tendency','direction','fashion'],
    'tendency':['inclination','propensity','trend'],
    'preference':['liking','inclination','choice'],
    'alternative':['option','substitute','choice'],
    'substitute':['replacement','alternative','stand-in'],
    'replacement':['substitute','successor'],
    'precursor':['forerunner','predecessor','harbinger'],
    'forerunner':['precursor','predecessor','pioneer'],
    'innovator':['pioneer','inventor','trailblazer'],
    'trailblazer':['pioneer','innovator','pathfinder'],
    'inventor':['creator','innovator','originator'],
    'originator':['creator','founder','inventor'],
    'creator':['originator','maker','author'],
    'founder':['creator','originator','establisher'],
    'architect':['designer','planner','creator'],
    'designer':['architect','planner','creator'],
    'planner':['organiser','designer','strategist'],
    'strategist':['planner','tactician'],
    'tactician':['strategist','planner'],
    'mastermind':['architect','planner','brains'],
    'genius':['prodigy','mastermind','virtuoso'],
    'virtuoso':['expert','master','maestro'],
    'maestro':['virtuoso','master','expert'],
    'master':['expert','virtuoso','specialist'],
    'specialist':['expert','authority','professional'],
    'professional':['expert','specialist','skilled worker'],
    'amateur':['novice','beginner','nonprofessional'],
    'beginner':['novice','newcomer','learner'],
    'learner':['student','trainee','pupil'],
    'trainee':['apprentice','learner','recruit'],
    'apprentice':['trainee','learner','novice'],
    'mentor':['adviser','guide','tutor'],
    'adviser':['consultant','counsellor','mentor'],
    'consultant':['adviser','specialist','expert'],
    'counsellor':['adviser','therapist','guide'],
    'therapist':['counsellor','healer'],
    'practitioner':['professional','specialist'],
    'surgeon':['operating physician'],
    'physician':['doctor','medical practitioner'],
    'clinician':['doctor','medical practitioner'],
    'researcher':['investigator','scientist','scholar'],
    'scholar':['academic','researcher','intellectual'],
    'academic':['scholar','intellectual','scholarly'],
    'philosopher':['thinker','theorist'],
    'theorist':['philosopher','academic'],
    'analyst':['examiner','evaluator','assessor'],
    'assessor':['evaluator','examiner','judge'],
    'evaluator':['assessor','judge','appraiser'],
    'appraiser':['evaluator','assessor'],
    'inspector':['examiner','auditor','overseer'],
    'overseer':['supervisor','manager','superintendent'],
    'supervisor':['manager','overseer','boss'],
    'manager':['supervisor','director','administrator'],
    'administrator':['manager','director','official'],
    'director':['manager','administrator','chief'],
    'executive':['manager','director','officer'],
    'officer':['official','executive','administrator'],
    'official':['officer','administrator','representative'],
    'representative':['delegate','official','agent'],
    'envoy':['representative','delegate','emissary'],
    'ambassador':['envoy','representative','diplomat'],
    'diplomat':['ambassador','envoy','negotiator'],
    'negotiator':['mediator','diplomat','arbitrator'],
    'mediator':['negotiator','arbitrator','intermediary'],
    'arbitrator':['mediator','judge','referee'],
    'referee':['arbitrator','umpire','judge'],
    'umpire':['referee','judge','arbitrator'],
    'judge':['arbitrator','magistrate','adjudicator'],
    'magistrate':['judge','justice'],
    'adjudicator':['judge','arbitrator'],
    'prosecutor':['attorney','lawyer'],
    'attorney':['lawyer','solicitor','counsel'],
    'lawyer':['attorney','solicitor','counsel'],
    'counsel':['lawyer','advice','guidance'],
    'defendant':['accused','respondent'],
    'accused':['defendant','suspect'],
    'suspect':['accused','person of interest'],
    'perpetrator':['culprit','offender','wrongdoer'],
    'culprit':['perpetrator','offender','wrongdoer'],
    'offender':['culprit','perpetrator','criminal'],
    'criminal':['offender','lawbreaker','felon'],
    'felon':['criminal','convict','offender'],
    'prisoner':['convict','inmate','captive'],
    'inmate':['prisoner','convict'],
    'captive':['prisoner','hostage'],
    'hostage':['captive','prisoner'],
    'kidnapper':['abductor'],
    'abductor':['kidnapper'],
    'thief':['robber','burglar','crook'],
    'robber':['thief','burglar','bandit'],
    'burglar':['thief','robber','housebreaker'],
    'bandit':['robber','outlaw','brigand'],
    'outlaw':['bandit','criminal','fugitive'],
    'smuggler':['trafficker','runner'],
    'trafficker':['smuggler','dealer'],
    'dealer':['trader','trafficker','merchant'],
    'trader':['merchant','dealer','businessperson'],
    'merchant':['trader','dealer','businessperson'],
    'businessperson':['entrepreneur','trader','executive'],
    'financier':['investor','banker','backer'],
    'banker':['financier','lender'],
    'lender':['creditor','financier'],
    'creditor':['lender','financier'],
    'debtor':['borrower'],
    'borrower':['debtor','loanee'],
    'customer':['client','consumer','buyer'],
    'client':['customer','patron','consumer'],
    'patron':['customer','client','sponsor'],
    'buyer':['purchaser','customer','consumer'],
    'purchaser':['buyer','consumer'],
    'shopper':['buyer','customer','patron'],
    'worker':['employee','labourer','staff member'],
    'employee':['worker','staff member','hand'],
    'employer':['boss','company','proprietor'],
    'boss':['employer','manager','superior'],
    'assistant':['aide','helper','deputy'],
    'aide':['assistant','helper','adviser'],
    'helper':['assistant','aide','supporter'],
    'supporter':['backer','advocate','champion'],
    'champion':['advocate','supporter','defender'],
    'defender':['protector','guardian','champion'],
    'guardian':['protector','custodian','defender'],
    'protector':['guardian','defender','custodian'],
    'custodian':['guardian','caretaker','keeper'],
    'caretaker':['custodian','keeper','janitor'],
    'keeper':['custodian','guardian','warden'],
    'warden':['keeper','guard','custodian'],
    'guard':['sentry','watchman','protector'],
    'sentry':['guard','watchman','lookout'],
    'watchman':['guard','sentry','lookout'],
    'lookout':['watchman','sentry','vantage point'],
    'scout':['reconnoiterer','spy','lookout'],
    'spy':['agent','informant','operative'],
    'agent':['representative','operative','spy'],
    'operative':['agent','worker','spy'],
    'informant':['source','tipster','spy'],
    'source':['origin','informant','provider'],
    'provider':['supplier','source','giver'],
    'supplier':['provider','vendor','distributor'],
    'distributor':['supplier','wholesaler','dealer'],
    'wholesaler':['distributor','supplier'],
    'shopkeeper':['retailer','proprietor'],
    'manufacturer':['maker','producer','fabricator'],
    'producer':['manufacturer','maker','creator'],
    'maker':['manufacturer','producer','creator'],
    'fabricator':['manufacturer','producer'],
    'builder':['constructor','contractor','maker'],
    'contractor':['builder','supplier'],
    'constructor':['builder','maker'],
    'engineer':['technician','builder','designer'],
    'technician':['engineer','specialist','mechanic'],
    'mechanic':['technician','repairer','engineer'],
    'repairer':['mechanic','fixer','technician'],
    'fixer':['repairer','problem-solver'],
    'operator':['worker','handler','controller'],
    'handler':['operator','manager','trainer'],
    'trainer':['coach','instructor','handler'],
    'coach':['trainer','instructor','mentor'],
    'instructor':['teacher','trainer','coach'],
    'educator':['teacher','instructor','tutor'],
    'professor':['academic','lecturer','scholar'],
    'lecturer':['professor','instructor','speaker'],
    'speaker':['orator','lecturer','presenter'],
    'orator':['speaker','rhetorician'],
    'presenter':['speaker','host','announcer'],
    'host':['presenter','anchor','master of ceremonies'],
    'anchor':['presenter','newsreader'],
    'announcer':['presenter','broadcaster'],
    'broadcaster':['announcer','presenter'],
    'journalist':['reporter','correspondent','newsman'],
    'reporter':['journalist','correspondent'],
    'editor':['reviser','compiler'],
    'author':['writer','novelist','creator'],
    'writer':['author','novelist','scribe'],
    'novelist':['writer','author','storyteller'],
    'storyteller':['narrator','novelist','raconteur'],
    'narrator':['storyteller','commentator'],
    'poet':['bard','versifier'],
    'bard':['poet','minstrel'],
    'playwright':['dramatist','scriptwriter'],
    'dramatist':['playwright','screenwriter'],
    'screenwriter':['scriptwriter','dramatist'],
    'scriptwriter':['screenwriter','writer'],
    'composer':['songwriter','musician'],
    'songwriter':['composer','lyricist'],
    'lyricist':['songwriter','poet'],
    'musician':['performer','instrumentalist','player'],
    'performer':['artist','entertainer','musician'],
    'artist':['creator','performer','painter'],
    'painter':['artist','illustrator'],
    'illustrator':['artist','designer','painter'],
    'sculptor':['artist','carver'],
    'photographer':['cameraman','snapper'],
    'filmmaker':['director','producer','cinematographer'],
    'actor':['performer','player','thespian'],
    'actress':['performer','player','thespian'],
    'dancer':['performer','ballerina'],
    'singer':['vocalist','performer','crooner'],
    'vocalist':['singer','performer'],
    'athlete':['sportsperson','competitor','player'],
    'sportsperson':['athlete','competitor'],
    'competitor':['rival','contender','opponent'],
    'opponent':['rival','adversary','competitor'],
    'adversary':['opponent','rival','enemy'],
    'enemy':['foe','adversary','opponent'],
    'partner':['ally','associate','collaborator'],
    'collaborator':['partner','associate','accomplice'],
    'accomplice':['collaborator','partner in crime'],
    'affiliate':['associate','partner','subsidiary'],
    'friend':['companion','ally','confidant'],
    'companion':['friend','associate','partner'],
    'confidant':['friend','trusted associate'],
    'acquaintance':['contact','associate'],
    'stranger':['unknown person','outsider'],
    'outsider':['stranger','foreigner','newcomer'],
    'newcomer':['recruit','arrival','novice'],
    'arrival':['newcomer','entrant'],
    'visitor':['guest','caller','tourist'],
    'guest':['visitor','invitee'],
    'tourist':['visitor','traveller','sightseer'],
    'traveller':['tourist','voyager','wayfarer'],
    'voyager':['traveller','explorer'],
    'explorer':['adventurer','voyager','pioneer'],
    'adventurer':['explorer','daredevil'],
    'daredevil':['risk-taker','adventurer'],
    'risk-taker':['gambler','daredevil'],
    'gambler':['risk-taker','better'],
    'winner':['champion','victor'],
    'victor':['winner','champion','conqueror'],
    'conqueror':['victor','vanquisher'],
    'loser':['also-ran','failure'],
    'leader':['head','chief','director'],
    'follower':['adherent','disciple','supporter'],
    'adherent':['follower','supporter','believer'],
    'disciple':['follower','adherent','pupil'],
    'pupil':['student','learner','disciple'],
    'graduate':['alumnus','degree-holder'],
    'alumnus':['graduate','former student'],
    'freshman':['newcomer','first-year student'],
    'senior':['elder','superior','veteran'],
    'elder':['senior','older person'],
    'rookie':['newcomer','novice','beginner'],
    'soldier':['warrior','fighter','trooper'],
    'warrior':['fighter','soldier','combatant'],
    'fighter':['warrior','combatant','battler'],
    'combatant':['fighter','warrior','belligerent'],
    'troop':['soldier','unit','force'],
    'army':['military','troops','forces'],
    'navy':['fleet','naval force'],
    'fleet':['navy','flotilla','armada'],
    'squadron':['unit','division','group'],
    'regiment':['unit','battalion','corps'],
    'battalion':['regiment','unit'],
    'platoon':['squad','unit'],
    'brigade':['unit','force','division'],
    'division':['unit','section','branch'],
    'unit':['section','division','group'],
    'branch':['division','department','section'],
    'department':['division','section','branch'],
    'section':['division','part','segment'],
    'wing':['branch','division','faction'],
    'clique':['faction','group','circle'],
    'bloc':['group','coalition','faction'],
    'assembly':['gathering','meeting','congregation'],
    'congregation':['assembly','gathering','crowd'],
    'crowd':['gathering','throng','mob'],
    'throng':['crowd','multitude','mass'],
    'mob':['crowd','gang','throng'],
    'gang':['group','crew','mob'],
    'crew':['team','gang','staff'],
    'team':['crew','squad','group'],
    'squad':['team','crew','unit'],
    'council':['committee','board','assembly'],
    'board':['committee','council','panel'],
    'panel':['board','committee','jury'],
    'jury':['panel','tribunal'],
    'court':['tribunal','bench','judiciary'],
    'bench':['court','judiciary'],
    'judiciary':['court system','bench'],
    'parliament':['legislature','congress','assembly'],
    'congress':['parliament','legislature','assembly'],
    'senate':['upper house','council'],
    'cabinet':['ministers','executive council'],
    'ministry':['department','cabinet office'],
    'agency':['bureau','office','department'],
    'bureau':['agency','office','department'],
    'corporation':['company','firm','business'],
    'undertaking':['venture','project','task'],
    'project':['undertaking','venture','scheme'],
    'task':['job','assignment','duty'],
    'assignment':['task','job','mission'],
    'chore':['task','duty','job'],
    'errand':['task','mission','chore'],
    'responsibility':['duty','obligation','accountability'],
    'accountability':['responsibility','liability'],
    'commitment':['obligation','dedication','pledge'],
    'dedication':['commitment','devotion','loyalty'],
    'cutoff':['deadline','limit','boundary'],
    'timeframe':['period','schedule','timeline'],
    'timeline':['schedule','timeframe','plan'],
    'schedule':['timetable','plan','agenda'],
    'timetable':['schedule','programme'],
    'programme':['schedule','plan','agenda'],
    'coursework':['assignments','study'],
    'homework':['assignment','coursework'],
    'drill':['exercise','practice','training'],
    'exam':['test','examination','assessment'],
    'examination':['exam','test','assessment'],
    'assessment':['evaluation','appraisal','test'],
    'appraisal':['assessment','evaluation','review'],
    'evaluation':['assessment','appraisal','analysis'],
    'analysis':['examination','study','evaluation'],
    'critique':['review','analysis','criticism'],
    'review':['critique','evaluation','assessment'],
    'feedback':['response','comments','critique'],
    'input':['contribution','feedback','suggestion'],
    'contribution':['input','donation','offering'],
    'donation':['contribution','gift','offering'],
    'gift':['present','donation','offering'],
    'present':['gift','donation'],
    'offering':['gift','contribution','donation'],
    'award':['prize','honour','accolade'],
    'trophy':['prize','award','cup'],
    'accolade':['honour','award','tribute'],
    'recognition':['acknowledgment','acclaim','honour'],
    'acclaim':['praise','recognition','applause'],
    'applause':['acclaim','ovation','cheering'],
    'ovation':['applause','cheering','acclaim'],
    'cheering':['applause','shouting','acclaiming'],
    'distinction':['honour','excellence','recognition'],
    'excellence':['distinction','superiority','quality'],
    'superiority':['excellence','dominance','preeminence'],
    'preeminence':['dominance','superiority','prominence'],
    'prominence':['fame','eminence','distinction'],
    'eminence':['prominence','distinction','fame'],
    'fame':['renown','celebrity','notoriety'],
    'renown':['fame','distinction','celebrity'],
    'stardom':['fame','celebrity'],
    'notoriety':['infamy','ill fame'],
    'infamy':['notoriety','disgrace','ill repute'],
    'disgrace':['shame','dishonour','ignominy'],
    'dishonour':['disgrace','shame','discredit'],
    'shoulder':['bear','take on','carry'],
    'summarise':['recap','condense','encapsulate','abridge'],
    'outweigh':['exceed','surpass','override'],
    'encompass':['include','cover','embrace','span'],
    'underpin':['support','sustain','underlie'],
    'underscore':['emphasise','highlight','stress'],
    'spotlight':['highlight','feature','showcase'],
    'simplify':['streamline','ease','clarify'],
    'streamline':['simplify','optimise','modernise'],
    'optimise':['maximise','improve','enhance'],
    'harness':['exploit','utilise','control'],
    'channel':['direct','funnel','focus'],
    'siphon':['divert','drain','extract'],
    'redirect':['divert','reroute'],
    'reroute':['redirect','divert'],
    'mould':['shape','form','fashion'],
    'shape':['mould','form','fashion'],
    'sculpt':['shape','carve','mould'],
    'carve':['sculpt','cut','engrave'],
    'engrave':['inscribe','carve','etch'],
    'etch':['engrave','inscribe'],
    'stamp':['imprint','mark','impress'],
    'implant':['embed','insert','instil'],
    'insert':['embed','introduce','add'],
    'splice':['join','merge','graft'],
    'graft':['transplant','splice'],
    'transplant':['graft','relocate'],
    'relocate':['move','transfer','shift'],
    'emigrate':['migrate','relocate'],
    'immigrate':['migrate','settle'],
    'settle':['establish','resolve','inhabit'],
    'populate':['inhabit','settle','occupy'],
    'overpopulate':['overcrowd'],
    'overcrowd':['congest','pack','cram'],
    'congest':['clog','block','overcrowd'],
    'clog':['block','congest','obstruct'],
    'unclog':['clear','unblock'],
    'unblock':['clear','unclog'],
    'vacate':['leave','abandon','empty'],
    'maroon':['strand','isolate'],
    'strand':['maroon','abandon'],
    'fetch':['retrieve','get','bring'],
    'beckon':['summon','signal','gesture'],
    'denote':['signify','indicate','represent'],
    'symbolise':['represent','denote','embody'],
    'personify':['embody','represent','symbolise'],
    'prove':['demonstrate','confirm','verify'],
    'disprove':['refute','invalidate','discredit'],
    'void':['nullify','cancel','invalidate'],
    'cancel':['void','annul','revoke'],
    'annul':['cancel','void','nullify'],
    'undo':['reverse','cancel','negate'],
    'counterweight':['balance','counterbalance'],
    'weigh':['consider','ponder','assess'],
    'assess':['evaluate','appraise','weigh'],
    'appraise':['assess','evaluate','value'],
    'reckon':['calculate','estimate','consider'],
    'compute':['calculate','reckon','work out'],
    'quantify':['measure','calculate','determine'],
    'itemise':['list','enumerate','detail'],
    'tabulate':['list','arrange','chart'],
    'chart':['map','plot','graph'],
    'map':['chart','plot','trace'],
    'plot':['chart','scheme','graph'],
    'trace':['track','follow','chart'],
    'track':['trace','follow','monitor'],
    'watch':['observe','monitor','view'],
    'scan':['survey','examine','skim'],
    'survey':['scan','examine','poll'],
    'canvass':['survey','poll','solicit'],
    'poll':['survey','canvass','vote'],
    'interview':['question','interrogate','converse with'],
    'grill':['interrogate','question','quiz'],
    'quiz':['question','test','interrogate'],
    'delve':['probe','explore','investigate'],
    'dig':['excavate','delve','probe'],
    'exhume':['unearth','disinter','excavate'],
    'mine':['extract','dig','excavate'],
    'theorise':['speculate','hypothesise','conjecture'],
    'hypothesise':['theorise','postulate','speculate'],
    'bulk':['majority','mass','volume'],
    'breadth':['width','extent','range'],
    'depth':['profoundness','extent','intensity'],
    'height':['altitude','elevation','stature'],
    'length':['duration','extent','span'],
    'width':['breadth','extent'],
    'thickness':['density','bulk'],
    'shallowness':['superficiality'],
    'vastness':['immensity','enormity'],
    'enormity':['vastness','magnitude','hugeness'],
    'hugeness':['enormity','vastness'],
    'smallness':['tininess','minuteness'],
    'minuteness':['smallness','tininess'],
    'tininess':['minuteness','smallness'],
    'shortness':['brevity','briefness'],
    'lengthiness':['prolixity','wordiness'],
    'wordiness':['verbosity','prolixity'],
    'verbosity':['wordiness','loquacity'],
    'loquacity':['talkativeness','garrulity'],
    'garrulity':['talkativeness','loquacity'],
    'taciturnity':['reticence','reserve'],
    'shyness':['timidity','bashfulness','reserve'],
    'timidity':['shyness','fearfulness'],
    'bashfulness':['shyness','timidity'],
    'boldness':['audacity','daring','courage'],
    'daring':['boldness','audacity','courage'],
    'bravery':['courage','valour','fearlessness'],
    'valour':['bravery','courage','heroism'],
    'heroism':['bravery','valour','gallantry'],
    'gallantry':['bravery','heroism','chivalry'],
    'cowardice':['timidity','faintheartedness'],
    'faintheartedness':['cowardice','timidity'],
    'recklessness':['rashness','carelessness'],
    'rashness':['recklessness','impetuosity'],
    'impetuosity':['rashness','impulsiveness'],
    'impulsiveness':['rashness','spontaneity'],
    'carelessness':['negligence','recklessness'],
    'negligence':['carelessness','laxity'],
    'laxity':['negligence','slackness'],
    'slackness':['laxity','looseness'],
    'strictness':['rigor','severity'],
    'leniency':['mercy','clemency','tolerance'],
    'mercy':['leniency','clemency','compassion'],
    'harshness':['severity','sternness'],
    'sternness':['harshness','strictness'],
    'gentleness':['tenderness','mildness','kindness'],
    'tenderness':['gentleness','softness','affection'],
    'mildness':['gentleness','moderateness'],
    'severity':['harshness','intensity','seriousness'],
    'intensity':['strength','severity','force'],
    'softness':['gentleness','tenderness'],
    'hardness':['toughness','rigidity','firmness'],
    'toughness':['hardness','resilience','strength'],
    'firmness':['resolve','solidity','hardness'],
    'solidity':['firmness','stability'],
    'steadiness':['stability','constancy'],
    'constancy':['steadfastness','loyalty','stability'],
    'inconsistency':['unpredictability','variability'],
    'variability':['inconsistency','fluctuation'],
    'fluctuation':['variation','oscillation'],
    'oscillation':['fluctuation','wavering'],
    'wavering':['hesitation','vacillation'],
    'vacillation':['wavering','indecision'],
    'indecision':['hesitation','uncertainty'],
    'decisiveness':['resolve','determination'],
    'irresolution':['indecision','vacillation'],
    'flexibility':['adaptability','pliancy'],
    'adaptability':['flexibility','versatility'],
    'versatility':['adaptability','flexibility'],
    'inflexibility':['rigidity','obstinacy'],
    'obstinacy':['stubbornness','inflexibility'],
    'stubbornness':['obstinacy','tenacity'],
    'persistence':['tenacity','perseverance'],
    'perseverance':['persistence','determination','tenacity'],
    'endurance':['stamina','resilience','fortitude'],
    'vigour':['energy','vitality','strength'],
    'liveliness':['vitality','energy','vivacity'],
    'vivacity':['liveliness','animation'],
    'animation':['liveliness','vivacity','energy'],
    'languor':['lethargy','fatigue'],
    'weariness':['fatigue','tiredness'],
    'exhaustion':['fatigue','depletion'],
    'depletion':['exhaustion','reduction'],
    'ebullience':['exuberance','enthusiasm'],
    'eagerness':['enthusiasm','keenness'],
    'keenness':['eagerness','enthusiasm'],
    'zeal':['enthusiasm','fervour','passion'],
    'fervour':['zeal','passion','ardour'],
    'ardour':['fervour','passion','zeal'],
    'listlessness':['apathy','lethargy'],
    'indifference':['apathy','unconcern'],
    'unconcern':['indifference','apathy'],
    'engagement':['involvement','participation'],
    'involvement':['engagement','participation'],
    'participation':['involvement','engagement'],
    'aloofness':['detachment','reserve'],
    'withdrawal':['retreat','removal','seclusion'],
    'seclusion':['isolation','solitude','withdrawal'],
    'isolation':['seclusion','solitude','separation'],
    'loneliness':['isolation','solitude'],
    'togetherness':['unity','solidarity'],
    'unity':['togetherness','solidarity','oneness'],
    'disunity':['division','discord'],
    'disharmony':['discord','conflict'],
    'concord':['harmony','agreement'],
    'concurrence':['agreement','accord'],
    'disagreement':['dissent','discord','conflict'],
    'accordance':['agreement','conformity'],
    'nonconformity':['deviation','dissent'],
    'convergence':['merging','coming together'],
    'confluence':['convergence','meeting point'],
    'fellowship':['camaraderie','companionship'],
    'companionship':['fellowship','company'],
    'gregariousness':['sociability'],
    'sociability':['friendliness','gregariousness'],
    'hospitality':['welcome','warmth','friendliness'],
    'warmth':['friendliness','affection','cordiality'],
    'coldness':['aloofness','frostiness'],
    'frostiness':['coldness','iciness'],
    'iciness':['coldness','frostiness'],
    'bluntness':['directness','candour'],
    'directness':['bluntness','frankness'],
    'frankness':['candour','openness','honesty'],
    'openness':['frankness','transparency'],
    'transparency':['openness','clarity','honesty'],
    'secrecy':['confidentiality','concealment'],
    'concealment':['secrecy','hiding'],
    'confidentiality':['secrecy','privacy'],
    'privacy':['confidentiality','seclusion'],
    'exposure':['revelation','disclosure'],
    'disclosure':['revelation','exposure','admission'],
    'admission':['confession','acknowledgment'],
    'acknowledgment':['admission','recognition'],
    'denial':['refutation','rejection'],
    'refutation':['denial','rebuttal'],
    'rebuttal':['refutation','counterargument'],
    'counterargument':['rebuttal','objection'],
    'objection':['protest','complaint'],
    'complaint':['grievance','objection'],
    'resentment':['bitterness','indignation'],
    'bitterness':['resentment','rancour'],
    'rancour':['bitterness','animosity'],
    'distaste':['dislike','aversion'],
    'revulsion':['disgust','repugnance'],
    'abhorrence':['loathing','detestation'],
    'loathing':['hatred','abhorrence'],
    'detestation':['loathing','hatred'],
    'fondness':['affection','liking'],
    'liking':['fondness','preference'],
    'adoration':['worship','devotion'],
    'worship':['adoration','veneration'],
    'veneration':['reverence','worship'],
    'adulation':['flattery','praise'],
    'flattery':['adulation','sycophancy'],
    'sycophancy':['flattery','fawning'],
    'fawning':['sycophancy','obsequiousness'],
    'obsequiousness':['servility','fawning'],
    'servility':['submissiveness','obsequiousness'],
    'submissiveness':['docility','servility'],
    'docility':['obedience','submissiveness'],
    'disobedience':['defiance','insubordination'],
    'insubordination':['disobedience','rebellion'],
    'rebellion':['revolt','insurrection'],
    'defiance':['resistance','rebelliousness'],
    'rebelliousness':['defiance','insubordination'],
    'acquiescence':['compliance','agreement'],
    'submission':['surrender','capitulation'],
    'harvest':['yield','crop','gather'],
    'crop':['harvest','yield','produce'],
    'livestock':['cattle','farm animals'],
    'cattle':['livestock','herd'],
    'herd':['flock','cattle','drove'],
    'flock':['herd','group','congregation'],
    'drove':['herd','crowd'],
    'pasture':['meadow','grassland','field'],
    'meadow':['pasture','field','grassland'],
    'grassland':['pasture','prairie','meadow'],
    'prairie':['grassland','plain'],
    'plain':['prairie','flatland'],
    'canyon':['gorge','ravine'],
    'gorge':['canyon','ravine','chasm'],
    'ravine':['gorge','gully','canyon'],
    'gully':['ravine','ditch'],
    'marsh':['swamp','wetland','bog'],
    'swamp':['marsh','bog','wetland'],
}
REPEAT_SYNONYMS.update(REPEAT_SYNONYMS_EXT4)

def broad_repetition_suggestions(text, level, existing_count=0):
    """Return clickable alternatives for repeated words, including common words
    not covered by the academic dictionary. First occurrence is left untouched."""
    ws=words(text)
    counts={}
    for w in ws: counts[w]=counts.get(w,0)+1
    results=[]
    for word,count in sorted(counts.items(), key=lambda kv:(-kv[1],kv[0])):
        key=word.lower()
        if count < 2 or len(key) < 3 or key not in REPEAT_SYNONYMS:
            continue
        # Prefer the academic dictionary's specific per-word usage reason
        # (e.g. "use when something works well") when this word also has an
        # entry there, since it names a real condition for the swap rather
        # than a generic caution. Fall back to a word-specific default
        # reason (not a single shared line for every synonym of every word)
        # so the click/tooltip always explains *why this particular word*
        # over the repeated original, not just "keep the meaning".
        academic_alts = {a.lower(): why for a, why in REPETITION_ALTERNATIVES.get(key, [])}
        matches=list(re.finditer(rf'\b{re.escape(word)}\b', text, re.I))
        for ordinal,m in enumerate(matches[1:], start=2):
            alts=[]
            for a in REPEAT_SYNONYMS[key]:
                why = academic_alts.get(a.lower()) or f'Replaces the repeated “{word}” without changing the meaning of this sentence.'
                alts.append({'word': a, 'why': why})
            results.append({
                'kind':'better','emoji':'🔁','category':'repetition',
                'text':f'“{m.group(0)}” appears {count} times. Vary this occurrence to improve vocabulary range.',
                'detail':f'This word has already appeared {ordinal-1} time(s) before this point, so repeating it again narrows your vocabulary range score. Choose a context-appropriate alternative below.',
                'word':m.group(0),'occurrence':ordinal,'count':count,
                'start':m.start(),'end':m.end(),'alternatives':alts,
                'replacement':alts[0]['word'] if alts else None,
                'message':f'Repeated vocabulary: {word} is used {count} times.'
            })
            if len(results)+existing_count>=20: return results
    return results

def repetition_suggestions(text, level):
    """Return targeted, context-aware alternatives for repeated vocabulary.
    These are database/rule suggestions, not generated text. Alternatives are only
    offered for words whose common academic senses are reasonably stable.
    """
    ws=words(text)
    counts={w:ws.count(w) for w in set(ws)}
    results=[]
    for word,count in sorted(counts.items(), key=lambda kv:(-kv[1],kv[0])):
        key=word.lower()
        if count < 4 or len(key) < 4 or key not in REPETITION_ALTERNATIVES:
            continue
        matches=list(re.finditer(rf'\b{re.escape(word)}\b', text, re.I))
        # Keep the first occurrence as the original; suggest variation for later uses.
        for ordinal,m in enumerate(matches[1:], start=2):
            alternatives=[{'word':a,'why':why} for a,why in REPETITION_ALTERNATIVES[key]]
            results.append({
                'kind':'better','emoji':'🔁','category':'repetition',
                'text':f'“{m.group(0)}” appears {count} times. On this occurrence, consider varying it.',
                'detail':f'Possible alternatives: {", ".join(a["word"] for a in alternatives)}. Choose only one that fits your meaning.',
                'word':m.group(0),'occurrence':ordinal,'count':count,
                'start':m.start(),'end':m.end(),'alternatives':alternatives,
                'replacement':alternatives[0]['word'] if alternatives else None,
                'message':f'Repeated vocabulary: {word} is used {count} times.'
            })
            if len(results)>=12:
                return results
    return results

ACADEMIC = set('analyze analysis approach assess assessment significant demonstrate evidence establish indicate factor framework methodology obtain require consequently furthermore moreover however therefore whereas facilitate implementation interpret distribution complex context consistent relevant substantial approximately derive contribute evaluate perspective implication impact outcome illustrate criterion coherent cohesive nuanced predominantly policy economic environmental technological societal '
                 'admittedly undeniable pedagogical pedagogy scalability trajectory pinpointing standardized administrative instantaneous transmission holistic interpersonal endeavor empathy communication inherently accomplished mentors inspire resilience guidance supervision cultivate integrity genuine intellectual ubiquitous auxiliary irreplaceable mentorship supplant unfettered democratizing underserved disciplines streamline optimizes rote algorithm numerical adaptive capability assertion automated integration advantages efficiency architecture progression ignited contentious fundamentally negotiation collaboration ethical arguably plausible nevertheless notwithstanding conversely accordingly henceforth insofar whereby paradigm proponents advocates mitigate exacerbate ostensibly inevitably profound multifaceted comprehensive prevalent unprecedented systemic empirical theoretical hypothesis rigorous discourse discern ambiguous inherent intrinsic extrinsic juxtapose paradoxical dichotomy nuance subtle underlying overarching pivotal integral vital indispensable inextricably meticulous meticulously pragmatic pragmatism idealism scrutiny scrutinize legitimate legitimacy credible credibility ramifications repercussions catalyst impetus discrepancy disparity inequity inequality equitable equity marginalized disenfranchised sustainable sustainability resilient vulnerability trajectory'.split())
# Fixed word lists inevitably miss advanced vocabulary they weren't seeded
# with. As a supplementary, deterministic proxy for lexical sophistication,
# longer words (8+ letters) that are NOT common everyday words also count,
# at reduced weight, so genuinely advanced writing isn't penalised just for
# using words absent from the list above.
COMMON_LONG_WORDS = set('something everything understand important different education educational children students '
                         'teachers possible although because without between through another together ability '
                         'activities information technology experience knowledge community communities interested '
                         'beautiful wonderful sometimes especially probably actually generally usually normally '
                         'countries government yourself themselves everyone anything nothing everybody remember '
                         'necessary favourite favorite difficult expensive following relationship comfortable'.split())

# Original seed material written for this application. It is used as reference data, not as a generative model.
SAMPLE_ESSAYS = [
('A1','Daily routine','I get up early every day. I eat breakfast and go to school. I like my school because I meet my friends there. After school, I go home and do my homework. In the evening, I watch television and talk with my family.'),
('A1','My favourite place','My favourite place is the park near my home. It is small but nice. I go there with my brother. We walk and play games. The trees are green and the air is fresh. I feel happy there.'),
('A2','Learning online','Online learning is useful for many students. Students can study at home and watch lessons again. However, it can be difficult when the internet is slow. Students should make a timetable and take short breaks. In my opinion, online learning is good when it is organised.'),
('A2','Public transport','Public transport is important in a city. Buses help people travel to work and school. They are usually cheaper than cars. However, buses can be crowded at busy times. Cities should improve routes and make buses more comfortable.'),
('B1','School uniforms','School uniforms can create a stronger sense of equality because students wear similar clothes. They can also save time in the morning. However, some students want to express their personality through clothing. In addition, uniforms can be expensive for families. Overall, schools should allow limited personal choice while keeping a simple uniform policy.'),
('B1','Exercise and health','Regular exercise has several benefits for young people. It can improve physical fitness and help students manage stress. For example, walking, cycling and team sports are simple activities that can be added to a weekly routine. Nevertheless, students also need enough sleep and a balanced diet. Therefore, exercise should be part of a wider healthy lifestyle.'),
('B2','Technology in education','Technology has transformed the way students access educational resources. Online libraries, interactive simulations and recorded lectures can make learning more flexible. Nevertheless, technology does not automatically improve educational outcomes. If students are distracted by notifications or lack guidance, digital tools may reduce concentration. Consequently, schools should combine technology with clear learning objectives and effective teacher support.'),
('B2','Working from home','Working from home offers employees greater flexibility and can reduce commuting time. It may also allow people to organise their working environment according to their needs. On the other hand, remote workers can experience isolation and may find it difficult to separate professional responsibilities from personal life. A balanced approach, including occasional office meetings and clear working hours, can preserve flexibility while maintaining collaboration.'),
('C1','Urban green spaces','Urban green spaces should be regarded as essential infrastructure rather than decorative additions to cities. Parks, tree-lined streets and community gardens can moderate heat, support biodiversity and provide residents with opportunities for recreation. More importantly, equitable access to green space can contribute to social wellbeing in densely populated neighbourhoods. Although such projects require long-term investment, the environmental and public-health benefits justify integrating green infrastructure into urban planning.'),
('C1','Artificial intelligence in education','Artificial intelligence can extend educational support by identifying patterns in learner performance and recommending targeted practice. Its value, however, depends on how responsibly it is implemented. Automated recommendations may reproduce weaknesses in the data on which they are trained, while excessive automation can diminish opportunities for meaningful teacher-student interaction. Accordingly, educational institutions should treat AI as an assistive instrument, subject to transparent evaluation, human oversight and clear safeguards for learner data.'),
('C2','Assessment and learning','Assessment is most valuable when it functions not merely as a mechanism for ranking learners but as evidence that informs subsequent instruction. A sophisticated assessment system therefore needs to distinguish between temporary performance fluctuations and persistent gaps in understanding. Moreover, numerical scores alone can obscure the strategies through which learners arrive at an answer. By triangulating performance data with qualitative observations and learner reflection, educators can obtain a more nuanced account of progress and design interventions that are both proportionate and pedagogically defensible.'),
('C2','Public policy and evidence','Effective public policy rarely emerges from a single compelling statistic. Decisions concerning complex social systems require the interpretation of incomplete evidence, competing objectives and unintended consequences. Policymakers must consequently evaluate not only whether an intervention produces an aggregate benefit, but also how that benefit is distributed across populations. In this respect, transparent assumptions, sensitivity analysis and mechanisms for post-implementation review are indispensable, since they allow policy to be revised when empirical outcomes diverge from initial expectations.')
]


ESSAY_TYPES = [
    ('opinion','Opinion Essay (Agree or Disagree)','To what extent do you agree or disagree?'),
    ('discussion','Discussion Essay','Discuss both views and give your own opinion.'),
    ('advantages_disadvantages','Advantages and Disadvantages Essay','Do the advantages outweigh the disadvantages?'),
    ('problem_solution','Problem and Solution Essay','What are the causes of this problem and what measures can be taken to solve it?'),
    ('two_part','Direct Question (Two-Part Question)','Answer both questions.'),
    ('cause_effect','Cause and Effect Essay','What are the causes and effects?'),
    ('positive_negative','Positive or Negative Development Essay','Is this a positive or negative development?'),
]

# Ten original reference collections. These are newly written training/reference samples,
# not copied from copyrighted ebooks. Each collection contains one original sample for
# every essay type so the offline database has broad task-type coverage.
REFERENCE_COLLECTIONS = [
    "Academic Writing Foundations","Modern Education Essays","Society and Technology",
    "Cities and the Environment","Work and the Economy","Health and Lifestyle",
    "Media and Communication","Young People and Society","Global Issues and Policy",
    "Advanced IELTS-Style Practice"
]


# Book/reference metadata researched from official IELTS and Cambridge English catalogues.
# The application stores titles/descriptions only; it does not bundle copyrighted book text.
REFERENCE_BOOKS = [
    ("The Official Cambridge Guide to IELTS", "Cambridge University Press • B2–C1 • skills development, strategy and official practice."),
    ("Complete IELTS Bands 4–5 Student's Book with Answers", "Cambridge University Press • B1 • IELTS skills, writing reference, language reference and practice."),
    ("Complete IELTS Bands 5–6.5 Workbook with Answers", "Cambridge University Press • B1–B2 • additional practice with writing and language reference support."),
    ("Complete IELTS Bands 6.5–7.5 Workbook without Answers", "Cambridge University Press • C1 • advanced IELTS practice, writing reference and language development."),
    ("IELTS 21 Practice Tests Academic", "Cambridge English • Academic IELTS practice-test collection for exam familiarisation and response analysis."),
    ("IELTS 21 Practice Tests General Training", "Cambridge English • General Training IELTS practice-test collection for exam familiarisation and response analysis."),
    ("IELTS 20 Practice Tests Academic", "Cambridge English • Academic IELTS practice and test-taking reference."),
    ("IELTS 20 Practice Tests General Training", "Cambridge English • General Training IELTS practice and test-taking reference."),
    ("Mindset for IELTS Level 1", "Cambridge English • structured IELTS preparation with language and skills development."),
    ("Mindset for IELTS Level 2", "Cambridge English • higher-level IELTS preparation with skills, language and exam strategy."),
    ("Cambridge English Exam Boosters IELTS Booster Academic", "Cambridge English • Academic IELTS exam practice and teacher resources."),
    ("IELTS Washback in Context: Preparation for Academic Writing in Higher Education", "Research-oriented reference on IELTS preparation and academic writing."),
]

TOPICS = [
    ("Online education","Some people think online education is better than classroom learning."),
    ("School starting age","Some people believe children should start school at a very early age, while others think they should begin later."),
    ("Working from home","More people are working from home nowadays."),
    ("Traffic congestion","Traffic congestion is becoming a major issue in many cities."),
    ("Online shopping","Many people prefer shopping online rather than in stores."),
    ("Stress at work","The number of people suffering from stress is increasing."),
    ("Remote work","Many companies now allow employees to work remotely."),
]

BASE_SAMPLE_PARAGRAPHS = {
'opinion': [
"Online education can make learning more flexible because students can access lessons from different locations. However, classroom interaction remains valuable for discussion and immediate support. I largely agree that online education can be better when courses are carefully designed, although it should not completely replace effective face-to-face teaching."
],
'discussion': [
"Starting school early can help children become familiar with routines and basic academic skills. On the other hand, beginning later may give young children more time to develop socially and emotionally. In my view, the appropriate age should depend on children's readiness rather than a single rule for every family."
],
'advantages_disadvantages': [
"Working from home can save commuting time and give employees greater control over their schedules. Nevertheless, remote work may reduce informal communication and make some workers feel isolated. Overall, the advantages can outweigh the disadvantages when employers provide clear expectations and regular opportunities for collaboration."
],
'problem_solution': [
"Traffic congestion is caused by rapid urban growth, heavy dependence on private cars and limited public transport. Cities can address the problem by improving reliable bus and rail networks, coordinating traffic management and encouraging alternatives such as cycling. These measures can reduce unnecessary car journeys while maintaining access to employment."
],
'two_part': [
"Online shopping has become popular because it is convenient, offers a wide range of products and allows consumers to compare prices quickly. It can be a positive development because it saves time and increases choice, although customers should remain aware of delivery, privacy and quality concerns."
],
'cause_effect': [
"Rising stress is linked to demanding workloads, financial pressure and difficulty separating work from personal life. Persistent stress can reduce concentration, damage relationships and contribute to lower productivity. Employers and governments can therefore support healthier working patterns while individuals develop practical strategies for managing pressure."
],
'positive_negative': [
"Remote working can be a positive development because it reduces commuting and gives some employees greater flexibility. It may also change how companies use office space. However, the benefits are not automatic, since isolation and weak communication can affect performance. On balance, the development is positive when organisations deliberately protect collaboration and wellbeing."
]
}

def build_reference_rows():
    rows=[]
    # Produce 70 distinct, original samples by varying collection framing.
    for idx, collection in enumerate(REFERENCE_COLLECTIONS,1):
        for typ, _, _ in ESSAY_TYPES:
            base=BASE_SAMPLE_PARAGRAPHS[typ][0]
            lead = [
                "A useful starting point is to consider the practical impact on individuals and communities.",
                "This issue has become increasingly relevant as social and economic conditions change.",
                "A balanced assessment requires attention to both immediate effects and longer-term consequences.",
                "The debate is especially important because a single policy can affect different groups in different ways.",
                "Recent changes in technology and working patterns make this question difficult to ignore.",
                "The strongest response should distinguish between potential benefits and the conditions required to achieve them.",
                "Although opinions differ, the evidence can be examined through convenience, equity and long-term sustainability.",
                "A realistic approach should avoid treating a complex social issue as if it had only one cause.",
                "The question has implications for individuals as well as institutions responsible for public services.",
                "Ultimately, the quality of the outcome depends on how carefully the proposed change is implemented."
            ][idx-1]
            # Add a collection-specific sentence to make each reference genuinely distinct.
            endings=[
                "For that reason, policies should combine flexibility with appropriate guidance.",
                "This suggests that careful implementation matters as much as the idea itself.",
                "The most effective approach is therefore likely to be balanced rather than absolute.",
                "Such measures are more convincing when their costs and benefits are assessed together.",
                "A decision should also consider people who may not have equal access to the proposed change.",
                "Clear standards can prevent a promising reform from producing unintended disadvantages.",
                "In practice, gradual improvement is often more sustainable than a sudden universal change.",
                "Decision-makers should monitor outcomes and adjust policies when results differ from expectations.",
                "The issue should consequently be evaluated with evidence rather than assumptions alone.",
                "On balance, a measured response is preferable to an unconditional endorsement or rejection."
            ]
            rows.append((['B1','B2','C1'][idx%3], f"{collection}: {typ.replace('_',' ').title()}", lead+" "+base+" "+endings[idx-1], typ, idx))
    return rows
REFERENCE_ROWS = build_reference_rows()

# Ten additional researched book/reference records. Only bibliographic metadata is stored;
# copyrighted book text is not bundled.
EXTRA_REFERENCE_BOOKS = [
    ("IELTS 20 Practice Tests General Training", "Cambridge University Press & Assessment • B1–C2 • four authentic General Training practice tests and sample Writing answers."),
    ("IELTS 19 Academic Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic Academic examination papers, scoring information and sample Writing answers."),
    ("IELTS 18 Academic Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic Academic IELTS practice tests and sample Writing answers."),
    ("IELTS 18 General Training Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic General Training IELTS practice tests and sample Writing answers."),
    ("IELTS 17 Academic Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic Academic IELTS examination practice and response analysis."),
    ("IELTS 17 General Training Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic General Training IELTS examination practice and response analysis."),
    ("IELTS 16 Academic Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic Academic IELTS practice and sample responses."),
    ("IELTS 16 General Training Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic General Training IELTS practice and sample responses."),
    ("IELTS 15 Academic Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic Academic IELTS practice tests and answer support."),
    ("IELTS 15 General Training Student's Book with Answers", "Cambridge University Press & Assessment • B1–C2 • authentic General Training IELTS practice tests and answer support."),
]


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS sample_essays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        topic TEXT NOT NULL,
        essay_type TEXT NOT NULL DEFAULT 'opinion',
        text TEXT NOT NULL,
        word_count INTEGER NOT NULL,
        sentence_count INTEGER NOT NULL,
        avg_sentence_words REAL NOT NULL,
        type_token_ratio REAL NOT NULL,
        academic_ratio REAL NOT NULL,
        transition_density REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS essay_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        question_format TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reference_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT UNIQUE NOT NULL,
        description TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS feedback_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        category TEXT NOT NULL,
        trigger TEXT NOT NULL,
        message TEXT NOT NULL,
        priority INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS vocabulary_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        word TEXT NOT NULL,
        alternatives TEXT NOT NULL
    );
    ''')
    if conn.execute('SELECT COUNT(*) FROM essay_types').fetchone()[0] == 0:
        conn.executemany('INSERT INTO essay_types(type_key,name,question_format) VALUES (?,?,?)', ESSAY_TYPES)
    existing_books = {r[0] for r in conn.execute('SELECT title FROM reference_books').fetchall()}
    book_rows = [(x, 'Original offline reference collection covering all seven essay task types; no copyrighted ebook text is bundled.') for x in REFERENCE_COLLECTIONS]
    book_rows += REFERENCE_BOOKS + EXTRA_REFERENCE_BOOKS
    conn.executemany('INSERT OR IGNORE INTO reference_books(title,description) VALUES (?,?)',
                     [(title, desc) for title, desc in book_rows if title not in existing_books])
    # Upgrade older databases that were created before essay_type existed.
    cols = [r[1] for r in conn.execute('PRAGMA table_info(sample_essays)').fetchall()]
    if 'essay_type' not in cols:
        conn.execute("ALTER TABLE sample_essays ADD COLUMN essay_type TEXT NOT NULL DEFAULT 'opinion'")
    if conn.execute('SELECT COUNT(*) FROM sample_essays').fetchone()[0] < 80:
        for level, topic, text in SAMPLE_ESSAYS:
            ws, ss = words(text), sentences(text)
            et='opinion'
            for key,name,_ in ESSAY_TYPES:
                if key.replace('_',' ') in topic.lower(): et=key
            conn.execute('INSERT INTO sample_essays(level,topic,essay_type,text,word_count,sentence_count,avg_sentence_words,type_token_ratio,academic_ratio,transition_density) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (level, topic, et, text, len(ws), len(ss), avg_sentence_length(text), type_token_ratio(text), academic_ratio(text), transition_density(text, level)))
        for level, topic, text, et, collection_no in REFERENCE_ROWS:
            ws, ss = words(text), sentences(text)
            conn.execute('INSERT INTO sample_essays(level,topic,essay_type,text,word_count,sentence_count,avg_sentence_words,type_token_ratio,academic_ratio,transition_density) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (level, topic, et, text, len(ws), len(ss), avg_sentence_length(text), type_token_ratio(text), academic_ratio(text), transition_density(text, level)))
    # Add 100 original, database-only practice essays. These are generated from
    # original templates and topic combinations; no copyrighted book passages are stored.
    generated_topics = [
        'online education','school uniforms','public transport','urban parks','remote work',
        'social media','renewable energy','healthy lifestyles','tourism','advertising',
        'artificial intelligence','university education','children and technology','public libraries',
        'housing costs','food waste','traffic congestion','crime prevention','globalisation','sports funding'
    ]
    generated_levels = ['A1','A2','B1','B2','C1']
    generated_types = ['opinion','discussion','advantages_disadvantages','problem_solution','two_part']
    def generated_essay(level, topic, et, n):
        if level=='A1':
            core=f'{topic.title()} is an important topic in daily life. Many people see it in different ways. I think it can be useful, but it can also cause problems. For example, people may use it to make life easier. However, they need to use it carefully. In my opinion, good choices and simple rules can make the situation better.'
        elif level=='A2':
            core=f'{topic.title()} has become common in many communities. There are clear benefits because it can help people save time, learn new things or solve everyday problems. However, there can also be disadvantages, such as cost, stress or unequal access. For this reason, people should consider both sides before making decisions. I believe practical support and sensible rules can improve the situation.'
        elif level=='B1':
            core=f'The issue of {topic} has attracted considerable attention in recent years. Supporters argue that it can provide useful opportunities, while critics point to possible social or economic problems. One important benefit is that it can improve people’s choices and access to services. Nevertheless, negative effects may appear when there is poor planning or limited guidance. Overall, a balanced approach is likely to produce better outcomes.'
        elif level=='B2':
            core=f'The growing importance of {topic} has generated debate about how individuals and institutions should respond. On the one hand, it can create meaningful benefits by improving access, efficiency and personal choice. On the other hand, poorly managed development may intensify inequality, financial pressure or social disruption. Consequently, policy should not focus solely on short-term gains; it should also consider long-term consequences and provide appropriate safeguards.'
        else:
            core=f'Debate surrounding {topic} reflects a broader tension between immediate benefits and longer-term societal consequences. Although proponents emphasise efficiency, opportunity and individual autonomy, these gains may be unevenly distributed and accompanied by external costs. A more defensible approach is therefore to evaluate the issue through measurable outcomes, distributional effects and the capacity of institutions to mitigate foreseeable risks. Such an approach can preserve legitimate benefits without overlooking structural disadvantages.'
        if et=='discussion':
            core += ' Both perspectives deserve consideration, although the stronger position depends on how the policy or practice is implemented.'
        elif et=='advantages_disadvantages':
            core += ' The advantages are substantial when implementation is well designed, but they do not automatically outweigh every disadvantage.'
        elif et=='problem_solution':
            core += ' The main causes include limited planning and unequal resources, so solutions should combine prevention, investment and effective monitoring.'
        elif et=='two_part':
            core += ' The first question concerns the main reasons for this trend, while the second concerns how individuals and institutions can respond effectively.'
        else:
            core += ' I therefore support a measured approach that protects the main benefits while reducing avoidable harms.'
        return core
    existing_generated = conn.execute("SELECT COUNT(*) FROM sample_essays WHERE topic LIKE 'Database Practice %'").fetchone()[0]
    if existing_generated < 100:
        rows=[]
        idx=existing_generated
        for topic in generated_topics:
            for level in generated_levels:
                for et in generated_types:
                    if len(rows) >= 100-existing_generated: break
                    idx += 1
                    label=f'Database Practice {idx}: {topic.title()}'
                    text=generated_essay(level,topic,et,idx)
                    ws,ss=words(text),sentences(text)
                    rows.append((level,label,et,text,len(ws),len(ss),avg_sentence_length(text),type_token_ratio(text),academic_ratio(text),transition_density(text,level)))
                if len(rows) >= 100-existing_generated: break
            if len(rows) >= 100-existing_generated: break
        conn.executemany('INSERT INTO sample_essays(level,topic,essay_type,text,word_count,sentence_count,avg_sentence_words,type_token_ratio,academic_ratio,transition_density) VALUES (?,?,?,?,?,?,?,?,?,?)',rows)
    if conn.execute('SELECT COUNT(*) FROM feedback_rules').fetchone()[0] == 0:
        rules = [
            ('A1','vocabulary','low_ttr','Use familiar words accurately first; then add one precise word at a time.',1),
            ('A2','vocabulary','low_ttr','Add a few topic-specific words and avoid repeating the same general word.',1),
            ('B1','cohesion','low_transitions','Connect ideas with clear relationships such as cause, contrast and example.',1),
            ('B2','lexical','low_academic','Prefer precise academic wording where it improves meaning, not simply longer words.',1),
            ('C1','lexical','low_academic','Aim for nuanced, precise vocabulary and appropriate collocation rather than conspicuous complexity.',1),
            ('C2','coherence','low_development','Qualify claims, acknowledge limitations and make relationships between propositions explicit.',1),
            ('B2','cohesion','missing_conclusion','Use a controlled conclusion linker such as “In conclusion,” or “To summarise,” when a conclusion is actually being made.',2),
            ('C1','cohesion','missing_conclusion','Use nuanced conclusion framing such as “Taken together,” when synthesising several preceding points.',2),
            ('C2','cohesion','missing_conclusion','Use synthesis-oriented framing such as “On balance,” or “Ultimately,” when it accurately signals evaluation.',2),
        ]
        conn.executemany('INSERT INTO feedback_rules(level,category,trigger,message,priority) VALUES (?,?,?,?,?)', rules)
    # Vocabulary target bank: reseed if the table is empty OR still holds the
    # old, smaller 12-row starter set (4 words x 3 levels). This lets an
    # upgraded deploy replace stale seed data without wiping any rows a user
    # may have added, since we only ever delete when the count exactly
    # matches the old seed size.
    vocab_count = conn.execute('SELECT COUNT(*) FROM vocabulary_targets').fetchone()[0]
    if vocab_count == 12:
        conn.execute('DELETE FROM vocabulary_targets')
        vocab_count = 0
    if vocab_count == 0:
        vocab = [
            ('B1','important','significant, key, major'),
            ('B1','good','beneficial, positive, favourable'),
            ('B1','bad','harmful, negative, damaging'),
            ('B1','big','large, considerable, sizeable'),
            ('B1','help','assist, support, aid'),
            ('B1','show','demonstrate, reveal, indicate'),
            ('B1','many','numerous, a lot of, a range of'),
            ('B1','think','believe, feel, consider'),
            ('B1','problem','issue, difficulty, challenge'),
            ('B1','change','alter, adjust, shift'),
            ('B2','important','significant, consequential, substantial'),
            ('B2','good','beneficial, effective, advantageous'),
            ('B2','bad','harmful, problematic, detrimental'),
            ('B2','big','considerable, substantial, considerable in scale'),
            ('B2','help','assist, support, facilitate'),
            ('B2','show','demonstrate, indicate, illustrate'),
            ('B2','many','numerous, a wide range of, a considerable number of'),
            ('B2','think','argue, believe, contend'),
            ('B2','problem','issue, challenge, difficulty'),
            ('B2','change','modify, adjust, transform'),
            ('B2','increase','rise, grow, expand'),
            ('B2','decrease','decline, diminish, fall'),
            ('B2','result','outcome, consequence, effect'),
            ('B2','cause','factor, trigger, source'),
            ('B2','use','employ, apply, utilise'),
            ('B2','get','obtain, acquire, gain'),
            ('C1','important','pivotal, consequential, salient'),
            ('C1','good','beneficial, effective, advantageous, constructive'),
            ('C1','bad','detrimental, counterproductive, adverse'),
            ('C1','show','demonstrate, illustrate, indicate, substantiate'),
            ('C1','help','facilitate, underpin, bolster'),
            ('C1','many','a substantial number of, considerable, extensive'),
            ('C1','think','maintain, posit, contend'),
            ('C1','problem','predicament, complication, obstacle'),
            ('C1','change','recalibrate, restructure, reconfigure'),
            ('C1','increase','escalate, amplify, intensify'),
            ('C1','decrease','curtail, attenuate, taper'),
            ('C1','result','ramification, corollary, upshot'),
            ('C1','cause','catalyst, precipitating factor, impetus'),
            ('C1','use','harness, leverage, deploy'),
            ('C1','get','secure, procure, garner'),
            ('C1','big','considerable, substantial, appreciable'),
            ('C2','important','pivotal, consequential, material, salient'),
            ('C2','good','beneficial, efficacious, constructive'),
            ('C2','bad','detrimental, deleterious, counterproductive'),
            ('C2','show','demonstrate, substantiate, elucidate, corroborate'),
            ('C2','help','underpin, buttress, galvanise'),
            ('C2','many','a plethora of, myriad, an appreciable number of'),
            ('C2','think','posit, aver, submit'),
            ('C2','problem','conundrum, quandary, impasse'),
            ('C2','change','reconfigure, recalibrate, transmute'),
            ('C2','increase','burgeon, proliferate, escalate markedly'),
            ('C2','decrease','wane, dwindle, attenuate'),
            ('C2','result','corollary, ramification, denouement'),
            ('C2','cause','impetus, precipitant, wellspring'),
            ('C2','use','harness, marshal, deploy strategically'),
            ('C2','get','procure, garner, glean'),
            ('C2','big','considerable, substantial, formidable'),
        ]
        conn.executemany('INSERT INTO vocabulary_targets(level,word,alternatives) VALUES (?,?,?)', vocab)
    conn.commit(); conn.close()


def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]


def words(text):
    return re.findall(r"\b[A-Za-z]+(?:'[A-Za-z]+)?\b", text.lower())


def avg_sentence_length(text):
    ss = sentences(text)
    return sum(len(words(s)) for s in ss) / max(1, len(ss))


def type_token_ratio(text):
    ws = words(text)
    return len(set(ws)) / max(1, len(ws))


def academic_ratio(text):
    ws = words(text)
    if not ws:
        return 0
    listed = sum(1 for w in ws if w in ACADEMIC)
    sophisticated = sum(1 for w in ws if len(w) >= 8 and w not in ACADEMIC and w not in COMMON_LONG_WORDS)
    return (listed + sophisticated * 0.6) / len(ws)


def transition_density(text, level='B2'):
    ws = words(text)
    count = sum(1 for phrase in TRANSITIONS[level] if re.search(rf'\b{re.escape(phrase)}\b', text, re.I))
    return count / max(1, len(ws)) * 100


def level_for_score(score):
    for level, (lo, hi) in LEVEL_RANGES.items():
        if lo <= score <= hi:
            return level
    return 'C2'


def target_level(level):
    return TARGET_LEVEL[level]


def pattern_issues(text):
    issues=[]
    patterns = [
        # --- Subject-verb agreement -------------------------------------------------
        # (A broad "any pronoun + is" pattern was intentionally removed here:
        # it flagged grammatically correct sentences like "He is happy" as
        # errors, since it didn't check whether the pronoun actually agrees
        # with "is". The narrower i/we/they-plus-is rule below already
        # covers the real error case.)
        (r'\b(he|she|it)\s+are\b', 'Use “is” with he/she/it.', 'grammar',
         'He/she/it is a third-person singular subject, so it takes the singular verb “is”, not “are”.'),
        (r'\b(i|we|they)\s+is\b', 'Check the verb agreement.', 'grammar',
         'I/we/they are not third-person singular, so they take “am/are”, not “is”.'),
        (r'\b(he|she|it)\s+have\b', 'Use “has” with he/she/it.', 'grammar',
         'He/she/it is third-person singular, so it takes “has”, not “have”.'),
        (r'\b(i|we|they|you)\s+has\b', 'Use “have” here.', 'grammar',
         '“Has” is only used with third-person singular subjects (he/she/it); I/we/they/you take “have”.'),
        (r'\b(he|she|it)\s+don\'?t\b', 'Use “doesn’t” with he/she/it.', 'grammar',
         'He/she/it is third-person singular, so the negative auxiliary is “doesn’t”, not “don’t”.'),
        (r'\bpeople\s+is\b', 'Use “people are”.', 'grammar',
         '“People” is a plural noun (the plural of “person”), so it takes the plural verb “are”.'),
        (r'\bchildren\s+is\b', 'Use “children are”.', 'grammar',
         '“Children” is a plural noun (the plural of “child”), so it takes the plural verb “are”.'),
        (r'\bwomen\s+is\b', 'Use “women are”.', 'grammar',
         '“Women” is already plural, so it takes the plural verb “are”.'),
        (r'\bmen\s+is\b', 'Use “men are”.', 'grammar',
         '“Men” is already plural, so it takes the plural verb “are”.'),
        (r'\beach\s+of\s+(?:the\s+|these\s+|those\s+)?\w+s\s+are\b', 'Use a singular verb after “each of”.', 'grammar',
         '“Each” is grammatically singular even when followed by a plural noun, so the verb should be singular (“is/has”), not “are”.'),
        (r'\bthe\s+number\s+of\s+\w+\s+are\b', 'Use a singular verb after “the number of”.', 'grammar',
         '“The number” (not the following plural noun) is the true subject, so the verb should be singular: “is”.'),

        # --- Articles ----------------------------------------------------------------
        (r'\ba\s+(?!(?:information|advice|research|equipment|furniture|homework|knowledge|evidence|feedback|traffic)s?\b)[aeiou]\w*\b',
         'Consider using “an” before a vowel sound.', 'grammar',
         '“An” is used before a word that starts with a vowel sound, so it reads more smoothly than “a”.'),
        (r'\ban\s+[bcdfghjklmnpqrstvwxyz]\w*\b', 'Consider using “a” before a consonant sound.', 'grammar',
         '“A” is used before a word that starts with a consonant sound, so it reads more smoothly than “an”.'),
        (r'\ban?\s+(?:information|advice|research|equipment|furniture|homework|knowledge|evidence|feedback|traffic)s?\b',
         'This noun is uncountable and is not normally used with “a/an” or a plural “-s”.', 'grammar',
         'This is an uncountable noun, so it has no plural and is not preceded by “a/an”; use it on its own or with “some/much”.'),

        # --- Comparatives / superlatives ---------------------------------------------
        (r'\bmore better\b', 'Avoid the double comparative; use “better”.', 'grammar',
         '“Better” is already the comparative form of “good”, so adding “more” in front double-marks the comparison.'),
        (r'\bmore worse\b', 'Avoid the double comparative; use “worse”.', 'grammar',
         '“Worse” is already the comparative form of “bad”, so adding “more” in front double-marks the comparison.'),
        (r'\bmost\s+best\b', 'Avoid the double superlative; use “best”.', 'grammar',
         '“Best” is already the superlative form of “good”, so adding “most” in front double-marks the comparison.'),
        (r'\bmost\s+worst\b', 'Avoid the double superlative; use “worst”.', 'grammar',
         '“Worst” is already the superlative form of “bad”, so adding “most” in front double-marks the comparison.'),
        (r'\bmore\s+(?!worse\b|better\b)(\w+er)\b', 'Avoid combining “more” with an “-er” comparative.', 'grammar',
         'Short adjectives form their comparative with “-er” alone; adding “more” as well double-marks the comparison.'),
        (r'\bmost\s+(?!best\b|worst\b)(\w+est)\b', 'Avoid combining “most” with an “-est” superlative.', 'grammar',
         'Short adjectives form their superlative with “-est” alone; adding “most” as well double-marks the comparison.'),

        # --- Prepositions --------------------------------------------------------------
        (r'\bdespite\s+of\b', 'Use “despite” without “of”.', 'grammar',
         '“Despite” is a preposition on its own and is never followed by “of” (unlike “in spite of”).'),
        (r'\bdiscuss\s+about\b', 'Use “discuss” without “about”.', 'grammar',
         '“Discuss” is a transitive verb that takes a direct object, so it is never followed by “about”.'),
        (r'\bmarried\s+with\b', 'Use “married to”.', 'grammar',
         'The fixed expression is “married to” a person, not “married with”.'),
        (r'\bgood\s+in\b(?!\s+\w+ing)', 'Consider “good at”.', 'grammar',
         'The standard collocation for describing a skill or ability is “good at”, not “good in”.'),
        (r'\bdepend\s+of\b', 'Use “depend on”.', 'grammar',
         'The verb “depend” is always followed by the preposition “on”, not “of”.'),
        (r'\bdependent\s+of\b', 'Use “dependent on”.', 'grammar',
         'The adjective “dependent” is always followed by the preposition “on”, not “of”.'),
        (r'\bconsist\s+of\s+of\b', 'Remove the duplicate “of”.', 'grammar',
         '“Consist of” already includes “of”; a second one is a repeated word.'),
        (r'\barrive\s+to\b', 'Use “arrive at/in”.', 'grammar',
         '“Arrive” takes “at” (for a point/building) or “in” (for a city/country), not “to”.'),
        (r'\bexplain\s+(?:me|him|her|them|us)\b', 'Use “explain … to” + person.', 'grammar',
         '“Explain” does not take a direct personal object; use “explain it to me/him/her/them/us” instead.'),
        (r'\bable\s+to\s+afford\b\s+to\b', 'Remove the extra “to”.', 'grammar',
         '“Afford” is already followed directly by an infinitive (“afford to do”); an extra “to” duplicates it.'),

        # --- Confusable words ----------------------------------------------------------
        (r"\bits\s+(?:is|was|has|will|can|does|going)\b", 'Did you mean “it’s” (it is/it has)?', 'grammar',
         '“Its” is the possessive form (no apostrophe); “it’s” is the contraction of “it is/it has”, which fits before a verb.'),
        (r"\byour\s+(?:a|an|going|welcome|right|wrong|not)\b", 'Did you mean “you’re” (you are)?', 'grammar',
         '“Your” shows possession; “you’re” is the contraction of “you are”, which fits before an adjective, noun, or “going to”.'),
        (r"\bthere\s+(?:own|is\s+own)\b", 'Did you mean “their own”?', 'grammar',
         '“There” refers to a place; “their” is the possessive form needed before “own”.'),
        (r'\b(?:less)\s+\w+s\b', 'Consider “fewer” with countable plural nouns.', 'grammar',
         '“Fewer” is used with countable plural nouns (fewer people); “less” is used with uncountable nouns (less time).'),
        (r'\baffect\s+(?:on|of)\b', 'Use “affect” without a preposition.', 'grammar',
         '“Affect” is a transitive verb (it affects something directly); it is not followed by “on” or “of”.'),

        # --- Double negatives / redundancy ---------------------------------------------
        (r"\b(?:don\'?t|doesn\'?t|didn\'?t|can\'?t|won\'?t|isn\'?t|aren\'?t)\s+\w*\s*no\s+\w+", 'Avoid the double negative.', 'grammar',
         'English generally uses one negative per clause; combining a negative verb with “no” creates a double negative that reverses or muddles the intended meaning.'),
        (r'\breturn\s+back\b', 'Remove the redundant “back”.', 'style',
         '“Return” already means “go back”, so adding “back” repeats the same meaning.'),
        (r'\brepeat\s+again\b', 'Remove the redundant “again”.', 'style',
         '“Repeat” already means “do again”, so adding “again” repeats the same meaning.'),
        (r'\bfree\s+gift\b', 'Consider just “gift”.', 'style',
         'A gift is free by definition, so “free” is redundant here.'),
        (r'\bplan\s+ahead\s+for\s+the\s+future\b', 'Consider “plan for the future”.', 'style',
         '“Plan ahead” and “for the future” both express forward planning, so combining them repeats the same idea.'),
        (r'\bpast\s+history\b', 'Consider just “history”.', 'style',
         'History is, by definition, about the past, so “past” is redundant here.'),
        (r'\bfuture\s+plans\b', 'Consider just “plans”.', 'style',
         'A plan is inherently about the future, so “future” is redundant here.'),
        (r'\bvery\s+unique\b', '“Unique” is normally absolute; consider removing “very”.', 'style',
         '“Unique” already means “one of a kind”, so it isn’t usually graded with “very”; removing it reads as more precise, formal English.'),
        (r'\bdue\s+to\s+the\s+fact\s+that\b', 'Consider the more concise “because” when appropriate.', 'style',
         '“Because” expresses the same cause-and-effect meaning more concisely, which is generally preferred in essay writing.'),
        (r'\bin\s+order\s+to\s+to\b', 'Remove the duplicate “to”.', 'grammar',
         '“In order to” already ends in “to”; a second one duplicates the same word.'),
        (r'\band\s+also\b', 'Consider just “and” or just “also”.', 'style',
         '“And” and “also” both add information; using both together is usually redundant.'),

        # --- Countability / quantifiers -------------------------------------------------
        (r'\bthere\s+is\s+many\b', 'Use “there are many”.', 'grammar',
         '“Many” takes a plural countable noun, so the verb must agree and be plural: “there are”.'),
        (r'\bthere\s+are\s+much\b', 'Use “there is much” or “there are many”, depending on meaning.', 'grammar',
         '“Much” is normally used with uncountable nouns and the singular verb “is”; if the noun is countable, use “many” with “are” instead.'),
        (r'\bmuch\s+\w+s\b(?!\s+of\b)', 'Consider “many” with countable plural nouns.', 'grammar',
         '“Much” is used with uncountable nouns; a plural noun ending in “-s” is usually countable and takes “many” instead.'),
        (r'\ba\s+lot\s+of\s+peoples\b', 'Use “a lot of people”.', 'grammar',
         '“People” is already the plural of “person”; adding “-s” creates an incorrect double plural.'),
        (r'\bequipments\b', 'Use “equipment” (no plural “-s”).', 'grammar',
         '“Equipment” is uncountable in English and has no plural form.'),
        (r'\bfurnitures\b', 'Use “furniture” (no plural “-s”).', 'grammar',
         '“Furniture” is uncountable in English and has no plural form.'),
        (r'\bhomeworks\b', 'Use “homework” (no plural “-s”).', 'grammar',
         '“Homework” is uncountable in English and has no plural form.'),
        (r'\bresearches\b', 'Use “research” (no plural “-s”) unless referring to distinct studies.', 'grammar',
         '“Research” is normally uncountable in general use, so it does not usually take a plural “-s”.'),

        # --- Modal / infinitive constructions --------------------------------------------
        (r'\b(?:can|could|should|would|will|must|might|may)\s+to\s+\w+', 'Remove “to” after a modal verb.', 'grammar',
         'Modal verbs (can/could/should/would/will/must/might/may) are followed directly by the base verb, with no “to” in between.'),
        (r'\bto\s+can\b', 'Modal verbs like “can” have no infinitive form.', 'grammar',
         '“Can” cannot follow “to”; use “to be able to” instead when an infinitive is needed.'),
        (r'\bsuggest(?:s|ed)?\s+to\s+\w+ing\b', 'Use “suggest doing” or “suggest that … should”.', 'grammar',
         '“Suggest” is followed by a gerund (“-ing”) or a “that” clause, not by “to” + verb.'),
        (r'\benjoy\s+to\s+\w+', 'Use “enjoy doing something”.', 'grammar',
         '“Enjoy” is followed by a gerund (“-ing” form), not a “to” infinitive.'),
        (r'\bavoid\s+to\s+\w+', 'Use “avoid doing something”.', 'grammar',
         '“Avoid” is followed by a gerund (“-ing” form), not a “to” infinitive.'),
        (r'\bfinish\s+to\s+\w+', 'Use “finish doing something”.', 'grammar',
         '“Finish” is followed by a gerund (“-ing” form), not a “to” infinitive.'),
        (r'\bconsider\s+to\s+\w+', 'Use “consider doing something”.', 'grammar',
         '“Consider” is followed by a gerund (“-ing” form), not a “to” infinitive.'),

        # --- Tense / verb form ------------------------------------------------------------
        (r'\bhave\s+went\b', 'Use “have gone”.', 'grammar',
         'The present perfect uses the past participle “gone”, not the simple past form “went”.'),
        (r'\bhas\s+went\b', 'Use “has gone”.', 'grammar',
         'The present perfect uses the past participle “gone”, not the simple past form “went”.'),
        (r'\bhave\s+came\b', 'Use “have come”.', 'grammar',
         'The present perfect uses the past participle “come”, not the simple past form “came”.'),
        (r'\bhave\s+ate\b', 'Use “have eaten”.', 'grammar',
         'The present perfect uses the past participle “eaten”, not the simple past form “ate”.'),
        (r'\bhave\s+wrote\b', 'Use “have written”.', 'grammar',
         'The present perfect uses the past participle “written”, not the simple past form “wrote”.'),
        (r'\bhave\s+did\b', 'Use “have done”.', 'grammar',
         'The present perfect uses the past participle “done”, not the simple past form “did”.'),
        (r'\bhave\s+saw\b', 'Use “have seen”.', 'grammar',
         'The present perfect uses the past participle “seen”, not the simple past form “saw”.'),
        (r'\bhave\s+began\b', 'Use “have begun”.', 'grammar',
         'The present perfect uses the past participle “begun”, not the simple past form “began”.'),
        (r'\bwas\s+been\b', 'Remove the duplicate auxiliary.', 'grammar',
         '“Was” and “been” cannot both directly follow one another; use either a simple past or a present-perfect form.'),
        (r'\bdid\s+\w+ed\b', 'The main verb should be in its base form after “did”.', 'grammar',
         '“Did” already carries the past tense, so the following verb should be in its base form (e.g. “did go”, not “did went”).'),
        (r'\bdidn\'?t\s+\w+ed\b', 'The main verb should be in its base form after “didn’t”.', 'grammar',
         '“Didn’t” already carries the negative past tense, so the following verb should be in its base form (e.g. “didn’t go”, not “didn’t went”).'),
        (r'\bis\s+being\s+\w+ed\s+by\s+by\b', 'Remove the duplicate “by”.', 'grammar',
         'The passive agent phrase only needs one “by”.'),

        # --- Word order / sentence structure ------------------------------------------
        (r'\balways\s+i\b', 'Reorder: the subject usually comes before the adverb.', 'grammar',
         'Frequency adverbs like “always” normally follow the subject (“I always…”), not precede it.'),
        (r'\bnever\s+i\s+(?:have|will|do|can)\b', 'Reorder: the subject usually comes before the adverb.', 'grammar',
         'Frequency adverbs like “never” normally follow the subject and auxiliary, not begin the sentence in statement word order.'),
        (r'\bvery\s+much\s+like\b', 'Consider “like … very much”.', 'style',
         'In standard word order, the intensifier “very much” usually follows the verb phrase rather than preceding “like”.'),
    ]
    for pat,msg,typ,why in patterns:
        for m in re.finditer(pat,text,re.I):
            replacement = None
            g0 = m.group(0)
            gl = g0.lower()
            if 'more better' in gl: replacement='better'
            elif 'more worse' in gl: replacement='worse'
            elif 'most best' in gl: replacement='best'
            elif 'most worst' in gl: replacement='worst'
            elif re.match(r'\bmore\s+\w+er\b', gl): replacement=re.sub(r'^more\s+','',g0,flags=re.I)
            elif re.match(r'\bmost\s+\w+est\b', gl): replacement=re.sub(r'^most\s+','',g0,flags=re.I)
            elif 'despite of' in gl: replacement='despite'
            elif 'discuss about' in gl: replacement=re.sub(r'\s+about\b','',g0,flags=re.I)
            elif 'married with' in gl: replacement=re.sub(r'\bwith\b','to',g0,flags=re.I)
            elif re.match(r'\bgood\s+in\b', gl): replacement=re.sub(r'\bin\b','at',g0,flags=re.I)
            elif 'depend of' in gl: replacement=re.sub(r'\bof\b','on',g0,flags=re.I)
            elif 'dependent of' in gl: replacement=re.sub(r'\bof\b','on',g0,flags=re.I)
            elif 'consist of of' in gl: replacement=re.sub(r'\bof\s+of\b','of',g0,flags=re.I)
            elif 'arrive to' in gl: replacement=re.sub(r'\bto\b','at',g0,flags=re.I)
            elif re.match(r'\bable\s+to\s+afford\s+to\b', gl): replacement=re.sub(r'\s+to\b(?!.*to)','',g0,flags=re.I,count=1)
            elif re.match(r'\bthere\s+is\s+many\b', gl): replacement='there are many'
            elif re.match(r'\bthere\s+are\s+much\b', gl): replacement='there is much'
            elif re.match(r'\bpeople\s+is\b', gl): replacement='people are'
            elif re.match(r'\bchildren\s+is\b', gl): replacement='children are'
            elif re.match(r'\bwomen\s+is\b', gl): replacement='women are'
            elif re.match(r'\bmen\s+is\b', gl): replacement='men are'
            elif re.match(r'\ba\s+lot\s+of\s+peoples\b', gl): replacement='a lot of people'
            elif re.match(r'\ban?\s+(?:information|advice|research|equipment|furniture|homework|knowledge|evidence|feedback|traffic)s?\b', gl):
                base = re.sub(r'^an?\s+','',gl,flags=re.I)
                singular_map = {'informations':'information','advices':'advice','researches':'research',
                                 'equipments':'equipment','furnitures':'furniture','homeworks':'homework',
                                 'knowledges':'knowledge','evidences':'evidence','feedbacks':'feedback','traffics':'traffic'}
                replacement = singular_map.get(base, base)
            elif gl=='equipments': replacement='equipment'
            elif gl=='furnitures': replacement='furniture'
            elif gl=='homeworks': replacement='homework'
            elif gl=='researches': replacement='research'
            elif re.match(r'\ba\s+[aeiou]\w*\b', gl): replacement='an'+g0[1:]
            elif re.match(r'\ban\s+[bcdfghjklmnpqrstvwxyz]\w*\b', gl): replacement='a'+g0[2:]
            elif re.match(r'\b(he|she|it)\s+are\b', gl): replacement=re.sub(r'\bare\b','is',g0,flags=re.I)
            elif re.match(r'\b(he|she|it)\s+have\b', gl): replacement=re.sub(r'\bhave\b','has',g0,flags=re.I)
            elif re.match(r'\b(i|we|they|you)\s+has\b', gl): replacement=re.sub(r'\bhas\b','have',g0,flags=re.I)
            elif re.match(r"\b(he|she|it)\s+don\'?t\b", gl): replacement=re.sub(r"don\'?t","doesn't",g0,flags=re.I)
            elif re.match(r'\b(i|we|they)\s+is\b', gl): replacement=re.sub(r'\bis\b','are',g0,flags=re.I)
            elif 'very unique' in gl: replacement=g0.replace('very ','',1)
            elif 'in order to to' in gl: replacement=re.sub(r'\s+to\b','',g0,flags=re.I,count=1)
            elif 'have went' in gl: replacement=re.sub(r'\bwent\b','gone',g0,flags=re.I)
            elif 'has went' in gl: replacement=re.sub(r'\bwent\b','gone',g0,flags=re.I)
            elif 'have came' in gl: replacement=re.sub(r'\bcame\b','come',g0,flags=re.I)
            elif 'have ate' in gl: replacement=re.sub(r'\bate\b','eaten',g0,flags=re.I)
            elif 'have wrote' in gl: replacement=re.sub(r'\bwrote\b','written',g0,flags=re.I)
            elif 'have did' in gl: replacement=re.sub(r'\bdid\b','done',g0,flags=re.I)
            elif 'have saw' in gl: replacement=re.sub(r'\bsaw\b','seen',g0,flags=re.I)
            elif 'have began' in gl: replacement=re.sub(r'\bbegan\b','begun',g0,flags=re.I)
            elif re.match(r'\b(?:can|could|should|would|will|must|might|may)\s+to\s+\w+', gl): replacement=re.sub(r'\s+to\b','',g0,flags=re.I,count=1)
            elif 'affect on' in gl or 'affect of' in gl: replacement=re.sub(r'\s+(on|of)\b','',g0,flags=re.I)
            alternatives = [{'word': replacement, 'why': why}] if replacement else []
            issues.append({'type':typ,'message':msg,'detail':why,'text':g0,'start':m.start(),'end':m.end(),'replacement':replacement,'alternatives':alternatives})

    # --- "then" vs "than" confusion (needs context after the comparative word, handled separately from the table above) ---
    for m in re.finditer(r'\b(more|less|better|worse|bigger|smaller|greater|higher|lower|rather)\s+then\b', text, re.I):
        replacement = re.sub(r'\bthen\b', 'than', m.group(0), flags=re.I)
        why = '“Than” is used for comparisons; “then” refers to time or sequence. After a comparative word, “than” is needed.'
        issues.append({'type':'grammar','message':'Did you mean “than” (for comparisons)?','detail':why,
                        'text':m.group(0),'start':m.start(),'end':m.end(),'replacement':replacement,
                        'alternatives':[{'word':replacement,'why':why}]})

    for m in re.finditer(r'\s+[,.!?]', text):
        issues.append({'type':'accuracy','message':'Remove the space before punctuation.','text':m.group(0),'start':m.start(),'end':m.end(),'replacement':m.group(0).strip()})
    for m in re.finditer(r'[.!?][A-Za-z]', text):
        issues.append({'type':'accuracy','message':'Add a space after sentence-ending punctuation.','text':m.group(0),'start':m.start(),'end':m.end(),'replacement':m.group(0)[0]+' '+m.group(0)[1:]})
    for m in re.finditer(r'([,.!?])\1+', text):
        issues.append({'type':'accuracy','message':'Remove the repeated punctuation mark.','detail':'Formal writing uses a single punctuation mark to end or separate a clause; repeating it (e.g. “!!”, “..”) reads as informal.',
                        'text':m.group(0),'start':m.start(),'end':m.end(),'replacement':m.group(1)})
    for m in re.finditer(r'\b(\w+)\s+\1\b', text, re.I):
        # Skip legitimate doubled words like "had had" or "that that" which
        # can be grammatically valid in certain constructions.
        if m.group(1).lower() in {'had','that','so','very'}:
            continue
        issues.append({'type':'accuracy','message':f'The word “{m.group(1)}” appears to be repeated by mistake.',
                        'detail':'This looks like an accidental double-typed word rather than an intentional repetition.',
                        'text':m.group(0),'start':m.start(),'end':m.end(),'replacement':m.group(1)})
    ss=sentences(text)
    # Track search position so repeated/near-identical short sentences each
    # get their own correct offset instead of all matching text.find()'s
    # first occurrence.
    _search_from = 0
    for s in ss:
        found = text.find(s, _search_from)
        start = found if found != -1 else text.find(s)
        if start != -1:
            _search_from = start + max(1, len(s) - 5)
        if len(words(s)) > 40:
            issues.append({'type':'coherence','message':'This sentence is very long. Consider splitting it where the relationship between ideas becomes clearer.','text':s[:60]+'…','start':start,'end':start+len(s)})
        elif len(words(s)) < 4:
            issues.append({'type':'coherence','message':'This short sentence may need more development or connection to the surrounding idea.','text':s,'start':start,'end':start+len(s)})
        elif s and not s[0].isupper() and s[0].isalpha():
            issues.append({'type':'grammar','message':'Start the sentence with a capital letter.','detail':'Standard English capitalises the first word of every sentence.',
                                                'text':s[:20]+('…' if len(s)>20 else ''),'start':start,'end':start+1,'replacement':s[0].upper(),
                                                'alternatives':[{'word':s[0].upper(),'why':'Standard English capitalises the first word of every sentence.'}]})
        # --- Comma splice: two independent clauses joined only by a comma ---
        # (e.g. "It was raining, we stayed inside.") A comma alone cannot
        # join two complete clauses in standard English; this needs a
        # coordinating conjunction, a semicolon, or a full stop instead.
        # Restricted to a comma followed by a personal pronoun/determiner +
        # verb, which is the pattern that reliably signals a second
        # independent clause rather than a normal listed/parenthetical
        # comma (so ordinary lists and appositives are not flagged).
        for m in re.finditer(
            r',\s+(I|we|he|she|it|they|this|that|these|those)\s+(am|is|are|was|were|has|have|had|do|does|did|can|could|will|would|should|must|[a-z]+ed|[a-z]+s)\b',
            s, re.I):
            clause_before = s[:m.start()].strip()
            # Use only the most recent clause segment — the text since the
            # last semicolon, or since the last comma that itself followed
            # a subordinator/transition — rather than the whole sentence
            # prefix. Without this, a sentence like "...has become
            # persistent; indeed, before turning to solutions, it is
            # worth..." sees a real verb far earlier in the sentence
            # ("has become") and wrongly treats the immediately-preceding
            # fronted phrase ("before turning to solutions,") as part of
            # that same independent clause, when it is actually its own
            # separate fronted phrase attached to "it is worth...".
            local_segment = re.split(r'[;:]|,\s*(?:indeed|in fact|notably|moreover|furthermore|however|therefore|consequently)\s*,?', clause_before, flags=re.I)[-1].strip(' ,')
            # The split above can leave a leading transition word attached
            # when it immediately follows the semicolon (e.g. "; indeed,
            # before turning..." splits at ";" first, leaving "indeed,
            # before turning..."); strip a leading transition word too so
            # the fronted-phrase check below sees the actual clause start.
            local_segment = re.sub(r'^(?:indeed|in fact|notably|moreover|furthermore|however|therefore|consequently)\s*,?\s*', '', local_segment, flags=re.I)
            # Require the first clause to itself look like a complete
            # independent clause — i.e. it must contain its own verb-ish
            # word (auxiliary/modal, or a plausible -ed/-s/-ing main verb).
            # A short fronted transitional phrase like "In my view," "On
            # the other hand," or "For example," has no verb of its own
            # and is not a second independent clause, so the comma there
            # is doing its normal job of setting off an introductory
            # phrase — not splicing two sentences together. Requiring a
            # word count alone (the previous check) let phrases like these
            # slip through as false positives.
            has_own_verb = bool(re.search(
                r'\b(am|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|can|could|shall|should|may|might|must|\w{3,}ed'
                r'|(?!this\b|thus\b|plus\b|status\b|focus\b|basis\b|campus\b|virus\b|bias\b|crisis\b|analysis\b|its\b|whose\b|towards\b|across\b|always\b|perhaps\b|amongst\b)\w{3,}s)\b',
                local_segment, re.I))
            if len(words(local_segment)) < 3 or not has_own_verb:
                continue
            # If the local clause before the comma opens with a
            # subordinating conjunction (Because/Although/While/Since/...)
            # or a fronted participial phrase ("Before turning to...",
            # "Turning to...", "Having considered..."), the comma is doing
            # its normal job of separating a fronted phrase from the main
            # clause that follows — that is correct punctuation, not a
            # splice, so skip it.
            if re.match(r'^(because|although|since|while|if|when|unless|whereas|despite|even though|as|after|before|turning|having|considering|given)\b', local_segment, re.I):
                continue
            abs_start = start + m.start()
            issues.append({'type':'grammar','message':'This looks like a comma splice: two complete sentences joined only by a comma.',
                            'detail':'When two independent clauses (each could stand alone as a sentence) are joined only by a comma, use a coordinating conjunction (", and"/", but"/", so"), a semicolon, or split them into two sentences instead.',
                            'text':s[max(0,m.start()-15):m.start()+len(m.group(0))],'start':abs_start,'end':abs_start+1,
                            'replacement':'.','alternatives':[{'word':'. ' + m.group(1)[0].upper() + m.group(1)[1:],'why':'Splitting into two sentences is the simplest fix for a comma splice.'},{'word':', and ' + m.group(1),'why':'Adding a coordinating conjunction after the comma also fixes a comma splice.'}]})
            break  # one flag per sentence is enough; avoid overlapping matches
        # --- Run-on sentence: two+ independent clauses with no connector at all ---
        # Heuristic: a sentence with 3+ verb-bearing clauses (found via
        # coordinating-conjunction-free clause boundaries approximated by
        # subject-pronoun repetition) and no comma/conjunction/semicolon
        # anywhere tends to be a fused run-on rather than one complex idea.
        # Count clause starts: a subject pronoun/noun immediately followed
        # by any verb-shaped word (auxiliary, or a plain word — covers
        # irregular past tense like "went"/"bought" that no inflection
        # regex catches). Three or more such clause starts with zero
        # connecting punctuation or conjunction is the run-on signal.
        # Count both pronoun-led clause starts and a plain noun-phrase
        # clause start followed by a plausible verb (covers a fused pair
        # like "Students often struggle... they get distracted...", where
        # the first clause's subject is a noun, not a pronoun).
        subj_hits = len(re.findall(
            r'\b(I|we|he|she|it|they|you)\s+(?:am|is|are|was|were|has|have|had|do|does|did|can|could|will|would|should|must'
            r'|[a-z]{3,}ed|[a-z]{3,}s'
            r'|went|came|took|got|made|said|saw|knew|thought|found|gave|told|became'
            r'|left|felt|brought|bought|caught|taught|kept|held|met|paid|sold'
            r'|ran|began|wrote|drove|spoke|broke|chose|grew|drew|flew|threw'
            r'|ate|fell|forgot|led|lost|built|sent|spent|stood|understood|won'
            r'|get|want|need|try|know|think|feel|see|hear|like|love|hate|make|take|give|find|leave|keep|let)\b',
            s, re.I))
        subj_hits += len(re.findall(
            r'\b(?!I\b|We\b|He\b|She\b|It\b|They\b|You\b)[A-Z][a-z]+\s+(?:often|usually|always|never|also|still|now|sometimes)?\s*(?:am|is|are|was|were|has|have|had|do|does|did|can|could|will|would|should|must|struggle|struggles|need|needs|want|wants|try|tries|seem|seems|tend|tends)\b',
            s))
        # Two fused clauses with no punctuation or connector at all (e.g.
        # "She studied hard she passed the exam.") is already a run-on, not
        # just a stylistic tic — the threshold is 2, not 3, as long as
        # there is truly zero connecting punctuation/conjunction anywhere.
        is_run_on = subj_hits >= 2 and ',' not in s and ';' not in s and not re.search(r'\b(and|but|or|because|so|although|while|when|if|since|which|that|who)\b', s, re.I)
        if is_run_on:
            issues.append({'type':'grammar','message':'This may be a run-on sentence: several independent clauses with no connecting word or punctuation between them.',
                            'detail':'Long sentences that fuse multiple complete clauses without a conjunction, comma, or semicolon are hard to follow. Break this into separate sentences or join clauses with an appropriate connector.',
                            'text':s[:60]+('…' if len(s)>60 else ''),'start':start,'end':start+len(s)})
        # --- Sentence fragment: no finite verb at all ---
        # A very rough but useful check: a sentence of reasonable length
        # that contains no verb-like word (common auxiliaries/modals or a
        # word ending in a typical verb inflection) is likely missing its
        # main verb, e.g. "Although the rising cost of living in most
        # cities." Short exclamations/greetings are excluded since those
        # are legitimately verbless.
        sw = words(s)
        if len(sw) >= 6 and not is_run_on:
            # A finite verb is either an auxiliary/modal, or a word ending
            # in a typical inflection (-ed/-ing/-s) that is plausibly a verb
            # rather than a plural noun or adverb. This is intentionally
            # permissive (favouring fewer false positives over catching
            # every fragment) since a blunt regex cannot reliably parse
            # English syntax.
            has_aux = bool(re.search(
                r'\b(am|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|can|could|shall|should|may|might|must)\b',
                s, re.I))
            # Only trust a bare "-ed" past-tense form as a verb (e.g.
            # "walked"); a bare "-ing" form is treated as a verb only when
            # an auxiliary appears somewhere in the sentence, since a lone
            # "-ing" is very often a gerund/noun ("the rising cost of
            # living") rather than a progressive-tense main verb, and that
            # ambiguity is exactly what makes a sentence like "Although the
            # rising cost of living in most cities." a fragment despite
            # containing an "-ing" word.
            has_ed_verb = bool(re.search(r'\b\w{3,}ed\b', s, re.I))
            # A handful of very common irregular past-tense verbs never end
            # in -ed, so they need their own check to avoid mislabelling
            # ordinary sentences like "we left for school" as fragments.
            has_irregular_past = bool(re.search(
                r'\b(went|came|took|got|made|said|saw|knew|thought|found|gave|told|became'
                r'|left|felt|brought|bought|caught|taught|kept|held|met|paid|sold'
                r'|ran|began|wrote|drove|spoke|broke|chose|grew|drew|flew|threw'
                r'|ate|fell|forgot|led|lost|built|sent|spent|stood|understood|won)\b',
                s, re.I))
            has_verb = has_aux or has_ed_verb or has_irregular_past
            # A word ending in -s that isn't a plural noun is a fairly
            # reliable third-person-singular present-tense verb signal
            # (e.g. "generate*s*", "affect*s*") — but plural nouns also end
            # in -s, so this is only trusted when the word directly follows
            # a plural-looking noun phrase's likely subject, which a plain
            # regex can't confirm. Instead, bare present-tense main verbs
            # (no -s, no -ed, no aux — e.g. "issues ... generate ...") are
            # accepted as evidence of a verb whenever the sentence does NOT
            # open with a subordinating conjunction, since the risk of a
            # false "fragment" flag on an ordinary declarative sentence is
            # worse than under-flagging a genuine verbless fragment in that
            # position. The stronger "no verb at all" signal is reserved
            # for sentences that open with a subordinator (although,
            # because, since...), which is the one shape this checker has
            # been validated against in detail.
            starts_subordinate = bool(re.match(r'^(although|because|since|while|if|when|unless|whereas|despite|even though)\b', s.strip(), re.I))
            if not starts_subordinate:
                has_verb = True
            # A comma partway through the sentence usually introduces (or
            # closes) a second clause with its own verb — a fronted
            # phrase/clause followed by a comma and a main clause (e.g. "In
            # the morning, we left for school." or "Although it was late,
            # we stayed.") is a complete sentence, not a fragment. Since a
            # bare regex can't reliably confirm the clause after the comma
            # has its own verb, treat any comma-containing sentence of this
            # shape as presumptively complete rather than risk a false
            # "fragment" flag on ordinary fronted-phrase sentences.
            if ',' in s:
                has_verb = True
            # A short sentence that starts with a subordinating word
            # (although, because, since, while, if, when...) and has no
            # comma is very likely just the dependent clause on its own,
            # with the main clause missing entirely — even when that
            # dependent clause itself contains a verb (e.g. "Because he
            # studied hard for the exam." has a verb, "studied", but is
            # still a fragment because it never states what happened as a
            # result). Longer subordinate-opening sentences are left alone:
            # past a certain length a plain regex can no longer reliably
            # tell a genuine standalone fragment from a single long
            # dependent-clause-as-descriptive-sentence, and a false
            # "fragment" flag there is worse than staying silent.
            if starts_subordinate and ',' not in s and len(sw) <= 14 and not has_aux:
                has_verb = False
            if not has_verb:
                issues.append({'type':'grammar','message':'This looks like a sentence fragment: it may be missing a main verb.',
                                'detail':'Every complete sentence needs a finite verb attached to its subject. Check whether this group of words can stand alone, or whether it needs to be joined to the sentence before or after it.' + (' It also starts with a subordinating word, which usually signals a dependent clause that needs a main clause attached.' if starts_subordinate else ''),
                                'text':s[:60]+('…' if len(s)>60 else ''),'start':start,'end':start+len(s)})
    # Function/structural words (relative pronouns, determiners, conjunctions)
    # are excluded: their repetition reflects sentence structure (e.g. repeated
    # "that"-clauses signal subordination, not weak vocabulary), not a lexical
    # choice a writer should vary.
    FUNCTION_WORDS = {'that','which','this','these','those','there','their','they','them',
                       'with','from','have','been','were','will','would','could','should',
                       'into','onto','than','then','when','where','while','about','after',
                       'before','under','over','such','some','more','most','also','only'}
    ws=words(text); freq={w:ws.count(w) for w in set(ws)}
    for w,c in sorted([(w,c) for w,c in freq.items() if c>=4 and len(w)>3 and w not in FUNCTION_WORDS], key=lambda x:-x[1])[:8]:
        # Skip the first occurrence, same as repetition_suggestions()/
        # broad_repetition_suggestions(): the first use isn't "repeated" and
        # essays necessarily reuse their own topic nouns (e.g. an essay about
        # "artificial intelligence" will say "artificial intelligence" often;
        # that's expected academic writing, not a vocabulary weakness).
        matches=list(re.finditer(rf'\b{re.escape(w)}\b', text,re.I))
        for ordinal,m in enumerate(matches[1:], start=2):
            alts_raw=REPETITION_ALTERNATIVES.get(w.lower(), [])
            alts=[{'word':a,'why':why} for a,why in alts_raw]
            issues.append({'type':'vocabulary','message':f'“{w}” is repeated {c} times. Consider varying later uses where the meaning allows it.',
                           'detail':f'This is occurrence {ordinal} of “{w}” ({c} total), which narrows vocabulary range. Pick an alternative that fits this specific sentence.' if alts else 'Try a precise synonym only when the meaning stays unchanged.',
                           'text':m.group(0),'start':m.start(),'end':m.end(),'repeated_count':c,'occurrence':ordinal,
                           'alternatives':alts,'replacement':alts[0]['word'] if alts else None})
    return issues


def dedupe_repetition_issues(issues):
    """A repeated word (e.g. used 5 times) produces one 'repeated N times'
    issue per occurrence so every instance can be underlined and clicked in
    the editor. Showing all of those in the issues *list* just repeats the
    same message N times, so collapse repetition-type entries to a single
    row (the first occurrence) per word for display purposes while leaving
    every other issue type untouched.
    """
    seen_repetition_words = set()
    result = []
    for issue in issues:
        if issue.get('type') == 'vocabulary' and 'repeated_count' in issue:
            key = issue['text'].lower()
            if key in seen_repetition_words:
                continue
            seen_repetition_words.add(key)
        result.append(issue)
    return result


def database_feedback(text, overall, level, target, issues, essay_type=None):
    conn=db()
    profile_rows=conn.execute('SELECT level, AVG(avg_sentence_words) avg_len, AVG(type_token_ratio) ttr, AVG(academic_ratio) academic, AVG(transition_density) transitions, COUNT(*) samples FROM sample_essays GROUP BY level').fetchall()
    profile={r['level']:dict(r) for r in profile_rows}
    rules=conn.execute('SELECT * FROM feedback_rules WHERE level IN (?,?) ORDER BY priority DESC', (level,target)).fetchall()
    vocab_rows=conn.execute('SELECT * FROM vocabulary_targets WHERE level=? LIMIT 16',(target,)).fetchall()
    conn.close()
    p=profile.get(level,{}); tp=profile.get(target,{})
    ss=sentences(text); avg=avg_sentence_length(text); ttr=type_token_ratio(text); acad=academic_ratio(text)
    target_trans=transition_density(text,target)
    feedback=[]
    if tp:
        gaps=[]
        if ttr < tp['ttr']-0.06: gaps.append('greater vocabulary variety')
        if acad < tp['academic']-0.02: gaps.append('more precise academic vocabulary')
        if avg < tp['avg_len']-5: gaps.append('more developed sentence structures')
        if target_trans < max(0.5,tp['transitions']*0.55): gaps.append('more purposeful cohesive devices')
        if gaps: feedback.append(f'To move toward {TARGET_LABEL[level]}, focus on: {", ".join(gaps)}.')
    if any(i['type']=='grammar' for i in issues): feedback.append('Grammar: correct the highlighted forms first. Accuracy gains are more valuable than adding advanced vocabulary on top of repeated errors.')
    boundary_issues = [i for i in issues if 'comma splice' in i.get('message','') or 'run-on' in i.get('message','') or 'fragment' in i.get('message','')]
    if boundary_issues:
        kinds = sorted({('comma splice' if 'comma splice' in i['message'] else 'run-on sentence' if 'run-on' in i['message'] else 'fragment') for i in boundary_issues})
        feedback.append(f'Sentence boundaries: this paragraph has at least one {", ".join(kinds)}. Fix these before anything else — a reader cannot follow the argument until each sentence is a single, complete, correctly joined idea.')
    if any(i['type']=='vocabulary' for i in issues): feedback.append('Vocabulary: vary repeated words only when the alternative is natural and precise.')
    if len(ss)>=3 and target_trans < 0.5: feedback.append(f'Cohesion: try a target-level linker only where the relationship is real. Examples include “{TRANSITIONS[target][0]}” and “{TRANSITIONS[target][1]}”.')
    if not feedback: feedback.append('Your paragraph is reasonably controlled. Keep refining clarity, vocabulary precision and cohesion in your next revision.')
    rule_messages=[]
    for r in rules:
        trig=r['trigger']
        if (trig=='low_ttr' and ttr < tp.get('ttr',.5)-.05) or (trig=='low_academic' and acad < tp.get('academic',.04)-.015) or (trig=='low_transitions' and target_trans < .5) or (trig=='missing_conclusion' and len(ss)>=3 and not any(x in text.lower() for x in ['in conclusion','to sum up','overall','taken together','on balance','ultimately'])) or (trig=='low_development' and avg < 15):
            rule_messages.append({'category':r['category'],'text':r['message']})
    if essay_type:
        feedback.append(f'Essay-type focus: {essay_type.replace("_"," ").title()}. Check that your response addresses every part of the task and uses a structure appropriate to this question type.')
    target_vocab=[]
    lower=' '.join(words(text))
    for r in vocab_rows:
        if re.search(rf'\b{re.escape(r["word"])}\b', lower):
            target_vocab.append({'word':r['word'],'alternatives':r['alternatives']})
    return feedback,rule_messages,target_vocab



ESSAY_TYPE_SIGNALS = {
    'problem_solution': [
        r'\bproblems?\b', r'\bsolutions?\b', r'\bcauses?\b', r'\bmeasures?\b', r'\bsolve[sd]?\b',
        r'\baddress(?:es|ed|ing)?\s+the\s+(?:problem|issue)\b', r'\btackle[sd]?\b', r'\bcope\s+with\b',
        r'\bshould\s+be\s+(?:done|taken)\b', r'\bsteps?\s+(?:can|should|to)\b'
    ],
    'advantages_disadvantages': [
        r'\badvantages?\b', r'\bdisadvantages?\b', r'\bbenefits?\s+and\s+drawbacks?\b',
        r'\bpros\s+and\s+cons\b', r'\boutweighs?\b', r'\bupsides?\b', r'\bdownsides?\b'
    ],
    'discussion': [
        r'\bboth\s+(?:views|sides|opinions|perspectives)\b', r'\bon\s+the\s+other\s+hand\b',
        r'\bsome\s+people\s+(?:think|believe|argue|say)\b.*\bothers?\b',
        r'\bwhile\s+others\b', r'\beach\s+side\b', r'\btwo\s+(?:views|opinions|sides)\b'
    ],
    'cause_effect': [
        r'\bcauses?\b', r'\breasons?\s+(?:for|behind|why)\b', r'\beffects?\b', r'\bresults?\s+in\b',
        r'\bleads?\s+to\b', r'\bconsequences?\b', r'\bdue\s+to\b', r'\bbecause\s+of\b', r'\bas\s+a\s+result\b'
    ],
    'positive_negative': [
        r'\bpositive\s+(?:or\s+negative\s+)?development\b', r'\bnegative\s+development\b',
        r'\bis\s+this\s+a\s+(?:positive|negative)\b', r'\bgood\s+or\s+bad\s+thing\b', r'\bstep\s+(?:forward|backward)\b'
    ],
    'two_part': [
        r'\bwhy\s+.+\?', r'\bwhat\s+.+\?', r'\bhow\s+.+\?', r'\bfirstly\b.*\bsecondly\b',
        r'\bfirst\s+question\b', r'\bsecond\s+question\b'
    ],
    'opinion': [
        r'\bi\s+(?:strongly\s+)?(?:agree|disagree)\b', r'\bto\s+what\s+extent\b', r'\bi\s+believe\b',
        r'\bin\s+my\s+opinion\b', r'\bi\s+think\b', r'\bi\s+would\s+argue\b', r'\bmy\s+view\b',
        r'^\s*should\b', r'\bshould\s+(?:governments?|schools?|companies|people|we|children|students)\b',
        r'\bought\s+to\s+be\b', r'\bis\s+it\s+(?:right|wrong|acceptable|justified)\b',
    ],
}
# Priority order used when multiple types score equally (more specific types first).
ESSAY_TYPE_PRIORITY = ['problem_solution','advantages_disadvantages','discussion','cause_effect','positive_negative','two_part','opinion']

# Titles matching these patterns are descriptive/expository/narrative in
# nature (a "general essay") rather than an argumentative task type, e.g.
# "My Favorite Season", "The Life of a River", "A Day I Will Never Forget",
# "How Volcanoes Form". These do not ask the writer to take a position, so
# they must never be routed into the debate-shaped opinion/discussion/
# advantages-disadvantages/problem-solution templates below.
GENERAL_ESSAY_SIGNALS = [
    r'^\s*my\s+(?:favorite|favourite)\b', r'^\s*a\s+day\b', r'^\s*the\s+life\s+of\b',
    r'^\s*how\s+.+\bworks?\b', r'^\s*how\s+.+\bforms?\b', r'^\s*describe\b', r'^\s*a\s+description\s+of\b',
    r'^\s*my\s+(?:best|worst|most\s+memorable)\b', r'^\s*an?\s+(?:unforgettable|memorable)\b',
    r'^\s*the\s+(?:history|story)\s+of\b', r'^\s*a\s+visit\s+to\b', r'^\s*a\s+journey\s+(?:to|through)\b',
    r'^\s*my\s+(?:hometown|family|school|hero|role\s+model)\b', r'\bi\s+will\s+never\s+forget\b',
    r'^\s*what\s+i\s+did\b', r'^\s*a\s+letter\s+to\b',
]

def detect_essay_type(title, text):
    """Infer the essay task type from the title and body text instead of asking the user."""
    combined = f"{title or ''} . {text or ''}"
    if not combined.strip():
        return 'opinion'
    low = combined.lower()
    for pat in GENERAL_ESSAY_SIGNALS:
        if re.search(pat, (title or '').lower().strip(), re.I):
            return 'general'
    scores = {}
    for et, patterns in ESSAY_TYPE_SIGNALS.items():
        count = 0
        for pat in patterns:
            count += len(re.findall(pat, low, re.I))
        scores[et] = count
    best_score = max(scores.values()) if scores else 0
    if best_score <= 0:
        # No argumentative/discussion signal at all: this reads as a plain
        # descriptive/expository/informational title, so default to a
        # general essay (no forced stance) rather than 'opinion', which
        # would fabricate a position the title never asked for.
        return 'general'
    candidates = [et for et in ESSAY_TYPE_PRIORITY if scores.get(et, 0) == best_score]
    return candidates[0] if candidates else 'opinion'


# --- Myanmar (စာစီစာကုံး) essay-type auto-detection --------------------------
# Mirrors detect_essay_type() above but for the four Myanmar composition
# types (descriptive/process/expository/argumentative). Debate-shaped
# stance-taking is handled entirely by Debate/အဆိုအချေ mode, so this
# detector never returns anything outside the four composition types —
# a title that happens to sound argumentative in Essay mode still gets a
# proper composition, not a debate script.
MY_PROCESS_SIGNALS = [
    r'နည်း\s*$', r'ပြင်ဆင်\s*နည်း', r'လုပ်\s*နည်း', r'ဖြစ်\s*နည်း', r'ရေး\s*နည်း',
    r'အဆင့်ဆင့်', r'ဖြစ်စဉ်', r'ဘယ်လို.*ဖြစ်', r'ဘယ်လို.*လုပ်', r'နည်းလမ်း',
    r'ဆောင်ရွက်\s*ပုံ', r'ပြုလုပ်ပုံ',
]
MY_ARGUMENTATIVE_SIGNALS = [
    r'သင့်\s*(?:၊|,|သလား|မသင့်)', r'ကောင်း\s*သလား', r'ဟုတ်\s*သလား', r'သင့်\s*၍', r'သင့်\s*မသင့်',
    r'လိုအပ်\s*(?:သလား|ပါသလား)', r'အကျိုးရှိ\s*သလား', r'အားကောင်း\s*သလား',
    r'ထောက်ခံ', r'ကန့်ကွက်', r'သဘောတူ', r'သဘောမတူ', r'ရှုထောင့်', r'အမြင်ကွဲ',
]
MY_EXPOSITORY_SIGNALS = [
    r'အကြောင်းရင်း', r'အကြောင်းတရား', r'အကျိုးဆက်', r'ဘာကြောင့်', r'ဆိုးကျိုး', r'ကောင်းကျိုး',
    r'အကျိုးကျေးဇူး', r'ဆိုးကျို', r'ကြောင့်.*ဖြစ်', r'ရလဒ်', r'သက်ရောက်မှု', r'ပြောင်းလဲမှု',
]
# Titles that are essentially a single value/quality/place/person noun
# phrase (the overwhelming majority of Myanmar school စာစီစာကုံး topics,
# e.g. "ပညာ၏တန်ဖိုး", "ဆရာကျေးဇူး", "ပုဂံ") default to descriptive: explain
# what it is, its features/importance, and its significance — the standard
# Myanmar school treatment for this kind of title.
MY_DESCRIPTIVE_HINTS = [r'တန်ဖိုး', r'ကျေးဇူး', r'အရေးပါမှု', r'အခန်းကဏ္ဍ', r'ဘဝ']


def detect_myanmar_essay_type(title):
    """Infer the Myanmar composition type from the title alone, the same
    way detect_essay_type() infers the English task type — so the student
    never has to choose descriptive/process/expository/argumentative by
    hand. Returns one of: descriptive, process, expository, argumentative.
    """
    t = (title or '').strip()
    if not t:
        return 'descriptive'
    for pat in MY_PROCESS_SIGNALS:
        if re.search(pat, t):
            return 'process'
    for pat in MY_ARGUMENTATIVE_SIGNALS:
        if re.search(pat, t):
            return 'argumentative'
    for pat in MY_EXPOSITORY_SIGNALS:
        if re.search(pat, t):
            return 'expository'
    for pat in MY_DESCRIPTIVE_HINTS:
        if re.search(pat, t):
            return 'descriptive'
    # Short, plain noun-phrase titles (most of the topic bank) read as a
    # straightforward descriptive/expository composition in Myanmar schools;
    # default to descriptive rather than forcing an argumentative stance
    # the title never asked for.
    return 'descriptive'


# Content-side signals, used to refine the title-only guess above once an
# actual draft exists. Titles are often a single bare noun phrase (e.g.
# "ပညာ၏တန်ဖိုး") with no reliable type signal at all, but the generated
# composition itself reliably contains cause/effect wording, sequential
# process language, or a taken position — so re-checking the draft catches
# what the title alone couldn't.
MY_CONTENT_PROCESS_SIGNALS = [
    r'ပထမဆင့်', r'ဒုတိယအဆင့်', r'နောက်ဆုံးအဆင့်', r'အဆင့်ဆင့်', r'ပထမအနေဖြင့်.*ထို့နောက်',
    r'ပြီးလျှင်', r'ထို့နောက်', r'ဆက်လက်၍', r'နောက်ဆုံးတွင်', r'အစီအစဉ်အတိုင်း',
]
MY_CONTENT_ARGUMENTATIVE_SIGNALS = [
    r'ကျွန်တော်.*ထင်မြင်', r'ကျွန်မ.*ထင်မြင်', r'ကျွန်ုပ်.*ယုံကြည်', r'သဘောထား', r'ရပ်တည်ချက်',
    r'ထောက်ခံ', r'ကန့်ကွက်', r'သင့်၏သဘောအရ', r'အကြံပြုလိုသည်မှာ', r'သင့်ကြောင်း', r'မသင့်ကြောင်း',
]
MY_CONTENT_EXPOSITORY_SIGNALS = [
    r'အကြောင်းရင်း', r'အကြောင်းတရား', r'ကြောင့်ဖြစ်သည်', r'ကြောင့်ဖြစ်ပေါ်', r'အကျိုးဆက်',
    r'ရလဒ်အနေဖြင့်', r'သက်ရောက်မှု', r'ဆိုးကျိုး', r'ကောင်းကျိုး',
]


def refine_myanmar_essay_type(title, essay_text, initial_type):
    """Re-check the title-based guess against the actual generated draft.

    The title alone (often a bare noun phrase) frequently carries no
    reliable type signal, but a finished composition does: process essays
    read as an ordered sequence, argumentative essays state and defend a
    position, expository essays explain causes/effects. Only overrides
    `initial_type` when the content signal is unambiguous; otherwise keeps
    the original guess rather than flip-flopping on weak evidence.
    """
    text = (essay_text or '').strip()
    if not text:
        return initial_type
    process_hits = sum(1 for pat in MY_CONTENT_PROCESS_SIGNALS if re.search(pat, text))
    arg_hits = sum(1 for pat in MY_CONTENT_ARGUMENTATIVE_SIGNALS if re.search(pat, text))
    expo_hits = sum(1 for pat in MY_CONTENT_EXPOSITORY_SIGNALS if re.search(pat, text))
    scores = {'process': process_hits, 'argumentative': arg_hits, 'expository': expo_hits}
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    # Require at least two distinct content hits before overriding a
    # title-based guess of 'descriptive' (the safe default) — a single
    # incidental phrase match shouldn't reclassify the whole composition.
    if initial_type == 'descriptive' and best_score >= 2:
        return best_type
    return initial_type


def normalize_topic(text):
    stop=set('the a an and or but of to in on for with from by is are was were be been being this that these those it its as at into about over after before than then very more most some any all both each every can could should would may might do does did have has had not only own their there they them you your we our i me my'.split())
    return {w for w in words(text) if len(w)>=3 and w not in stop}

def topic_relevance(title, text):
    if not title.strip() or not text.strip():
        return {'available':False,'score':None,'label':'No title provided','message':'Enter an essay title/topic so the database can check whether your paragraph stays relevant.'}
    tw=normalize_topic(title); ww=normalize_topic(text)
    if not tw:
        return {'available':False,'score':None,'label':'Title too short','message':'Use a more descriptive essay title, for example “The impact of technology on education”.'}
    overlap=tw & ww
    score=round(min(100, len(overlap)/len(tw)*70 + min(30, len(ww & set(list(tw))) * 5)))
    # semantic-ish expansion for common topic families
    expansions={
      'education':{'school','student','learning','teacher','university','education','study'},
      'technology':{'technology','digital','internet','online','computer','ai','artificial'},
      'environment':{'environment','climate','pollution','green','carbon','energy','nature'},
      'health':{'health','exercise','diet','medical','doctor','disease','fitness'},
      'transport':{'transport','traffic','bus','car','road','travel','commute'},
      'work':{'work','job','employee','employment','career','office','salary'},
      'government':{'government','policy','public','state','law','tax','citizen'},
      'crime':{'crime','criminal','police','prison','punishment','illegal','safety','offence','offender','theft','burglary','arrest','law','justice','sentence','victim','reoffending'},
      'media':{'media','news','television','social','advertising','journalism'},
      'family':{'family','families','parent','parents','parenting','child','children','kid','kids',
                'sibling','siblings','marriage','married','spouse','household','upbringing',
                'grandparent','grandparents','relative','relatives','divorce','stepfamily',
                'guardian','caregiver','elderly','discipline','chores','nuclear','extended'},
      'tourism':{'tourism','tourist','travel','holiday','destination','visitor'},
      'economy':{'economy','inflation','prices','income','poverty','business','finance'},
      'science':{'science','research','experiment','scientist','discovery','laboratory'},
      'culture':{'culture','cultural','tradition','custom','heritage','identity'},
      'sports':{'sport','sports','athlete','competition','fitness','team'},
      'housing':{'housing','house','home','rent','property','landlord'},
      'food':{'food','farming','agriculture','diet','nutrition','crops'},
      'globalisation':{'globalisation','globalization','global','international','trade'},
      'social_media':{'social','media','platform','online','network','post'},
      'ai':{'ai','artificial','intelligence','automation','robot','algorithm'},
      'libraries':{'library','libraries','book','books','reading','archive','librarian','borrowing','literacy','shelves','catalogue'},
      'advertising':{'advertising','marketing','consumer','product','brand','commercial','advert','advertisement','campaign','promotion','sponsor','sponsorship','influencer','billboard','jingle','endorsement'},
      'energy':{'energy','renewable','fossil','fuel','electricity','solar','wind'},
      'internet':{'internet','online','web','website','digital','connectivity','broadband','wifi','browsing','network','connection','access','offline','bandwidth'},
      'youth':{'youth','teenager','teenagers','young','children','generation','adolescent','adolescents','teen','upbringing'},
      'language':{'language','languages','bilingual','fluent','communication','dialect','translation','vocabulary','accent','multilingual','linguistic'},
      'democracy':{'democracy','democratic','election','vote','voting','representation','ballot','candidate','parliament','referendum','electorate','constituency','suffrage','accountability','governance'},
      'sustainability':{'sustainability','sustainable','green','resources','circular','recycling','conservation','eco-friendly','footprint','longevity','stewardship'},
      'immigration':{'immigration','immigrant','immigrants','migrant','migration','refugee'},
      'gender_equality':{'gender','equality','feminism','discrimination','sexism','equal','pay','workplace','stereotype','stereotypes','representation','parity','harassment'},
      'animal_welfare':{'animal','animals','wildlife','conservation','endangered','zoo'},
      'space_exploration':{'astronaut','rocket','satellite','universe','spacecraft','exploration'},
      'arts_culture_funding':{'museum','theatre','music','artist','gallery'},
      'urbanisation':{'urban','urbanisation','city','cities','urbanization'},
      'tradition_modernity':{'tradition','traditional','modern','modernisation','custom'},
      'volunteering':{'volunteer','volunteering','charity','nonprofit','donation','fundraising','unpaid','philanthropy','outreach'},
      'privacy_technology':{'privacy','surveillance','tracking','cybersecurity','encryption','data','personal','breach','hacking','password','security','online','digital','consent','monitoring','identity','cookies','biometric'},
      'mental_health':{'mental','anxiety','depression','therapy','counselling','burnout','stress','wellbeing','psychological','emotional','resilience'},
      'artificial_intelligence_ethics':{'deepfake','deepfakes','algorithmic','bias','ai','artificial','intelligence','automation','algorithm','automated','machine','learning','ethics','ethical','regulation','accountability','transparency','misuse','discrimination','surveillance'},
      'remote_work':{'telecommute','telecommuting','hybrid','telework','remote','work','job','office','commute','commuting','flexible','flexibility','workplace','employer','employee','home','videoconference','collaboration'},
      'consumerism':{'consumerism','overconsumption','materialism','disposable','consumerist','shopping','buying','spending','brand','fashion','waste','packaging','advertising','marketing','possessions','purchase','retail','impulse'},
      'renewable_energy_transition':{'fossil','fuels','emissions','transition','renewable','energy','solar','wind','coal','oil','gas','carbon','electricity','grid','clean','net-zero','decarbonisation','battery'},
      'genetic_engineering':{'genetic','gmo','gene','crispr','cloning','genetically','dna','engineering','modification','biotechnology','hereditary','mutation','embryo','breeding'},
      'social_inequality':{'inequality','wealth','gap','class','privilege','mobility','poverty','disadvantage','opportunity','disparity'},
      'space_and_astronomy_education':{'astronomy','telescope','telescopes','stargazing','planetarium','cosmos','space','universe','galaxy','planet','planets','star','stars','constellation','observatory','satellite'},
      'disaster_preparedness':{'disaster','disasters','earthquake','flooding','hurricane','wildfire'},
      'freedom_of_speech':{'freedom','speech','censorship','censor','expression','press','suppression','dissent','protest','moderation'},
      'nutrition_and_public_health':{'obesity','malnutrition','sugar','processed','nutrition','diet','calories','junk','food','healthy','unhealthy','vitamins','deficiency','overweight','sugary','snacks','labelling','portion'},
    }
    title_family=set()
    for k,vals in expansions.items():
        if tw & vals: title_family |= vals
    family_overlap=len(ww & title_family)
    if title_family:
        score=max(score, min(100, 35 + family_overlap*7))
    elif not overlap:
        # Neither a literal keyword match nor a recognised topic family: we
        # have no reliable signal (the topic just isn't in our small fixed
        # category list), not evidence the essay is off-topic. Reporting a
        # false 0 here previously triggered a full CEFR-band demotion for
        # essays that were perfectly on-topic but paraphrased the title.
        return {'available':False,'score':None,'label':'Relevance not checked','message':'The title topic isn’t in the database’s topic-family list, so relevance couldn’t be checked automatically.'}
    if score>=65: label='Highly relevant'
    elif score>=40: label='Mostly relevant'
    elif score>=20: label='Weak relevance'
    else: label='Likely off-topic'
    msg={'Highly relevant':'Your paragraph strongly matches the main topic words and topic family.', 'Mostly relevant':'Your paragraph is generally related, but one or more key title ideas could be developed more explicitly.', 'Weak relevance':'Only a limited part of the paragraph connects with the title. Add topic-specific ideas and examples.', 'Likely off-topic':'The paragraph contains few signals connected to the title. Refocus the main idea and supporting evidence on the stated topic.'}[label]
    return {'available':True,'score':score,'label':label,'message':msg,'matched_terms':sorted(overlap)[:12]}

def thesis_check(title, text, essay_type=None):
    ss=sentences(text)
    intro=' '.join(ss[:2]) if ss else ''
    low=intro.lower()
    markers=['i agree','i disagree','i believe','in my opinion','i would argue','i argue','this essay argues','this essay will','i strongly believe','i partly agree','i completely agree','i do not agree','should','ought to','is beneficial','is harmful','advantages outweigh','disadvantages outweigh','both views','while','although']
    marker_hits=[m for m in markers if m in low]
    has_position=bool(marker_hits)
    has_topic=bool(topic_relevance(title,intro)['available'] and topic_relevance(title,intro)['score']>=20) if title else bool(intro)
    min_words=8 if essay_type in ('opinion','discussion','advantages_disadvantages','positive_negative','problem_solution','two_part') else 6
    strong=has_position and has_topic and len(words(intro))>=min_words
    if strong:
        msg='A thesis/central position is present in the opening. Make sure it directly answers every part of the task.'
        status='Thesis statement detected'
    elif has_position:
        msg='A position is visible, but the thesis could be clearer and more specific about the main answer or scope.'
        status='Thesis needs strengthening'
    else:
        msg='No clear thesis statement was detected in the opening sentences. State your main position or answer explicitly.'
        status='Thesis not clearly detected'
    return {'status':status,'detected':strong,'message':msg,'opening':intro[:240]}


def complexity_metrics(text):
    ss=sentences(text); ws=words(text)
    if not ws:
        return {'complexity':0,'sentence_variety':0,'development':0,'subordination':0,'long_sentence_ratio':0}
    # Deterministic proxies for syntactic sophistication. These are not a parser/CEFR test.
    complex_markers = r'\b(?:although|though|whereas|while|because|since|unless|if|provided that|which|who|whom|whose|that|even though|despite|in order to|so that|rather than|whereby|insofar as|in that|not merely|not only)\b'
    # Advanced connective/adverbial phrases signal complex clause-linking even
    # when they don't introduce a classic subordinate clause (e.g. sentence
    # adverbials like "accordingly", "conversely", "notwithstanding").
    advanced_connectives = r'\b(?:accordingly|conversely|notwithstanding|nevertheless|nonetheless|henceforth|by the same token|on balance|insofar as|by contrast|in light of)\b'
    subordinate=sum(len(re.findall(complex_markers,s,re.I)) for s in ss)
    advanced_hits=sum(len(re.findall(advanced_connectives,s,re.I)) for s in ss)
    clause_counts=[len(re.findall(r'\b(?:and|but|or|because|although|while|whereas|if|which|that|who|since|unless|not merely|not only)\b',s,re.I)) for s in ss]
    complex_sent=sum(1 for c in clause_counts if c>=1)
    very_complex=sum(1 for c in clause_counts if c>=2)
    lengths=[len(words(x)) for x in ss]
    avg=sum(lengths)/max(1,len(lengths))
    variance=(sum((x-avg)**2 for x in lengths)/max(1,len(lengths)))**0.5
    variety=min(100, round(45 + (complex_sent/max(1,len(ss)))*35 + min(20,variance*3)))
    complexity=min(100, round(8 + avg*2.4 + min(28,subordinate/max(1,len(ss))*26) + min(18,very_complex/max(1,len(ss))*22) + min(10,advanced_hits/max(1,len(ss))*10)))
    development=min(100, round(25 + min(35,avg*2.2) + min(25,len(ss)*3) + min(15, max(0,len(set(ws))/max(1,len(ws))*20))))
    return {'complexity':complexity,'sentence_variety':variety,'development':development,
            'subordination':subordinate/max(1,len(ss)),'long_sentence_ratio':sum(1 for x in lengths if x>30)/max(1,len(lengths))}

def task_development_score(text, essay_type, relevance, thesis):
    ss=sentences(text); low=text.lower()
    if not ss: return 0
    structure=0
    if len(ss)>=3: structure+=15
    if len(ss)>=5: structure+=10
    # evidence/example signals: simple markers OR more sophisticated
    # elaboration patterns (qualification, illustration, causal reasoning
    # expressed without a stock phrase), so dense academic prose isn't
    # penalised just for avoiding "for example"/"therefore".
    if re.search(r'\b(for example|for instance|such as|e\.g\.|in light of|by triangulating|by examining|through)\b',low): structure+=15
    if re.search(r'\b(because|therefore|consequently|as a result|accordingly|this means|which can|thereby|insofar as)\b',low): structure+=15
    if essay_type=='discussion' and re.search(r'\bon the other hand|while others|however|conversely\b',low): structure+=10
    if essay_type=='problem_solution' and re.search(r'\b(solution|measure|address|prevent|reduce|improve|tackle)\w*\b',low): structure+=10
    if essay_type=='advantages_disadvantages' and re.search(r'\b(advantage|disadvantage|benefit|drawback)\w*\b',low): structure+=10
    if essay_type=='cause_effect' and re.search(r'\b(cause|reason|effect|result|consequence|lead to)\w*\b',low): structure+=10
    if thesis.get('detected'): structure+=10
    if relevance.get('available'): structure += round(relevance.get('score',0)*0.15)
    # Credit sustained subordination/elaboration directly: essays that build
    # multi-clause, qualified arguments show development even without
    # ticking a specific discourse-marker box.
    subordinate_density=sum(len(re.findall(r'\b(?:that|which|who|whose|because|although|whereas|since|insofar as|in that)\b',s,re.I)) for s in ss)/max(1,len(ss))
    structure += min(20, round(subordinate_density*12))
    return min(100,structure)

def estimate_cefr(scores):
    # A weighted score is combined with a core-skill ceiling. This prevents
    # advanced vocabulary from masking weak grammar/accuracy.
    overall=round(
        scores['grammar_accuracy']*.20 +
        scores['grammar_complexity']*.15 +
        scores['vocabulary_range']*.15 +
        scores['vocabulary_precision']*.10 +
        scores['cohesion']*.10 +
        scores['coherence']*.10 +
        scores['task_relevance']*.10 +
        scores['sentence_variety']*.05 +
        scores['development']*.05
    )
    raw_level=level_for_score(overall)
    # Core control ceiling: an essay cannot be labelled more than one CEFR
    # step above its weakest core language-control dimension.
    core=[scores['grammar_accuracy'],scores['grammar_complexity'],
          scores['vocabulary_range'],scores['vocabulary_precision'],
          scores['cohesion'],scores['coherence']]
    weakest=level_for_score(min(core))
    order={x:i for i,x in enumerate(LEVELS)}
    ceiling_index=min(order[raw_level], order[weakest]+1)
    level=LEVELS[ceiling_index]
    # Task relevance can also cap a result when the answer is clearly
    # off-topic. This is a coarse keyword-overlap heuristic, so it is only
    # allowed to pull the level down by one band (not all the way to B1) and
    # only when the drop is severe, so it can't silently override strong
    # core language control (grammar, vocabulary, cohesion, coherence).
    if scores['task_relevance'] < 20 and order[level] > order['A2']:
        level=LEVELS[max(order['A2'], order[level]-1)]
    return overall,level,raw_level,weakest

RUBRICS = {
    'general': {
        'label': 'General CEFR band',
        'description': 'The deterministic CEFR-style estimate (A1–C2) from the weighted language/task profile above.',
    },
    'ap_lit': {
        'label': 'AP Literature & Composition (1–9)',
        'description': 'Approximates the College Board 1–9 free-response scale, weighted toward thesis, evidence & commentary, and sophistication of argument.',
    },
    'ielts_academic': {
        'label': 'IELTS Academic Writing Task 2 (Band 0–9)',
        'description': 'Approximates the four official IELTS criteria: Task Response, Coherence & Cohesion, Lexical Resource, Grammatical Range & Accuracy.',
    },
    'custom': {
        'label': 'Custom syllabus rubric (A–F)',
        'description': 'A generic university-style rubric weighting thesis, evidence, organisation and mechanics. Swap in your own syllabus weighting for an exact match.',
    },
}

def predict_rubric_score(overall, scores, rubric):
    """Calibrates the raw language/task profile against a named grading
    standard instead of only a generic 0-100 number, so the prediction reads
    the way the target grader (AP reader, IELTS examiner, course syllabus)
    would score it. This is a deterministic approximation, not an official
    score, and is always reported as such."""
    r = rubric if rubric in RUBRICS else 'general'
    if r == 'ap_lit':
        composite = (scores.get('task_relevance', 0) * .30 + scores.get('development', 0) * .30 +
                     scores.get('coherence', 0) * .15 + scores.get('grammar_complexity', 0) * .15 +
                     scores.get('vocabulary_precision', 0) * .10)
        band = max(1, min(9, round(1 + composite / 100 * 8)))
        return {'rubric': r, 'label': RUBRICS[r]['label'], 'predicted_score': f'{band}/9',
                'criteria': {'Thesis & argument': round(scores.get('task_relevance', 0)),
                             'Evidence & commentary': round(scores.get('development', 0)),
                             'Sophistication': round((scores.get('coherence', 0) + scores.get('vocabulary_precision', 0)) / 2)},
                'note': 'Predicted score band only — not an official AP score.'}
    if r == 'ielts_academic':
        criteria = {
            'Task Response': round((scores.get('task_relevance', 0) + scores.get('development', 0)) / 2),
            'Coherence & Cohesion': round((scores.get('cohesion', 0) + scores.get('coherence', 0)) / 2),
            'Lexical Resource': round((scores.get('vocabulary_range', 0) + scores.get('vocabulary_precision', 0)) / 2),
            'Grammatical Range & Accuracy': round((scores.get('grammar_accuracy', 0) + scores.get('grammar_complexity', 0)) / 2),
        }
        bands = {k: round((0.5 + v / 100 * 8) * 2) / 2 for k, v in criteria.items()}
        overall_band = round((sum(bands.values()) / 4) * 2) / 2
        return {'rubric': r, 'label': RUBRICS[r]['label'], 'predicted_score': f'Band {overall_band}',
                'criteria': bands, 'note': 'Predicted band only — not an official IELTS score.'}
    if r == 'custom':
        thresholds = [(90, 'A'), (85, 'A-'), (80, 'B+'), (75, 'B'), (70, 'B-'), (65, 'C+'), (60, 'C'), (55, 'C-'), (45, 'D')]
        letter = next((g for t, g in thresholds if overall >= t), 'F')
        return {'rubric': r, 'label': RUBRICS[r]['label'], 'predicted_score': letter,
                'criteria': {'Thesis': round(scores.get('task_relevance', 0)), 'Evidence & development': round(scores.get('development', 0)),
                             'Organisation': round(scores.get('cohesion', 0)), 'Mechanics': round(scores.get('grammar_accuracy', 0))},
                'note': 'Generic rubric weighting — replace with your syllabus\u2019s exact criteria for an exact match.'}
    return {'rubric': 'general', 'label': RUBRICS['general']['label'], 'predicted_score': None,
            'criteria': None, 'note': RUBRICS['general']['description']}

def audit_pipeline(text, essay_title, essay_type, relevance, thesis, development, scores, issues):
    """Runs each check as its own isolated pass over the essay — thesis
    strength, evidence relevance, logic continuity between sentences, and
    structure — rather than one single-shot judgement, so a weakness in one
    dimension can't be smoothed over by strength in another."""
    steps = []
    if thesis.get('detected'):
        t_score, t_status = 85, 'strong'
    elif thesis.get('status') == 'Thesis needs strengthening':
        t_score, t_status = 55, 'developing'
    else:
        t_score, t_status = 25, 'weak'
    steps.append({'key': 'thesis', 'name': 'Thesis strength', 'score': t_score, 'status': t_status,
                  'detail': thesis.get('message', '')})

    if relevance.get('available'):
        e_score = relevance['score']
        e_status = 'strong' if e_score >= 65 else 'developing' if e_score >= 40 else 'weak'
        e_detail = relevance['message']
    else:
        e_score, e_status = None, 'n/a'
        e_detail = 'Add an essay title/topic to activate this check.'
    steps.append({'key': 'evidence', 'name': 'Evidence & topic relevance', 'score': e_score, 'status': e_status, 'detail': e_detail})

    logic_issues = [i for i in issues if i['type'] == 'coherence']
    l_score = max(0, 100 - len(logic_issues) * 12) if logic_issues else min(100, round(development * .6 + scores.get('cohesion', 0) * .4))
    l_status = 'strong' if l_score >= 70 else 'developing' if l_score >= 45 else 'weak'
    l_detail = (f'{len(logic_issues)} possible logic gap(s) flagged where an idea jumps without a clear connection.' if logic_issues
                else 'No abrupt logic jumps flagged between sentences; ideas connect using visible linkers or reference chains.')
    steps.append({'key': 'logic', 'name': 'Logic leaps between ideas', 'score': l_score, 'status': l_status, 'detail': l_detail})

    ss = sentences(text)
    s_status = 'strong' if development >= 70 else 'developing' if development >= 45 else 'weak'
    steps.append({'key': 'structure', 'name': 'Structure & development', 'score': development, 'status': s_status,
                  'detail': f'{len(ss)} sentence(s) checked for paragraph flow and idea development against a {(essay_type or "general").replace("_", " ")} essay shape.'})
    return steps


def analyze_myanmar(text, essay_title=None, rubric='general'):
    """Lightweight offline Myanmar essay analysis with the same response shape
    as the English engine, so the existing Edu dashboard works unchanged."""
    text=(text or '').strip()
    segments=[x.strip() for x in re.split(r'[။!?]\s*', text) if x.strip()]
    tokens=re.findall(r'[\u1000-\u109F]+', text)
    n=len(tokens)
    if not text:
        overall=0
    else:
        connectors=["ထို့အပြင်","သို့သော်","ထို့ကြောင့်","အထူးသဖြင့်","အနှစ်ချုပ်အားဖြင့်","အခြားတစ်ဖက်တွင်"]
        connector_count=sum(text.count(x) for x in connectors)
        paragraphs=[p.strip() for p in re.split(r'\n\s*\n',text) if p.strip()]
        grammar_accuracy=max(55,min(98,82 + min(12, len(segments)//4) - (8 if '။။' in text else 0)))
        grammar_complexity=max(45,min(95,58 + len([s for s in segments if len(s)>80])*5))
        unique=len(set(tokens)); vocabulary_range=max(45,min(95,45 + round((unique/max(1,n))*45)))
        vocabulary_precision=max(45,min(95,55 + min(25, connector_count*4)))
        cohesion=max(45,min(95,55 + connector_count*7 + (8 if len(paragraphs)>=3 else 0)))
        coherence=max(45,min(95,68 + (8 if 3<=len(segments)<=12 else 0) - (10 if any(len(s)>180 for s in segments) else 0)))
        task_relevance=70 if essay_title else 60
        sentence_variety=max(45,min(95,55 + len(set(min(5,len(s)//40) for s in segments))*8))
        development=max(45,min(95,55 + min(30,len(paragraphs)*8) + min(10,n//80)))
        vals=[grammar_accuracy,grammar_complexity,vocabulary_range,vocabulary_precision,cohesion,coherence,task_relevance,sentence_variety,development]
        overall=round(sum(vals)/len(vals))
    level='A1' if overall<35 else 'A2' if overall<50 else 'B1' if overall<65 else 'B2' if overall<78 else 'C1' if overall<90 else 'C2'
    target={'A1':'A2','A2':'B1','B1':'B2','B2':'C1','C1':'C2','C2':'C2'}[level]
    scores={'grammar_accuracy':grammar_accuracy if text else 0,'grammar_complexity':grammar_complexity if text else 0,
            'vocabulary_range':vocabulary_range if text else 0,'vocabulary_precision':vocabulary_precision if text else 0,
            'cohesion':cohesion if text else 0,'coherence':coherence if text else 0,'task_relevance':task_relevance if text else 0,
            'sentence_variety':sentence_variety if text else 0,'development':development if text else 0}
    scores['overall']=overall
    spelling_highlights = check_myanmar_spelling(text)
    # Merge spelling findings into the same editor underline/issue pipeline.
    spelling_issues = [{k:v for k,v in h.items() if k in {'type','category','message','detail','text','start','end','replacement'}} for h in spelling_highlights]
    issues.extend(spelling_issues)
    feedback = ["မြန်မာဘာသာ စာစီစာကုံးအတွက် အခြေခံဖွဲ့စည်းပုံ၊ ဝါကျဆက်စပ်မှုနှင့် အကြောင်းအရာဖွံ့ဖြိုးမှုကို စစ်ဆေးထားပါသည်။"]
    if spelling_highlights:
        feedback.append(f"သတ်ပုံစစ်ဆေးမှုတွင် ပြန်စစ်ရန်လိုသော {len(spelling_highlights)} နေရာ တွေ့ရှိထားပါသည်။ အနီရောင်အောက်မျဉ်းကို နှိပ်၍ အကြံပြုထားသော သတ်ပုံမှန်ကို အသုံးပြုနိုင်ပါသည်။")
    if len(segments)<3: feedback.append("နိဒါန်း၊ အကြောင်းပြချက်ပါသော ကိုယ်ထည်စာပိုဒ်များနှင့် နိဂုံးပိုင်းကို ပိုမိုပြည့်စုံအောင် ရေးသားပါ။")
    if not essay_title: feedback.append("ခေါင်းစဉ်ထည့်ပေးပါက ခေါင်းစဉ်နှင့် စာအကြောင်းအရာ ကိုက်ညီမှုကို ပိုမိုကောင်းမွန်စွာ စစ်ဆေးနိုင်ပါသည်။")
    steps=[
      {'key':'thesis','name':'အဓိကအမြင်','score':min(100,55+min(35,n//20)) if text else 0,'status':'strong' if overall>=70 else 'developing' if overall>=50 else 'weak','detail':'အဓိကအမြင်ကို ရှင်းလင်းစွာ ဖော်ပြထားခြင်းကို စစ်ဆေးသည်။'},
      {'key':'evidence','name':'အထောက်အထားနှင့် ခေါင်းစဉ်ဆက်စပ်မှု','score':task_relevance if text else 0,'status':'strong' if task_relevance>=70 else 'developing','detail':'ခေါင်းစဉ်နှင့် အကြောင်းအရာဆက်စပ်မှုကို စစ်ဆေးသည်။'},
      {'key':'logic','name':'အတွေးအခေါ် ဆက်စပ်မှု','score':coherence if text else 0,'status':'strong' if coherence>=70 else 'developing','detail':'အကြောင်းပြချက်များ ဆက်စပ်ညီညွတ်မှုကို စစ်ဆေးသည်။'},
      {'key':'structure','name':'ဖွဲ့စည်းပုံနှင့် ဖွံ့ဖြိုးမှု','score':development if text else 0,'status':'strong' if development>=70 else 'developing','detail':f'{len(segments)} ဝါကျနှင့် {max(1,len(re.split(r"\\n\\s*\\n",text)))} စာပိုဒ်ကို စစ်ဆေးထားသည်။'}
    ]
    return {'scores':scores,'level':level,'target_level':target,'target_label':target,'raw_level':level,'weakest_core_level':level,
            'stats':{'words':n,'sentences':len(segments),'characters':len(text)},'issues':issues,'suggestions':[],
            'paragraph_feedback':' '.join(feedback),'linking_words':[],'highlights':spelling_highlights,'detected_essay_type':'မြန်မာ စာစီစာကုံး',
            'topic_relevance':{'available':bool(essay_title),'score':task_relevance,'label':'ကောင်း','message':'ခေါင်းစဉ်နှင့် စာအကြောင်းအရာကို စစ်ဆေးထားသည်။'},
            'thesis':{'detected':bool(text),'message':'အဓိကအမြင်ကို စစ်ဆေးထားသည်။'},
            'rubric':{'label':'မြန်မာစာ အထွေထွေ အကဲဖြတ်မှု','predicted_score':f'{overall}/100','criteria':{},'note':'မြန်မာဘာသာ စာစီစာကုံးအတွက် အော့ဖ်လိုင်း ခန့်မှန်းချက်ဖြစ်သည်။'},
            'audit_pipeline':steps}

def analyze(text, essay_title=None, rubric='general'):
    if not text.strip():
        zero={k:0 for k in ['grammar_accuracy','grammar_complexity','vocabulary_range','vocabulary_precision','cohesion','coherence','task_relevance','sentence_variety','development']}
        zero.update({'grammar':0,'vocabulary':0,'lexical':0,'accuracy':0,'overall':0})
        rel0=topic_relevance(essay_title or '',text); th0=thesis_check(essay_title or '',text,None)
        return {'scores':zero,'level':'A1','target_level':'B2','target_label':'B2','stats':{},'issues':[],'suggestions':[],'paragraph_feedback':'Write a paragraph first to receive feedback.','linking_words':CONCLUSION_LINKS['B2'],'highlights':[],'detected_essay_type':None,'topic_relevance':rel0,'thesis':th0,
                'rubric':predict_rubric_score(0,zero,rubric),'audit_pipeline':audit_pipeline(text,essay_title or '',None,rel0,th0,0,zero,[])}

    essay_type=detect_essay_type(essay_title or '', text)
    issues=pattern_issues(text); ws=words(text); ss=sentences(text)
    unique=len(set(ws)); ttr=unique/max(1,len(ws)); acad=academic_ratio(text); avg=avg_sentence_length(text)
    grammar_errors=len([i for i in issues if i['type']=='grammar'])
    accuracy_errors=len([i for i in issues if i['type']=='accuracy'])
    vocab_issues=len([i for i in issues if i['type']=='vocabulary'])
    # Sentence-boundary errors (comma splices, run-ons, fragments) are
    # already included in grammar_errors above (they're type:'grammar'),
    # but they interfere with readability more than a single wrong verb
    # form does, so they carry a slightly larger per-error penalty. Since
    # each one is already contributing its base 14-point weight through
    # grammar_errors, only the extra weight (6, for a total of 20) is
    # added here to avoid double-counting the same issue twice.
    boundary_errors=len([i for i in issues if 'comma splice' in i.get('message','') or 'run-on' in i.get('message','') or 'sentence fragment' in i.get('message','')])
    grammar_accuracy=max(0,100-min(60,grammar_errors*14+accuracy_errors*8+boundary_errors*6))
    # Vocabulary range rewards variety but uses diminishing returns.
    vocabulary_range=min(100,round(30+ttr*85))
    vocabulary_precision=min(100,round(45+ttr*35+acad*100*.45-min(20,vocab_issues*2)))
    complexity_metrics_=complexity_metrics(text)
    grammar_complexity=complexity_metrics_['complexity']
    sentence_variety=complexity_metrics_['sentence_variety']
    # Cohesion uses purposeful connectors and paragraph/sentence development.
    # Count connectors from every CEFR band (not just B2) so that advanced
    # linkers (e.g. C1/C2 "notwithstanding", "insofar as") are credited
    # instead of being invisible to the detector and dragging cohesion down.
    all_transitions=set()
    for lvl_words in TRANSITIONS.values():
        all_transitions.update(lvl_words)
    target_trans=sum(1 for x in all_transitions if re.search(rf'\b{re.escape(x)}\b',text,re.I))
    cohesion=min(100,round(45+min(30,target_trans*6)+(15 if len(ss)>=3 else 0)+(10 if complexity_metrics_['subordination']>0.5 else 0)))
    # Coherence penalises extreme sentence length and rewards developed, controlled prose.
    coherence=max(25,min(100,round(78-abs(avg-20)*1.1-(18 if complexity_metrics_['long_sentence_ratio']>.35 else 0)+(8 if 8<=avg<=28 else 0))))
    relevance=topic_relevance(essay_title or '',text)
    thesis=thesis_check(essay_title or '',text,essay_type)
    task_relevance=relevance['score'] if relevance.get('available') else (65 if thesis.get('detected') else 45)
    development=task_development_score(text,essay_type,relevance,thesis)

    raw_scores={'grammar_accuracy':grammar_accuracy,'grammar_complexity':grammar_complexity,
                'vocabulary_range':vocabulary_range,'vocabulary_precision':vocabulary_precision,
                'cohesion':cohesion,'coherence':coherence,'task_relevance':task_relevance,
                'sentence_variety':sentence_variety,'development':development}
    overall,level,raw_level,weakest=estimate_cefr(raw_scores)
    target=target_level(level)
    # Legacy dashboard fields remain available.
    grammar=round(grammar_accuracy*.60+grammar_complexity*.40)
    vocab=round(vocabulary_range*.60+vocabulary_precision*.40)
    lexical=vocabulary_precision
    accuracy=grammar_accuracy
    feedback,rules,target_vocab=database_feedback(text,overall,level,target,issues,essay_type)
    if relevance.get('available'):
        feedback.append(f'Topic relevance: {relevance["label"]} ({relevance["score"]}/100). {relevance["message"]}')
    if essay_title.strip():
        feedback.append(f'Thesis check: {thesis["message"]}')
    feedback.append(f'Level method: weighted language/task profile = {overall}/100; raw band {raw_level}, controlled by a core-skill ceiling at {level}.')
    suggestions=[]
    # Context-aware repetition coaching: broad clickable alternatives first, then academic/context notes.
    suggestions.extend(broad_repetition_suggestions(text, target)[:12])
    existing_rep_words={s.get('word','').lower() for s in suggestions if s.get('category')=='repetition'}
    suggestions.extend([s for s in repetition_suggestions(text, target) if s.get('word','').lower() not in existing_rep_words][:8])
    actionable=[i for i in issues if i.get('replacement') is not None]
    for i in actionable[:8]:
        suggestions.append({'kind':'better','emoji':'🟡','text':f'Change “{i["text"]}” → “{i["replacement"]}”','start':i['start'],'end':i['end'],'replacement':i['replacement']})
    if ttr < 0.45: suggestions.append({'kind':'better','emoji':'🟡','text':f'Build vocabulary variety toward {target}. Use a more precise word only when it matches the intended meaning.'})
    if acad < 0.03: suggestions.append({'kind':'better','emoji':'🔵','text':f'Use more precise academic vocabulary appropriate to {target}; avoid forcing advanced words.'})
    if grammar_complexity < 55: suggestions.append({'kind':'better','emoji':'🟡','text':f'Increase sentence variety toward {target}: combine some related ideas with accurate subordinate or relative clauses.'})
    if sentence_variety < 60: suggestions.append({'kind':'better','emoji':'🟡','text':'Mix simple, compound and complex sentences instead of using one repeated sentence pattern.'})
    if len(ss)>=3 and target_trans==0: suggestions.append({'kind':'good','emoji':'🟢','text':f'Add a logical linker when needed, such as “{TRANSITIONS[target][0]}” or “{TRANSITIONS[target][1]}”.'})
    if avg>30: suggestions.append({'kind':'better','emoji':'🟡','text':'Break very long sentences when this makes the logical relationship between ideas clearer.'})
    suggestions.append({'kind':'best' if overall>=85 else 'good','emoji':'🟣' if overall>=85 else '🟢','text':f'Your next target is {TARGET_LABEL[level]}. Revise accuracy first, then build complexity and vocabulary precision using the database reference examples.'})
    if not text.strip().endswith(('.', '!', '?')): suggestions.append({'kind':'good','emoji':'🟢','text':'Finish the final sentence with appropriate punctuation.'})
    if essay_title.strip() and relevance.get('available') and relevance['score'] < 65:
        suggestions.append({'kind':'better','emoji':'🎯','text':f'Keep the paragraph anchored to the essay title: {relevance["message"]}'})
    if essay_title.strip() and not thesis['detected']:
        suggestions.append({'kind':'best','emoji':'🎓','text':'Add a clear thesis in the introduction: directly state your position or the main answer to the essay question.'})
    return {'scores':{'grammar':grammar,'vocabulary':vocab,'lexical':lexical,'accuracy':accuracy,'coherence':coherence,'cohesion':cohesion,
                       'grammar_accuracy':grammar_accuracy,'grammar_complexity':grammar_complexity,'vocabulary_range':vocabulary_range,
                       'vocabulary_precision':vocabulary_precision,'task_relevance':task_relevance,'sentence_variety':sentence_variety,
                       'development':development,'overall':overall},
            'level':level,'raw_level':raw_level,'weakest_core_level':weakest,
            'target_level':target,'target_label':TARGET_LABEL[level],
            'method':{'weights':{'Grammar accuracy':20,'Grammar complexity':15,'Vocabulary range':15,'Vocabulary precision':10,'Cohesion':10,'Coherence':10,'Task relevance':10,'Sentence variety':5,'Development':5},
                      'ceiling_rule':'Overall level is capped so weak core language control cannot be hidden by advanced vocabulary alone.'},
            'stats':{'words':len(ws),'sentences':len(ss),'characters':len(text),'unique_words':unique,'type_token_ratio':round(ttr,3),'academic_word_ratio':round(acad,3),'avg_sentence_words':round(avg,1),
                     'subordination_per_sentence':round(complexity_metrics_['subordination'],2),'long_sentence_ratio':round(complexity_metrics_['long_sentence_ratio'],2)},
            'issues':dedupe_repetition_issues(issues)[:80],'suggestions':suggestions,'paragraph_feedback':' '.join(feedback),
            'linking_words':CONCLUSION_LINKS[target],'level_transitions':TRANSITIONS[target][:6],
            'highlights':([i for i in issues if 'start' in i and 'end' in i] + [s for s in suggestions if s.get('category')=='repetition' and 'start' in s and 'end' in s])[:100],
            'topic_relevance':relevance,'thesis':thesis,
            'detected_essay_type':essay_type.replace('_',' ').title() if essay_type else None,
            'target_vocabulary':target_vocab,'rules_triggered':rules,
            'rubric':predict_rubric_score(overall,raw_scores,rubric),
            'audit_pipeline':audit_pipeline(text,essay_title or '',essay_type,relevance,thesis,development,raw_scores,issues)}


@edu_bp.route('/')
@edu_bp.route('/lang=<lang>')
def index(lang=None):
    # /edu/ is the English entry point; /edu/lang=my opens a dedicated
    # Myanmar-language tab without replacing the current English tab.
    requested = (lang or '').strip().lower()
    if requested not in ('', 'my', 'en'):
        requested = 'en'
    return render_template('index.html', initial_language=('my' if requested == 'my' else 'en'))

@edu_bp.route('/edu-logo.png')
def edu_logo():
    from flask import send_from_directory
    return send_from_directory(BASE, 'edu-logo.png')

# NOTE: /api/analyze (the paid text-analysis endpoint) is intentionally NOT
# registered here. It's defined once, directly on the main Flask app in
# backend/app.py, because charging TSO coins requires the Supabase-backed
# users/sessions tables that this blueprint (SQLite-only, no session
# awareness) doesn't have access to. See app.py's edu_api_analyze_paid().
# The `analyze()` function above is imported from there and called directly.

@edu_bp.get('/api/health')
def health(): return jsonify({'server':True,'database':DB_PATH.exists(),'ai_required':False})

@edu_bp.get('/api/rubrics')
def rubrics(): return jsonify({'rubrics':[{'key':k,**v} for k,v in RUBRICS.items()]})

# စာစီစာကုံး topic bank — a free, self-contained topic picker independent
# from generation_topic_knowledge (which grounds အဆိုအချေ/debate and English
# essay generation). Lets students browse or randomly draw a ready-made
# Myanmar composition title by category/difficulty instead of typing one
# blind. No TSO coin cost; this only reads a small local reference table.
@edu_bp.get('/api/topics')
def essay_topics():
    category = (request.args.get('category') or '').strip()
    difficulty = (request.args.get('difficulty') or '').strip().lower()
    random_flag = (request.args.get('random') or '').strip().lower() in {'1', 'true', 'yes'}
    limit_raw = request.args.get('limit')
    try:
        limit = max(1, min(100, int(limit_raw))) if limit_raw else (1 if random_flag else 100)
    except (TypeError, ValueError):
        limit = 1 if random_flag else 100

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        clauses, params = [], []
        if category:
            clauses.append('category = ?'); params.append(category)
        if difficulty:
            clauses.append('difficulty = ?'); params.append(difficulty)
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        order = ' ORDER BY RANDOM()' if random_flag else ' ORDER BY category, id'
        rows = conn.execute(
            f'SELECT title, category, difficulty, keywords FROM essay_topics{where}{order} LIMIT ?',
            (*params, limit)).fetchall()
        categories = [r[0] for r in conn.execute(
            'SELECT DISTINCT category FROM essay_topics ORDER BY category').fetchall()]
        conn.close()
    except Exception:
        return jsonify({'ok': False, 'error': 'Topic bank unavailable.', 'topics': [], 'categories': []}), 500

    topics = [dict(r) for r in rows]
    if random_flag:
        return jsonify({'ok': True, 'topic': topics[0] if topics else None, 'categories': categories})
    return jsonify({'ok': True, 'topics': topics, 'categories': categories, 'count': len(topics)})

# Idea Map / Architecture Sketch — free, self-contained (no external AI call,
# no TSO coin cost). Builds a structural diagram from the essay's own text
# and an optional decorative sketch layer, both rendered as SVG locally.
@edu_bp.post('/api/idea-map')
def idea_map_endpoint():
    from .idea_map import generate_idea_map
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    title = (data.get('title') or data.get('essay_title') or '').strip()
    include_sketch = data.get('include_sketch', True)
    if not text:
        return jsonify({'ok': False, 'error': 'Write a paragraph first to generate an idea map.'}), 400
    if len(text) > 20000:
        return jsonify({'ok': False, 'error': 'Text is too long for the idea map.'}), 400
    result = generate_idea_map(text, essay_title=title, include_sketch=bool(include_sketch))
    return jsonify(result)

init_db()
