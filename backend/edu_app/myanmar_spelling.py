"""Conservative offline Myanmar spelling/orthography checker.

This is a deterministic student-proofreading aid, not a complete Myanmar
orthographic dictionary. It only flags high-confidence common misspellings
and spacing/word-form errors so that it does not over-correct acceptable
regional or stylistic variants.
"""
import re

# Strong, commonly seen student misspellings -> standard form.
# Keep this list conservative; add entries only when the correction is clear.
COMMON_MISSPELLINGS = {
    "အခြေနေ": "အခြေအနေ",
    "ဖြစ်နိုင်ချေ": "ဖြစ်နိုင်ခြေ",
    "သဘောတူညီမူ": "သဘောတူညီမှု",
    "လုပ်ဆောင်မူ": "လုပ်ဆောင်မှု",
    "တိုးတက်မူ": "တိုးတက်မှု",
    "ကျဆင်းမူ": "ကျဆင်းမှု",
    "ပြောင်းလဲမူ": "ပြောင်းလဲမှု",
    "တာဝန်ယူမူ": "တာဝန်ယူမှု",
    "ပူးပေါင်းဆောင်ရွက်မူ": "ပူးပေါင်းဆောင်ရွက်မှု",
    "ပါဝင်မူ": "ပါဝင်မှု",
    "အသုံးပြုမူ": "အသုံးပြုမှု",
    "ဖွံ့ဖြိုးမူ": "ဖွံ့ဖြိုးမှု",
    "အောင်မြင်မူ": "အောင်မြင်မှု",
    "ကျရှုံးမူ": "ကျရှုံးမှု",
    "လိုက်နာမူ": "လိုက်နာမှု",
    "လေ့လာမူ": "လေ့လာမှု",
    "ထိန်းသိမ်းမူ": "ထိန်းသိမ်းမှု",
    "တားဆီးမူ": "တားဆီးမှု",
    "ကာကွယ်မူ": "ကာကွယ်မှု",
    "စီမံခန့်ခွဲမူ": "စီမံခန့်ခွဲမှု",
    "သတ်မှတ်မူ": "သတ်မှတ်မှု",
    "ဆက်လက်မူ": "ဆက်လက်မှု",
    "အကျိုးသက်ရောက်မူ": "အကျိုးသက်ရောက်မှု",
    "ဆုံးဖြတ်မူ": "ဆုံးဖြတ်မှု",
    "တောင်းဆိုမူ": "တောင်းဆိုမှု",
    "ပေးအပ်မူ": "ပေးအပ်မှု",
    "ဖြည့်ဆည်းမူ": "ဖြည့်ဆည်းမှု",
    "လျှော့ချမူ": "လျှော့ချမှု",
    "မြှင့်တင်မူ": "မြှင့်တင်မှု",
    "စောင့်ကြည့်မူ": "စောင့်ကြည့်မှု",
    "အသိအမှတ်ပြုမူ": "အသိအမှတ်ပြုမှု",
    "မှတ်တမ်းတင်မူ": "မှတ်တမ်းတင်မှု",
    "အကဲဖြတ်မူ": "အကဲဖြတ်မှု",
    "ပြန်လည်သုံးသပ်မူ": "ပြန်လည်သုံးသပ်မှု",
    "အာရုံစိုက်မူ": "အာရုံစိုက်မှု",
    "ဆက်သွယ်မူ": "ဆက်သွယ်မှု",
    "ဆွေးနွေးမူ": "ဆွေးနွေးမှု",
    "ယှဉ်ပြိုင်မူ": "ယှဉ်ပြိုင်မှု",
    "ရွေးချယ်မူ": "ရွေးချယ်မှု",
    "အတည်ပြုမူ": "အတည်ပြုမှု",
}


def _is_myanmar(ch):
    return '\u1000' <= ch <= '\u109f'


def check_myanmar_spelling(text, limit=80):
    """Return editor-compatible red-underline spelling findings."""
    text = text or ""
    findings = []
    occupied = []
    for wrong, correct in COMMON_MISSPELLINGS.items():
        start = 0
        while True:
            pos = text.find(wrong, start)
            if pos < 0:
                break
            end = pos + len(wrong)
            # Myanmar words are often written directly next to particles
            # such as “သည်/ကြောင့်/မှု”. Exact dictionary matches are therefore
            # intentionally allowed inside a longer Myanmar phrase.
            if not any(not (end <= a or pos >= b) for a, b in occupied):
                findings.append({
                    'start': pos, 'end': end, 'text': wrong,
                    'replacement': correct,
                    'type': 'spelling', 'category': 'spelling',
                    'message': f'သတ်ပုံမှားနိုင်သည် — “{wrong}” အစား “{correct}” ဟု ရေးပါ။',
                    'detail': 'မြန်မာစာ သတ်ပုံစစ်ဆေးမှု — အင်တာနက်မှ စိစစ်ထားသော သတ်ပုံအရင်းအမြစ်များ + conservative rule-based database'
                })
                occupied.append((pos, end))
            start = end
            if len(findings) >= limit:
                return sorted(findings, key=lambda x: x['start'])
    return sorted(findings, key=lambda x: x['start'])

