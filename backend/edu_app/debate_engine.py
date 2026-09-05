"""
TSO Edu — Myanmar အဆိုအချေ engine.
Offline, deterministic and aligned with the four Myanmar debate/အဆိုအချေ
patterns supplied for TSO Edu:
A) အကြောင်းအရာနှစ်ခု နှစ်ဖက်မျှ
B) အကြောင်းအရာတစ်ခု ကျိုး/ပြစ် မျှ
C) အကြောင်းအရာတစ်ခု တစ်ဖက်အလေးကဲ
D) အကြောင်းအရာတစ်ခု နှိုင်းယှဉ်ဘက်အများ
The engine classifies a proposition, determines a support/opposition stance,
checks the recommended 4-paragraph architecture, and returns concrete
strengths/weaknesses for generation and analysis. No external AI is required.
"""
import re
from .myanmar_spelling import check_myanmar_spelling

TYPE_LABELS = {
    "balanced_two_sided": "အကြောင်းအရာနှစ်ခု နှစ်ဖက်မျှအဆို",
    "balanced_pro_con": "အကြောင်းအရာတစ်ခု ကျိုး/ပြစ်မျှအဆို",
    "one_sided": "အကြောင်းအရာတစ်ခု တစ်ဖက်အလေးကဲအဆို",
    "comparative_many": "အကြောင်းအရာတစ်ခု နှိုင်းယှဉ်ဘက်အများအဆို",
}
STANCE_WORDS = {
    "support": ["ထောက်ခံ", "သဘောတူ", "ကောင်းသည်", "အကျိုးရှိ", "သာလွန်", "အလှဆုံး", "အကောင်းဆုံး", "ပို၍"],
    "oppose": ["ကန့်ကွက်", "သဘောမတူ", "မကောင်း", "အပြစ်", "အားနည်း", "မသင့်", "မဖြစ်သင့်"],
}
COMPARATIVE = ["အကောင်းဆုံး", "အလှဆုံး", "အကောင်းမွန်ဆုံး", "အများဆုံး", "စိတ်ဝင်စားစရာအကောင်းဆုံး"]
ONE_SIDED = ["ပညာနှင့်တူသော", "ကျေးဇူးသိတတ်ခြင်း", "လူ့ယဉ်ကျေးမှု", "မရှိ", "မတန်", "အရေးကြီးသည်", "လိုအပ်သည်"]
BALANCED = ["ထက်", "ဖြစ်ရခြင်းသည်ကောင်း", "ကောင်းသည်", "မကောင်း", "အကျိုး", "အပြစ်", "ကောင်းကျိုး", "ဆိုးကျိုး"]

def classify_proposition(title):
    t = (title or "").strip()
    if any(x in t for x in COMPARATIVE):
        return "comparative_many"
    if any(x in t for x in ONE_SIDED) and not any(x in t for x in ["ထက်", "အကောင်းဆုံး", "အလှဆုံး"]):
        return "one_sided"
    # "A ထက် B" can be a two-sided comparison when neither superlative is present.
    if "ထက်" in t:
        return "balanced_two_sided"
    if any(x in t for x in BALANCED):
        return "balanced_pro_con"
    return "balanced_two_sided"

def detect_stance(text, title=""):
    t = (text or "") + " " + (title or "")
    sup = sum(t.count(x) for x in STANCE_WORDS["support"])
    opp = sum(t.count(x) for x in STANCE_WORDS["oppose"])
    if sup == opp == 0:
        return "support"
    return "support" if sup >= opp else "oppose"

