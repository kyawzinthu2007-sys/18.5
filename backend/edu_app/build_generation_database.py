"""Build/upgrade the bundled TSO Edu local generation knowledge database.
This database contains original pedagogical metadata and short facts/angles,
not copyrighted textbook passages.
"""
from pathlib import Path
import sqlite3, json, csv
DB_PATH = Path(__file__).parent / "data" / "writing_coach.db"
ESSAY_TOPICS_CSV = Path(__file__).parent / "data" / "essay_topics_100.csv"

TOPICS = [
('education','Education and Learning','education school student learning teacher university curriculum exam',
 'access, quality, equity, motivation, skills, assessment',
 'improve access to learning; develop practical and academic skills; support teachers; increase motivation',
 'unequal access; exam pressure; excessive screen use; funding constraints',
 'online classes, school facilities, teacher training, vocational education'),
('technology','Technology and Digital Life','technology digital internet computer smartphone app artificial intelligence AI',
 'access, efficiency, privacy, dependency, inequality, innovation',
 'save time; improve access to information; automate routine work; connect people',
 'privacy risks; misinformation; digital exclusion; overdependence',
 'online services, smartphones, AI tools, cybersecurity'),
('environment','Environment and Climate','environment climate pollution carbon energy nature recycling sustainability wildlife',
 'emissions, conservation, consumption, energy, adaptation, policy',
 'reduce pollution; protect habitats; improve public health; conserve resources',
 'transition costs; enforcement difficulties; unequal burdens; slow results',
 'renewable energy, recycling, public transport, conservation'),
('health','Health and Wellbeing','health exercise diet medical doctor disease fitness hospital wellbeing nutrition',
 'prevention, access, lifestyle, healthcare, inequality, mental wellbeing',
 'prevent illness; improve fitness; reduce healthcare pressure; support wellbeing',
 'cost; unequal access; poor adherence; limited healthcare capacity',
 'exercise, nutrition, preventive care, public-health campaigns'),
('transport','Transport and Cities','transport traffic bus car road travel commute cycling train',
 'mobility, congestion, safety, emissions, infrastructure, affordability',
 'reduce congestion; improve mobility; lower emissions; expand affordable travel',
 'construction cost; maintenance; rural limitations; resistance to change',
 'rail networks, buses, cycling, pedestrian areas'),
('work','Work and Employment','work job employee employment career office salary workplace remote employer',
 'productivity, flexibility, skills, income, work-life balance, management',
 'increase flexibility; widen recruitment; reduce commuting; improve work-life balance',
 'isolation; blurred boundaries; coordination problems; unequal home conditions',
 'remote work, training, flexible schedules, workplace policies'),
('government','Government and Public Policy','government policy public state law tax citizen regulation',
 'effectiveness, fairness, cost, accountability, implementation, trust',
 'provide consistent services; protect vulnerable groups; establish standards; improve accountability',
 'bureaucracy; public cost; unintended effects; weak implementation',
 'tax policy, public services, regulation, local government'),
('crime','Crime and Public Safety','crime criminal police prison punishment illegal safety offence offender theft burglary arrest law justice sentence victim reoffending',
 'prevention, deterrence, rehabilitation, policing, inequality, justice',
 'improve safety; deter offending; support rehabilitation; increase public confidence',
 'high costs; unfair enforcement; overcrowding; failure to address root causes',
 'community policing, rehabilitation, youth programmes, prevention'),
('media','Media and Information','media news television social advertising journalism newspaper broadcasting',
 'accuracy, access, bias, accountability, attention, literacy',
 'inform the public; expose wrongdoing; broaden participation; share information quickly',
 'misinformation; sensationalism; bias; reduced trust',
 'social media, journalism, advertising, fact checking'),
('family','Family and Society',
 'family families parent parents parenting child children kid kids sibling siblings marriage married '
 'spouse household upbringing grandparent grandparents relative relatives divorce stepfamily guardian '
 'caregiver elderly discipline chores nuclear extended single-parent',
 'support, responsibility, development, care, equality, time, discipline, caregiving',
 'provide emotional support; support child development; share responsibilities; strengthen intergenerational bonds',
 'financial pressure; time conflicts; unequal responsibilities; changing circumstances; caregiving strain on one member',
 'parenting, childcare, household work, intergenerational support, single-parent households, elder care'),
('tourism','Tourism and Travel','tourism travel holiday visitor hotel destination culture',
 'income, culture, environment, infrastructure, employment, overcrowding',
 'create jobs; support local businesses; encourage cultural exchange; fund conservation',
 'overcrowding; environmental damage; seasonal dependence; rising local costs',
 'heritage sites, eco-tourism, local businesses, transport'),
('economy','Economy and Cost of Living','economy inflation prices income poverty business finance cost',
 'income, prices, employment, productivity, inequality, stability',
 'create employment; improve productivity; increase investment; support living standards',
 'inflation; inequality; financial insecurity; market shocks',
 'housing costs, wages, small businesses, public spending'),
('science','Science and Research','science research experiment discovery evidence laboratory innovation',
 'evidence, funding, ethics, innovation, uncertainty, public benefit',
 'expand knowledge; improve technology; solve practical problems; inform policy',
 'research costs; ethical risks; uncertain outcomes; unequal access to benefits',
 'medical research, energy research, public science education'),
('culture','Culture and Heritage','culture tradition heritage language art museum identity community',
 'identity, preservation, diversity, access, commercialization, education',
 'preserve heritage; strengthen identity; encourage creativity; support tourism',
 'commercialization; exclusion; changing traditions; preservation costs',
 'museums, festivals, languages, historic sites'),
('sports','Sport and Physical Activity','sport football exercise athletics competition fitness team',
 'health, teamwork, discipline, inclusion, funding, performance',
 'improve health; develop teamwork; build discipline; create community',
 'cost; injury; excessive competition; unequal opportunities',
 'school sport, public facilities, professional sport'),
('housing','Housing and Urban Living','housing home rent apartment city urban property homelessness',
 'affordability, supply, location, quality, planning, inequality',
 'provide stable living conditions; support workers; improve neighbourhoods',
 'high rents; shortages; displacement; infrastructure pressure',
 'affordable housing, zoning, public housing, urban planning'),
('food','Food and Agriculture','food farming agriculture diet waste farmers crops production',
 'security, nutrition, cost, sustainability, waste, rural livelihoods',
 'support food security; provide jobs; improve nutrition; reduce waste',
 'resource use; price volatility; waste; unequal access',
 'local farming, food waste, school meals, sustainable agriculture'),
('globalisation','Globalisation and International Relations','globalisation trade international country global business culture',
 'trade, jobs, culture, supply chains, inequality, cooperation',
 'expand markets; increase exchange; spread knowledge; create opportunities',
 'unequal gains; dependence; cultural pressure; supply-chain disruption',
 'international trade, migration, multinational companies, cooperation'),
('social_media','Social Media','social media facebook tiktok instagram platform influencer online',
 'communication, identity, information, privacy, business, wellbeing',
 'connect communities; promote small businesses; share information; enable participation',
 'misinformation; privacy loss; comparison pressure; addictive use',
 'short videos, online communities, digital marketing, moderation'),
('ai','Artificial Intelligence','artificial intelligence AI machine learning automation chatbot robot',
 'productivity, accuracy, employment, ethics, privacy, education',
 'automate routine work; assist learning; analyse information; improve productivity',
 'job displacement; bias; privacy concerns; overreliance',
 'AI tutors, workplace automation, recommendation systems, language tools'),
('libraries','Libraries and Public Learning','library libraries book books reading public information community learning archive librarian borrowing literacy shelves catalogue',
 'access, literacy, digital inclusion, quiet study, community services',
 'provide free resources; support literacy; reduce information inequality',
 'funding; changing usage; digital alternatives; maintenance',
 'public libraries, e-books, study spaces, community programmes'),
('advertising','Advertising and Consumer Behaviour','advertising marketing consumer product brand commercial advert advertisement campaign promotion sponsor sponsorship influencer billboard endorsement',
 'information, persuasion, choice, business, children, consumption',
 'inform consumers; support competition; help businesses reach customers',
 'manipulation; overconsumption; misleading claims; pressure on children',
 'online ads, product placement, influencer marketing, consumer literacy'),
('energy','Energy and Resources','energy electricity renewable solar wind coal oil gas power',
 'security, cost, emissions, reliability, investment, access',
 'increase energy security; reduce emissions; support development',
 'transition cost; intermittency; infrastructure needs; affordability',
 'solar, wind, electricity grids, energy efficiency'),
('internet','Internet and Online Services','internet online web website digital connectivity broadband wifi browsing network connection access offline bandwidth',
 'access, communication, commerce, education, privacy, security',
 'increase access; support commerce; enable remote learning; improve communication',
 'cybersecurity; misinformation; digital exclusion; privacy',
 'e-commerce, online banking, remote learning, broadband'),
('youth','Young People and Education','youth teenager teenagers young children generation adolescent adolescents teen upbringing',
 'skills, identity, opportunity, pressure, employment, participation',
 'develop skills; increase opportunities; encourage civic participation',
 'exam stress; unemployment; harmful online content; inequality',
 'career guidance, apprenticeships, youth activities, mentoring'),
('language','Language and Communication','language languages bilingual fluent communication dialect translation vocabulary accent multilingual linguistic',
 'access, identity, education, employment, cultural exchange',
 'improve communication; expand educational access; support international exchange',
 'language barriers; unequal opportunities; loss of minority languages',
 'English learning, translation, multilingual education, language preservation'),
('democracy','Civic Participation','democracy democratic election vote voting representation ballot candidate parliament referendum electorate constituency suffrage governance',
 'participation, representation, trust, accountability, information',
 'increase participation; improve accountability; represent diverse views',
 'misinformation; disengagement; polarisation; unequal participation',
 'voting, public consultation, civic education, local participation'),
('sustainability','Sustainable Development','sustainability sustainable development green economy resources future circular recycling conservation renewable eco-friendly footprint stewardship',
 'long-term planning, resources, equity, environment, growth',
 'protect resources; reduce waste; support resilient development',
 'higher initial costs; coordination problems; conflicting priorities',
 'circular economy, efficient buildings, renewable energy, responsible consumption'),
('education_myanmar','မြန်မာ စာစီစာကုံး—ပညာရေး','ပညာရေး ကျောင်းသား ဆရာ ဆရာမ ကျောင်း တက္ကသိုလ် စာသင်',
 'ပညာရည်, စည်းကမ်း, အခွင့်အရေး, ဆရာ, မိဘ, လူမှုဘဝ',
 'အသိပညာတိုးတက်စေခြင်း; အကျင့်စာရိတ္တဖွံ့ဖြိုးစေခြင်း; အလုပ်အကိုင်အတွက် ပြင်ဆင်ပေးခြင်း',
 'အခွင့်အရေးမညီမျှမှု; စာမေးပွဲဖိအား; အရင်းအမြစ်ကန့်သတ်မှု',
 'စာဖတ်ခြင်း, ကျောင်းပညာရေး, ဆရာကောင်း, မိဘပူးပေါင်းမှု'),
('environment_myanmar','မြန်မာ စာစီစာကုံး—ပတ်ဝန်းကျင်','ပတ်ဝန်းကျင် သဘာဝ သစ်တော ရေ အမှိုက် လေထု ညစ်ညမ်း',
 'သဘာဝထိန်းသိမ်းရေး, သန့်ရှင်းရေး, တာဝန်ယူမှု, အရင်းအမြစ်',
 'သဘာဝကိုကာကွယ်ခြင်း; ကျန်းမာရေးကောင်းမွန်စေခြင်း; အနာဂတ်မျိုးဆက်များအတွက် အရင်းအမြစ်ထိန်းသိမ်းခြင်း',
 'အမှိုက်ပြဿနာ; သဘာဝပျက်စီးမှု; အသိပညာနည်းပါးမှု',
 'အမှိုက်ခွဲခြားခြင်း, သစ်ပင်စိုက်ခြင်း, ရေထိန်းသိမ်းခြင်း'),
('character_myanmar','မြန်မာ စာစီစာကုံး—ကိုယ်ကျင့်တရား','ကိုယ်ကျင့်တရား စည်းကမ်း ရိုးသားမှု ကြိုးစားမှု တာဝန်ယူမှု လူငယ်',
 'ရိုးသားမှု, စည်းကမ်း, ကြိုးစားမှု, တာဝန်ယူမှု, အများအကျိုး',
 'ယုံကြည်မှုတည်ဆောက်ခြင်း; လူမှုဘဝတိုးတက်စေခြင်း; အောင်မြင်မှုအတွက် အခြေခံပေးခြင်း',
 'စည်းကမ်းပျက်မှု; အလွယ်တကူအောင်မြင်လိုမှု; မကောင်းသောပတ်ဝန်းကျင်',
 'အချိန်တိကျမှု, အလုပ်ကြိုးစားမှု, အများအကျိုးဆောင်ရွက်မှု'),
('technology_myanmar','မြန်မာ စာစီစာကုံး—နည်းပညာ','နည်းပညာ ကွန်ပျူတာ အင်တာနက် ဖုန်း ဒစ်ဂျစ်တယ် လူမှုကွန်ရက်',
 'အကျိုးရှိမှု, ပညာရေး, ဆက်သွယ်ရေး, လုံခြုံရေး, တာဝန်ယူမှု',
 'သတင်းအချက်အလက်ရရှိစေခြင်း; ဆက်သွယ်ရေးလွယ်ကူခြင်း; ပညာသင်ယူနိုင်ခြင်း',
 'အချိန်ဖြုန်းခြင်း; မမှန်သတင်း; ကိုယ်ရေးကိုယ်တာလုံခြုံရေး',
 'အွန်လိုင်းပညာရေး, ဒစ်ဂျစ်တယ်ကျွမ်းကျင်မှု, လုံခြုံသောအင်တာနက်အသုံးပြုမှု'),
]