# Internet-researched expansion (2026-08-20).
# Sources reviewed:
# - Myanmar Computer Federation: Myanmar Spelling Book / 2003 Myanmar Language Commission edition
# - kanaung/wordlists: 13,574-line Myanmar spelling-book word list
# - Myanmar proverbs spelling reference: common correct/incorrect pairs
# - mySpellCorrect: statistical Burmese spelling-correction approach
# These entries are conservative: only clear correction pairs are auto-replaced.
INTERNET_COMMON_MISSPELLINGS = {
    "နုတ်ထွက်": "နုတ်ထွက်", # canonical guard; kept out of wrong-map below
}

# Common errors reported by online Myanmar spelling references.
# wrong -> correct
INTERNET_CORRECTIONS = {
    "နှုတ်ထွက်":"နုတ်ထွက်", "အမှီလိုက်":"အမီလိုက်", "အခန်းအနား":"အခမ်းအနား",
    "နေ့လည်":"နေ့လယ်", "ရလာဒ်":"ရလဒ်", "ရာနှုံး":"ရာနှုန်း", "ရန်ညှိုး":"ရန်ငြိုး",
    "ရံပုံငွေ":"ရန်ပုံငွေ", "တုန့်ပြန်":"တုံ့ပြန်", "ရုတ်သိမ်း":"ရုပ်သိမ်း",
    "စီစစ်":"စိစစ်", "ရှုတ်ချည်နှပ်ချည်":"ရှုံ့ချည်နှပ်ချည်", "ရှုပ်ချ":"ရှုတ်ချ",
    "ရှုတ်ထွေး":"ရှုပ်ထွေး", "ဂတိဂဝတ်":"ကတိကဝတ်", "ကထဲက":"ကတည်းက",
    "ချစ်ကုတ်":"ခြစ်ကုတ်", "ချိုးခြံ":"ခြိုးခြံ", "ချက်ခြင်း":"ချက်ချင်း",
    "ပရိတ်သတ်":"ပရိသတ်", "ဂရုဏာ":"ကရုဏာ", "သံဓိဋ္ဌာန်":"သန္နိဋ္ဌာန်",
    "ဘေးဥပါဒ်":"ဘေးဥပဒ်", "အာရုဏ်ဦး":"အရုဏ်ဦး", "ဒါဏ်ကြေး":"ဒဏ်ကြေး",
    "အနာဂါတ်":"အနာဂတ်", "ဟေမာန်":"ဟေမန်", "သာမာန်":"သာမန်",
    "စကြာဝဠာ":"စကြဝဠာ", "စံပါယ်ပန်း":"စံပယ်ပန်း", "လှည်းယာဉ်":"လှည်းယဉ်",
    "အကျိုးကျေးဇူးများစွာရှိသည့်":"အကျိုးကျေးဇူးများစွာရှိသည့်",
    "ဖြစ်ပါသည့်":"ဖြစ်ပါသည်", "ပြုလုပ်မည့်":"ပြုလုပ်မည့်", "ရေးသားမည့်":"ရေးသားမည့်",
    "ဆောင်ရွက်မည့်":"ဆောင်ရွက်မည့်", "ရှိသည့်":"ရှိသည့်", "သုံးသည့်":"သုံးသည့်",
    "အသုံးပြုသည့်":"အသုံးပြုသည့်", "လုပ်ဆောင်သည့်":"လုပ်ဆောင်သည့်",
    "အဲဒီ":"အဲဒီ", "အဲ့ဒီ":"အဲဒီ", "အဲ့အစား":"အဲဒီအစား",
    "တစ်ချို့":"တချို့", "တချို့သော":"တချို့သော", "တခါ":"တစ်ခါ",
    "တခု":"တစ်ခု", "တခြား":"တခြား", "တကယ်လို့":"တကယ်လို့",
}

# Remove no-op entries and merge web-researched corrections before checking.
for _wrong, _correct in INTERNET_CORRECTIONS.items():
    if _wrong != _correct:
        COMMON_MISSPELLINGS.setdefault(_wrong, _correct)

SPELLING_SOURCES = [
    {
        "name": "Myanmar Computer Federation — Myanmar Spelling Book",
        "url": "https://mcf.org.mm/myanmar-unicode/1876.html",
        "note": "References the Myanmar Language Commission's 2003 Myanmar Spelling Book."
    },
    {
        "name": "kanaung/wordlists — Myanmar spelling book word list",
        "url": "https://github.com/kanaung/wordlists/blob/master/%E1%80%99%E1%80%BC%E1%80%94%E1%80%99%E1%80%AC%E2%80%8B%E1%80%85%E1%80%AC%E1%80%9C%E1%80%AF%E1%80%B6%E1%80%B8%E2%80%8B%E1%80%95%E1%80%B1%E1%80%AB%E1%80%84%E1%80%BA%E1%80%B8%E2%80%8B%20%E1%80%9E%E1%80%90%E1%80%BA%E1%80%95%E1%80%AF%E1%80%B6%E1%80%80%E1%80%BB%E1%80%99%E1%80%BA%E1%80%B8%E2%80%8B.txt",
        "note": "Public 13,574-line spelling-book word list for segmentation and spellchecking."
    },
    {
        "name": "Myanmar Proverbs — common spelling errors",
        "url": "https://www.mmproverbs.pro/",
        "note": "Provides common correct/incorrect spelling pairs and cites Myanmar dictionaries/spelling references."
    },
    {
        "name": "mySpellCorrect — Burmese statistical spelling correction",
        "url": "https://github.com/thuraaungjune/mySpellCorrect",
        "note": "Uses n-gram/SymSpell methods for Burmese spelling correction."
    }
]