def _paras(text):
    p = [x.strip() for x in re.split(r"\n\s*\n", text.strip()) if x.strip()]
    if len(p) >= 4:
        return p
    # Myanmar full stops are useful fallback paragraph boundaries.
    s = [x.strip() for x in re.split(r"(?<=[။!?])\s*", text.strip()) if x.strip()]
    if not s:
        return p
    n = len(s)
    size = max(1, (n + 3) // 4)
    return [" ".join(s[i:i+size]) for i in range(0, n, size)]

def _myanmar_grammar_highlights(text):
    """Conservative offline Myanmar proofreading flags.
    These are pattern-based warnings, not an AI grammar judgment.
    Every returned item is compatible with the Edu editor highlighter.
    """
    items = []
    def add(pattern, message, replacement=None):
        for m in re.finditer(pattern, text):
            # Avoid flagging a span twice.
            item = {"start": m.start(), "end": m.end(), "text": m.group(0),
                    "type": "grammar", "category": "grammar", "message": message}
            if replacement is not None:
                item["replacement"] = replacement
            if not any(not (item["end"] <= x["start"] or item["start"] >= x["end"]) for x in items):
                items.append(item)

    add(r"[ \t]+[။၊,!?]", "ပုဒ်ဖြတ်အမှတ်မတိုင်မီ မလိုအပ်သော space ရှိနေသည်။")
    add(r"[။၊,!?]{2,}", "ပုဒ်ဖြတ်အမှတ်များ ထပ်နေသည်။")
    add(r"\b(\S+)\s+\1\b", "တူညီသောစကားလုံး ထပ်ရေးထားသည်။")
    add(r"သည်\s+သည်", "“သည်” ထပ်နေသည်။")
    add(r"ဖြစ်သည်\s+သည်", "ဝါကျဖွဲ့စည်းပုံကို ပြန်စစ်ပါ။")
    add(r"သောကြောင့်\s+ထို့ကြောင့်", "အကြောင်းပြဆက်စပ်စကားလုံးများ ထပ်သုံးထားသည်။")
    add(r"ထို့ကြောင့်\s+ထို့ကြောင့်", "“ထို့ကြောင့်” ထပ်သုံးထားသည်။")
    # Common spacing/particle mistakes seen in student Myanmar writing.
    add(r"ပါ\s*သည်", "“ပါသည်” ကို စကားလုံးတစ်လုံးတည်းအဖြစ် ရေးပါ။", "ပါသည်")
    add(r"လို့\s+ဆို\s+ပြီး", "ဆက်စပ်စကားလုံးအသုံးပြုပုံကို ပြန်စစ်ပါ။")
    return sorted(items, key=lambda x: (x["start"], x["end"]))

def _debate_paragraphs(text):
    return [x.strip() for x in re.split(r"\n\s*\n", text.strip()) if x.strip()]

def _contains_any(text, words):
    return any(w in text for w in words)

def _paragraph_score_flags(ps, kind, stance):
    """Return exact 10-mark rubric, 2+3+3+2.
    Paragraph 1 is introduction and is structurally required but unscored.
    """
    p = ps + [""] * max(0, 4-len(ps))
    p2, p3, p4 = p[1], p[2], p[3]
    oppose_words = STANCE_WORDS["oppose"] + ["အားနည်း", "ဆိုးကျိုး", "အပြစ်", "ချို့ယွင်း", "မသင့်"]
    support_words = STANCE_WORDS["support"] + ["အားသာ", "ကောင်းကျိုး", "အကျိုးရှိ", "အကျိုးကျေးဇူး"]
    reason_words = ["အကြောင်းမှာ", "အဘယ်ကြောင့်ဆိုသော်", "ထို့ကြောင့်", "ဥပမာ", "အထောက်အထား", "အကျိုးဆက်"]

    # 2 marks: position is started clearly in paragraph 2.
    stance2 = 2 if _contains_any(p2, STANCE_WORDS["support"] + STANCE_WORDS["oppose"]) else 0

    if kind == "balanced_two_sided":
        # Pattern 1: paragraph 3 = opposing weakness (3); paragraph 4 = own strength (3).
        opp3 = 3 if _contains_any(p3, oppose_words) else 0
        own3 = 3 if _contains_any(p4, support_words) else 0
        # Final 2 marks: conclusion confirms position in paragraph 4.
        conclusion2 = 2 if _contains_any(p4, ["နိဂုံး", "အနှစ်ချုပ်", "ထို့ကြောင့်", "သို့ဖြစ်၍", "အဆုံးတွင်", "မိမိရပ်တည်ချက်"]) else 0
        return {
            "pattern":"ပုံစံ – ၁",
            "pattern_label":"အကြောင်းအရာနှစ်ခု နှစ်ဖက်မျှအဆို",
            "position":stance2, "opposing_weakness":opp3,
            "own_strength":own3, "conclusion":conclusion2
        }

    if kind in ("balanced_pro_con", "comparative_many"):
        # Pattern J: each body paragraph combines both sides (3 each).
        def combo3(px):
            has_opp = _contains_any(px, oppose_words)
            has_own = _contains_any(px, support_words)
            return 3 if has_opp and has_own else (2 if has_opp or has_own else 0)
        body3 = combo3(p3)
        body4 = combo3(p4)
        conclusion2 = 2 if _contains_any(p4, ["နိဂုံး", "အနှစ်ချုပ်", "ထို့ကြောင့်", "သို့ဖြစ်၍", "အဆုံးတွင်", "မိမိရပ်တည်ချက်"]) else 0
        return {
            "pattern":"ပုံစံ – J",
            "pattern_label":TYPE_LABELS[kind],
            "position":stance2, "body_one":body3, "body_two":body4, "conclusion":conclusion2
        }

    # Pattern 3: own-side strengths in both body paragraphs.
    body3 = 3 if _contains_any(p3, support_words) else (2 if _contains_any(p3, reason_words) else 0)
    body4 = 3 if _contains_any(p4, support_words) else (2 if _contains_any(p4, reason_words) else 0)
    conclusion2 = 2 if _contains_any(p4, ["နိဂုံး", "အနှစ်ချုပ်", "ထို့ကြောင့်", "သို့ဖြစ်၍", "အဆုံးတွင်", "မိမိရပ်တည်ချက်"]) else 0
    return {
        "pattern":"ပုံစံ – ၃",
        "pattern_label":TYPE_LABELS[kind],
        "position":stance2, "body_one":body3, "body_two":body4, "conclusion":conclusion2
    }

def analyze_debate(text, title=""):
    text = (text or "").strip()
    kind = classify_proposition(title)
    stance = detect_stance(text, title)
    ps = _debate_paragraphs(text)
    grammar_highlights = _myanmar_grammar_highlights(text)
    spelling_highlights = check_myanmar_spelling(text)
    all_highlights = sorted(grammar_highlights + spelling_highlights, key=lambda x: (x["start"], x["end"]))

    rubric = _paragraph_score_flags(ps, kind, stance)
    # Exact 10 marks: 2 + 3 + 3 + 2.
    marks = int(rubric["position"] + rubric.get("opposing_weakness", rubric.get("body_one", 0))
                + rubric.get("own_strength", rubric.get("body_two", 0)) + rubric["conclusion"])
    # Penalize missing four-paragraph architecture only through the rubric itself;
    # keep the result bounded to ten.
    marks = max(0, min(10, marks))

    strengths, weaknesses, issues = [], [], []
    if len(ps) == 4:
        strengths.append("စာပိုဒ် ၄ ပိုဒ်ဖြင့် နိဒါန်း၊ စာကိုယ်နှင့် နိဂုံး ဖွဲ့စည်းထားသည်။")
    else:
        weaknesses.append(f"သတ်မှတ်ထားသော စာပိုဒ် ၄ ပိုဒ်အစား {len(ps)} ပိုဒ်သာ တွေ့ရသည်။")
        issues.append({"type":"structure","message":"နိဒါန်း + စာကိုယ် ၂ ပိုဒ် + နိဂုံး ပါဝင်သည့် ၄ ပိုဒ်ဖွဲ့စည်းပုံကို လိုက်နာပါ။"})

    if rubric["position"] == 2:
        strengths.append("ဒုတိယပိုဒ်တွင် မိမိရပ်တည်ချက်ကို အစပြုဖော်ပြထားသည်။")
    else:
        weaknesses.append("ဒုတိယပိုဒ်တွင် မိမိရပ်တည်ချက်ကို ရှင်းလင်းစွာ မစတင်သေးပါ။")
        issues.append({"type":"stance","message":"ဒုတိယပိုဒ်တွင် ထောက်ခံ/ကန့်ကွက် မိမိရပ်တည်ချက်ကို တိတိကျကျ စတင်ဖော်ပြပါ။"})

    if kind == "balanced_two_sided":
        if rubric["opposing_weakness"] < 3:
            weaknesses.append("တတိယပိုဒ်တွင် မိမိမရပ်တည်သောဘက်၏ အားနည်းချက်ကို ပိုမိုရှင်းလင်းစွာ ဖော်ပြပါ။")
        if rubric["own_strength"] < 3:
            weaknesses.append("စတုတ္ထပိုဒ်တွင် မိမိရပ်တည်သောဘက်၏ အားသာချက်ကို သက်သေ/ဥပမာဖြင့် ခိုင်မာစွာ ဖော်ပြပါ။")
    elif kind in ("balanced_pro_con", "comparative_many"):
        if rubric["body_one"] < 3:
            weaknesses.append("တတိယပိုဒ်တွင် ဆန့်ကျင်ဘက်၏ အားနည်းချက်နှင့် မိမိဘက်၏ အားသာချက် နှစ်မျိုးစလုံး ထည့်ပါ။")
        if rubric["body_two"] < 3:
            weaknesses.append("စတုတ္ထပိုဒ်တွင် ဆန့်ကျင်ဘက်၏ အားနည်းချက်နှင့် မိမိဘက်၏ အားသာချက် နှစ်မျိုးစလုံး ထည့်ပါ။")
    else:
        if rubric["body_one"] < 3 or rubric["body_two"] < 3:
            weaknesses.append("တတိယနှင့် စတုတ္ထပိုဒ်များတွင် မိမိရပ်တည်သည့်ဘက်၏ အားသာချက်များကို အကြောင်းပြချက်နှင့် ဥပမာများဖြင့် ဖော်ပြပါ။")

    if rubric["conclusion"] < 2:
        weaknesses.append("နိဂုံးတွင် မိမိရပ်တည်ချက်ကို ထပ်မံအတည်ပြုရန် လိုအပ်သည်။")
    else:
        strengths.append("နိဂုံးတွင် မိမိရပ်တည်ချက်ကို အတည်ပြုထားသည်။")

    for h in all_highlights[:20]:
        issues.append({"type":h["type"],"message":h["message"],"text":h.get("text"),"start":h.get("start"),"end":h.get("end"),"replacement":h.get("replacement")})

    if not issues:
        issues.append({"type":"structure","message":"အဆိုအချေ၏ သတ်မှတ်ပုံစံနှင့် ကိုက်ညီသော အဓိကအချက်များကို တွေ့ရသည်။"})

    score100 = marks * 10
    recommended = {
        "balanced_two_sided": [
            "၁။ နိဒါန်း — အဆို၏အဓိပ္ပါယ်နှင့် အကြောင်းအရာကို မိတ်ဆက်ပါ။",
            "၂။ စာကိုယ် — မိမိရပ်တည်ချက်ကို အစပြုပါ။ (၂ မှတ်)",
            "၃။ စာကိုယ် — မိမိမရပ်တည်သောဘက်၏ အားနည်းချက်များကို ရှင်းပြပါ။ (၃ မှတ်)",
            "၄။ စာကိုယ်/နိဂုံး — မိမိရပ်တည်သောဘက်၏ အားသာချက်များကို တင်ပြပြီး မိမိရပ်တည်ချက်ကို အတည်ပြုပါ။ (၃+၂ မှတ်)"
        ],
        "balanced_pro_con": [
            "၁။ နိဒါန်း — အဆိုကို မိတ်ဆက်ပါ။",
            "၂။ စာကိုယ် — မိမိရပ်တည်ချက်ကို အစပြုပါ။ (၂ မှတ်)",
            "၃။ စာကိုယ် — ဆန့်ကျင်ဘက်၏ အားနည်းချက် + မိမိဘက်၏ အားသာချက်။ (၃ မှတ်)",
            "၄။ စာကိုယ်/နိဂုံး — ဆန့်ကျင်ဘက်၏ အားနည်းချက် + မိမိဘက်၏ အားသာချက်၊ ထို့နောက် ရပ်တည်ချက်အတည်ပြုပါ။ (၃+၂ မှတ်)"
        ],
        "comparative_many": [
            "၁။ နိဒါန်း — နှိုင်းယှဉ်ရမည့် အကြောင်းအရာများကို မိတ်ဆက်ပါ။",
            "၂။ စာကိုယ် — မိမိရပ်တည်ချက်ကို အစပြုပါ။ (၂ မှတ်)",
            "၃။ စာကိုယ် — နှိုင်းယှဉ်ဘက်၏ အားနည်းချက် + မိမိဘက်၏ အားသာချက်။ (၃ မှတ်)",
            "၄။ စာကိုယ်/နိဂုံး — နှိုင်းယှဉ်ဘက်၏ အားနည်းချက် + မိမိဘက်၏ အားသာချက်၊ ထို့နောက် ရပ်တည်ချက်အတည်ပြုပါ။ (၃+၂ မှတ်)"
        ],
        "one_sided": [
            "၁။ နိဒါန်း — အဆိုကို မိတ်ဆက်ပါ။",
            "၂။ စာကိုယ် — မိမိရပ်တည်ချက်ကို အစပြုပါ။ (၂ မှတ်)",
            "၃။ စာကိုယ် — မိမိရပ်တည်သည့်ဘက်၏ အားသာချက်များ။ (၃ မှတ်)",
            "၄။ စာကိုယ်/နိဂုံး — မိမိရပ်တည်သည့်ဘက်၏ အားသာချက်များနှင့် ရပ်တည်ချက်အတည်ပြုခြင်း။ (၃+၂ မှတ်)"
        ]
    }[kind]

    return {
        "ok": True, "mode":"debate", "proposition_type":kind,
        "proposition_type_label":TYPE_LABELS[kind], "stance":stance,
        "stance_label":"ထောက်ခံ" if stance=="support" else "ကန့်ကွက်",
        "score":score100, "marks":marks, "max_marks":10,
        "paragraph_count":len(ps), "rubric_marks":rubric,
        "strengths":strengths[:8], "weaknesses":weaknesses[:8],
        "issues":issues[:12], "highlights":all_highlights,
        "grammar_check":{"available":bool(all_highlights),"message":"မြန်မာစာ စာလုံးပေါင်း၊ သတ်ပုံနှင့် သဒ္ဒါ/ရေးသားပုံကို စစ်ဆေးထားသည်။" if all_highlights else ""},
        "recommended_structure": recommended
    }

def generate_debate(title, stance="support", language="my", target_words=300):
    title = (title or "ပညာရေးသည် လူငယ်များအတွက် အရေးကြီးသည်").strip()
    kind = classify_proposition(title)
    stance = "oppose" if stance == "oppose" else "support"
    pos = "agree" if stance == "support" else "disagree"
    if language != "my":
        intro = f"Introduction: The proposition is “{title}”. I {pos} with it."
        p2 = f"First, I clearly {pos} with the proposition because the position can be supported by practical reasons and relevant evidence."
        if kind == "balanced_two_sided":
            p3 = "The opposing side has weaknesses that should be considered, including limitations, possible disadvantages, and situations where its argument is less convincing."
            p4 = f"On the other hand, my position has stronger practical advantages. These advantages can be supported with examples and cause-and-effect reasoning. In conclusion, the evidence supports my position on “{title}”."
        elif kind in ("balanced_pro_con", "comparative_many"):
            p3 = "The opposing side has limitations, while my preferred side has clear advantages when practical usefulness and likely outcomes are considered."
            p4 = "The opposing side also has weaknesses that reduce its strength, whereas my position offers more convincing benefits and evidence. In conclusion, I maintain this position."
        else:
            p3 = "My position has important advantages, including practical usefulness, positive outcomes, and stronger reasons for accepting the proposition."
            p4 = "A further advantage is that the position can be supported by relevant examples and consistent reasoning. In conclusion, these advantages confirm my position."
        return "\n\n".join([intro,p2,p3,p4])

    pos_mm = "ထောက်ခံ" if stance=="support" else "ကန့်ကွက်"
    intro = f"“{title}” ဟူသောအဆိုသည် ဆွေးနွေးသင့်သည့် အကြောင်းအရာတစ်ရပ်ဖြစ်သည်။ ဤအဆိုကို {pos_mm}သည့်ဘက်မှ ရပ်တည်၍ ကျိုးကြောင်းဆီလျော်စွာ ဆွေးနွေးမည်။"
    p2 = f"ပထမဦးစွာ မိမိသည် ဤအဆိုကို {pos_mm}သည်။ အကြောင်းမှာ အဆိုပါအမြင်သည် လက်တွေ့ဘဝတွင် အကျိုးရှိနိုင်သည့် အချက်များနှင့် ဆက်စပ်နေပြီး မိမိရပ်တည်ချက်ကို အကြောင်းပြချက်များဖြင့် ထောက်ခံနိုင်သောကြောင့် ဖြစ်သည်။"
    if kind == "balanced_two_sided":
        p3 = f"အခြားတစ်ဖက်တွင် {title} နှင့်ပတ်သက်၍ မတူညီသောအမြင်များ ရှိနိုင်သည်။ သို့သော် ထိုမရပ်တည်သောဘက်တွင် အကန့်အသတ်များ၊ ဆိုးကျိုးများနှင့် လက်တွေ့အခြေအနေအချို့တွင် အားနည်းနိုင်သည့်အချက်များ ရှိသည်။ ထို့ကြောင့် အဆိုပါဘက်၏ အားနည်းချက်များကို သေချာစွာ စဉ်းစားသင့်သည်။"
        p4 = f"တစ်ဖက်တွင် မိမိရပ်တည်သည့်ဘက်၌ အကျိုးကျေးဇူးများနှင့် အားသာချက်များ ပိုမိုထင်ရှားသည်။ ဥပမာအားဖြင့် လက်တွေ့အကျိုးရှိမှု၊ လူမှုဘဝအပေါ် ကောင်းသောသက်ရောက်မှုနှင့် ရေရှည်အကျိုးဖြစ်ထွန်းမှုတို့ကို တွေ့နိုင်သည်။ ထို့ကြောင့် အထက်ပါအကြောင်းပြချက်များအရ မိမိသည် ဤအဆိုကို {pos_mm}သည့်ဘက်တွင် ရပ်တည်သည်ဟု အတည်ပြုနိုင်သည်။"
    elif kind in ("balanced_pro_con", "comparative_many"):
        p3 = f"တစ်ဖက်တွင်လည်း ဆန့်ကျင်သည့်ဘက်၏ အားနည်းချက်များကို တွေ့နိုင်သည်။ ထိုအခက်အခဲများနှင့် ကန့်သတ်ချက်များရှိသော်လည်း မိမိရပ်တည်သည့်ဘက်၌ အကျိုးကျေးဇူး၊ အသုံးဝင်မှုနှင့် လက်တွေ့အောင်မြင်နိုင်မှုတို့က ပိုမိုအားကောင်းသည်။ ထို့ကြောင့် နှစ်ဖက်စလုံးကို မျှတစွာ စဉ်းစားပြီး မိမိဘက်၏ အားသာချက်ကို ဖော်ပြနိုင်သည်။"
        p4 = f"ထို့အပြင် ဆန့်ကျင်သည့်ဘက်တွင် ဖြစ်ပေါ်နိုင်သည့် ဆိုးကျိုးများနှင့် အားနည်းချက်များကို ထည့်သွင်းစဉ်းစားလျှင် မိမိရွေးချယ်သည့်ဘက်၏ ကောင်းကျိုးများ ပိုမိုထင်ရှားလာသည်။ ဥပမာများနှင့် အကြောင်းပြချက်များကလည်း မိမိရပ်တည်ချက်ကို ခိုင်မာစေသည်။ နိဂုံးချုပ်ရလျှင် မိမိသည် ဤအဆိုကို {pos_mm}သည့်ဘက်တွင် ရပ်တည်ကြောင်း အတည်ပြုသည်။"
    else:
        p3 = f"မိမိရပ်တည်သည့်ဘက်တွင် {title} နှင့် ဆက်စပ်သော အားသာချက်များစွာ ရှိသည်။ ထိုအားသာချက်များသည် လူတစ်ဦးချင်း၊ မိသားစုနှင့် လူမှုအသိုင်းအဝိုင်းအတွက် အကျိုးရှိစေနိုင်ပြီး လက်တွေ့ဘဝတွင်လည်း တွေ့မြင်နိုင်သည်။"
        p4 = f"ထို့အပြင် မိမိရပ်တည်သည့်ဘက်၏ အားသာချက်များမှာ ရေရှည်အကျိုးဖြစ်ထွန်းမှု၊ ယုံကြည်စိတ်ချရမှုနှင့် လက်တွေ့အသုံးဝင်မှုတို့ ဖြစ်သည်။ ထိုအချက်များကို ဥပမာများဖြင့် ခိုင်မာစွာ ဖော်ပြနိုင်သည်။ နိဂုံးချုပ်ရလျှင် အထက်ပါအကြောင်းပြချက်များကြောင့် မိမိသည် ဤအဆိုကို {pos_mm}သည့်ဘက်တွင် ရပ်တည်သည်။"
    return "\n\n".join([intro,p2,p3,p4])