LEVEL_RULES = {
'A1':'Use short, clear sentences, familiar vocabulary, one main idea per paragraph, and a direct conclusion.',
'A2':'Use simple but varied sentences, common topic vocabulary, basic examples, and clear cause/contrast links.',
'B1':'Develop each point with a reason and example; use controlled complex sentences and clear paragraph progression.',
'B2':'Use precise vocabulary, varied sentence structures, balanced development and explicit logical relationships.',
'C1':'Use nuanced claims, precise collocations, controlled complexity, qualifications and synthesis rather than repetition.',
'C2':'Use sophisticated but natural phrasing, subtle distinctions, explicit evaluation and tightly controlled cohesion.'}

TYPE_RULES = {
'opinion':'State a clear position and support it consistently; acknowledge a relevant limitation where useful.',
'discussion':'Explain both views fairly, develop each side, then give a justified overall opinion.',
'advantages_disadvantages':'Present major advantages and disadvantages, compare their significance and reach a clear judgement.',
'problem_solution':'Explain important causes/problems, then propose realistic measures and explain how they address the problem.',
'two_part':'Answer both questions fully and separately while maintaining a single coherent overall argument.',
'cause_effect':'Explain meaningful causes, connect them to consequences, and distinguish immediate from longer-term effects.',
'positive_negative':'Evaluate positive and negative dimensions and state whether the overall development is beneficial or harmful.',
'descriptive':'Describe the subject clearly with relevant details, logical order and an appropriate Myanmar school composition style.',
'process':'Present stages in a clear sequence, explain relationships between steps and finish with the overall outcome.',
'expository':'Explain the subject objectively with definitions, causes, examples and consequences where relevant.',
'argumentative':'Present a defensible position, support it with reasons and examples, consider an opposing point and conclude logically.'}

def load_essay_topics(con):
    """Load the စာစီစာကုံး (composition) topic bank — a separate, independent
    content set from generation_topic_knowledge (which powers အဆိုအချေ/debate
    and English essay grounding). This table is a pure topic picker/bank:
    100 curated Myanmar composition titles across 10 categories with a
    beginner/intermediate/advanced difficulty tag, used to let students pick
    a ready-made စာစီစာကုံး title instead of typing one blind.
    """
    con.executescript('''
    CREATE TABLE IF NOT EXISTS essay_topics (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT UNIQUE NOT NULL,
      category TEXT NOT NULL,
      difficulty TEXT NOT NULL,
      keywords TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_essay_topics_category ON essay_topics(category);
    CREATE INDEX IF NOT EXISTS idx_essay_topics_difficulty ON essay_topics(difficulty);
    ''')
    if not ESSAY_TOPICS_CSV.exists():
        return 0
    rows = []
    with open(ESSAY_TOPICS_CSV, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            title = (r.get('title') or '').strip()
            category = (r.get('category') or '').strip()
            difficulty = (r.get('difficulty') or '').strip().lower()
            keywords = (r.get('keywords') or title).strip()
            if title and category:
                rows.append((title, category, difficulty, keywords))
    con.executemany(
        'INSERT OR REPLACE INTO essay_topics(title,category,difficulty,keywords) VALUES (?,?,?,?)',
        rows)
    return len(rows)


def main():
    con=sqlite3.connect(DB_PATH)
    con.executescript('''
    CREATE TABLE IF NOT EXISTS generation_topic_knowledge (
      id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
      keywords TEXT NOT NULL, angles TEXT NOT NULL, benefits TEXT NOT NULL, risks TEXT NOT NULL, examples TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS generation_level_rules (
      level TEXT PRIMARY KEY, rule TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS generation_type_rules (
      type_key TEXT PRIMARY KEY, rule TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS generation_pair_rules (
      level TEXT NOT NULL, type_key TEXT NOT NULL, paragraph_plan TEXT NOT NULL,
      PRIMARY KEY(level,type_key)
    );
    ''')
    essay_topics_loaded = load_essay_topics(con)
    con.executemany('INSERT OR REPLACE INTO generation_topic_knowledge(domain,title,keywords,angles,benefits,risks,examples) VALUES (?,?,?,?,?,?,?)', TOPICS)
    con.executemany('INSERT OR REPLACE INTO generation_level_rules(level,rule) VALUES (?,?)', LEVEL_RULES.items())
    con.executemany('INSERT OR REPLACE INTO generation_type_rules(type_key,rule) VALUES (?,?)', TYPE_RULES.items())
    plans={
      'opinion':'Introduction with thesis; reason 1 + example; reason 2 + example/qualification; conclusion.',
      'discussion':'Introduction; view A + development; view B + development; own judgement; conclusion.',
      'advantages_disadvantages':'Introduction; strongest advantages; strongest disadvantages; comparison/judgement; conclusion.',
      'problem_solution':'Introduction; causes/problem 1; causes/problem 2; practical solutions; conclusion.',
      'two_part':'Introduction; answer part 1; answer part 2; implications/example; conclusion.',
      'cause_effect':'Introduction; major cause(s); mechanism/link; effects; conclusion.',
      'positive_negative':'Introduction; positive effects; negative effects; overall evaluation; conclusion.',
      'descriptive':'Introduction; main features; supporting details; significance/lesson; conclusion.',
      'process':'Introduction; starting stage; middle stages; final stage/outcome; conclusion.',
      'expository':'Definition/context; key causes/features; examples/effects; implications; conclusion.',
      'argumentative':'Introduction + claim; reason 1; reason 2; counterargument/rebuttal; conclusion.'}
    rows=[]
    for level in LEVEL_RULES:
      for typ,plan in plans.items(): rows.append((level,typ,plan))
    con.executemany('INSERT OR REPLACE INTO generation_pair_rules(level,type_key,paragraph_plan) VALUES (?,?,?)', rows)
    con.commit()
    stats={t:con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ['sample_essays','essay_types','reference_books','feedback_rules','vocabulary_targets','generation_topic_knowledge','generation_level_rules','generation_type_rules','generation_pair_rules','essay_topics']}
    con.close()
    print(json.dumps({'database':str(DB_PATH),'tables':stats},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
