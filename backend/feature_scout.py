
"""
TSO Feature Scout — discover public website features and prepare safe
feature proposals for creator approval.

This module intentionally analyzes public pages rather than copying source
code, private content, credentials, cookies, or protected UI. It honors
robots.txt, uses a small request timeout, and keeps extracted content short.
"""
import json, os, re, time, uuid, urllib.parse, urllib.request, urllib.error
import urllib.robotparser
from html.parser import HTMLParser
from datetime import datetime, timezone

from ai_provider import call_ai

FEATURE_SCOUT_USER_AGENT = os.getenv(
    "FEATURE_SCOUT_USER_AGENT", "TalentshowoffFeatureScout/1.0 (+https://talentshowoff.com)"
)
FEATURE_SCOUT_TIMEOUT = int(os.getenv("FEATURE_SCOUT_TIMEOUT", "12"))
FEATURE_SCOUT_MAX_PAGES = max(1, min(int(os.getenv("FEATURE_SCOUT_MAX_PAGES", "5")), 10))
FEATURE_SCOUT_MAX_CHARS = max(1000, min(int(os.getenv("FEATURE_SCOUT_MAX_CHARS", "18000")), 30000))


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.headings, self.buttons, self.links = "", [], [], []
        self._tag = None
        self._buf = []
    def handle_starttag(self, tag, attrs):
        self._tag = tag.lower()
        attrs = dict(attrs)
        if tag.lower() == "a" and attrs.get("href"):
            self.links.append((self._clean(attrs.get("href")), self._clean(attrs.get("aria-label") or "")))
        if tag.lower() in ("button", "summary"):
            self._buf = []
    def handle_endtag(self, tag):
        tag = tag.lower()
        text = self._clean(" ".join(self._buf))
        if tag == "title" and text: self.title = text[:300]
        if tag in ("h1","h2","h3") and text and text not in self.headings: self.headings.append(text[:180])
        if tag in ("button","summary") and text and text not in self.buttons: self.buttons.append(text[:120])
        self._buf = []
        self._tag = None
    def handle_data(self, data):
        if self._tag in ("title","h1","h2","h3","button","summary"):
            self._buf.append(data)
    @staticmethod
    def _clean(s):
        return re.sub(r"\s+", " ", s or "").strip()


def _allowed(url):
    p = urllib.parse.urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc)


def _robots_allows(url):
    p = urllib.parse.urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        with urllib.request.urlopen(
            urllib.request.Request(robots_url, headers={"User-Agent": FEATURE_SCOUT_USER_AGENT}),
            timeout=min(FEATURE_SCOUT_TIMEOUT, 6),
        ) as r:
            rp.parse(r.read().decode("utf-8", errors="ignore").splitlines())
        return rp.can_fetch(FEATURE_SCOUT_USER_AGENT, url), rp
    except Exception:
        # A missing/unreachable robots file is not proof of permission. We
        # permit the public page request but keep it tightly rate limited.
        return True, rp


def fetch_public_page(url):
    if not _allowed(url):
        raise ValueError("Only http/https public URLs are supported.")
    allowed, _ = _robots_allows(url)
    if not allowed:
        raise PermissionError("robots.txt does not allow the Feature Scout to inspect this URL.")
    req = urllib.request.Request(url, headers={"User-Agent": FEATURE_SCOUT_USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=FEATURE_SCOUT_TIMEOUT) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype and ctype:
            raise ValueError("The target is not an HTML page.")
        raw = r.read(FEATURE_SCOUT_MAX_CHARS * 3)
    parser = _PageParser()
    parser.feed(raw.decode("utf-8", errors="ignore"))
    base = f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"
    links = []
    for href, label in parser.links:
        try:
            absolute = urllib.parse.urljoin(url, href)
            p = urllib.parse.urlparse(absolute)
            if p.netloc == urllib.parse.urlparse(url).netloc and p.scheme in ("http","https"):
                links.append({"url": absolute, "label": label})
        except Exception:
            pass
    return {
        "url": url, "title": parser.title, "headings": parser.headings[:20],
        "buttons": parser.buttons[:30], "links": links[:60],
    }


def search_public_web(query, limit=5):
    # DuckDuckGo HTML is used only as a discovery index. We do not submit
    # credentials, cookies, or user-specific data.
    q = urllib.parse.quote_plus(query[:300])
    url = "https://html.duckduckgo.com/html/?q=" + q
    req = urllib.request.Request(url, headers={"User-Agent": FEATURE_SCOUT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=FEATURE_SCOUT_TIMEOUT) as r:
        text = r.read().decode("utf-8", errors="ignore")
    results = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.I|re.S):
        href = re.sub("<[^>]+>", "", m.group(1))
        title = re.sub("<[^>]+>", "", m.group(2))
        href = urllib.parse.unquote(href)
        # DDG may wrap destination URLs in uddg=
        parsed = urllib.parse.urlparse(href)
        if "uddg" in urllib.parse.parse_qs(parsed.query):
            href = urllib.parse.parse_qs(parsed.query)["uddg"][0]
        if _allowed(href):
            results.append({"url": href, "title": re.sub(r"\s+", " ", title).strip()[:200]})
        if len(results) >= limit: break
    return results


def analyze_sources(query, urls, current_features):
    candidates = []
    for u in urls[:FEATURE_SCOUT_MAX_PAGES]:
        try:
            page = fetch_public_page(u)
            candidates.append(page)
            time.sleep(0.5)
        except Exception as e:
            candidates.append({"url": u, "error": str(e)})
    prompt = """You are TSO Feature Scout. Compare public website feature patterns
with Talentshowoff's current product. Do NOT copy source code, text, images, branding,
or proprietary implementation. Identify product-level ideas that could be independently
implemented. Reject features that require private access, credential scraping, copyright
copying, or unsafe automation.

Return JSON with:
summary, features:[{name, value, evidence_urls, complexity(low|medium|high),
risk(low|medium|high), recommendation, implementation_steps}], duplicate_features.
Current features: %s
Research request: %s
Public page observations: %s
""" % (json.dumps(current_features, ensure_ascii=False), query, json.dumps(candidates, ensure_ascii=False)[:FEATURE_SCOUT_MAX_CHARS])
    result = call_ai(prompt.split("Return JSON with:",1)[0], prompt, max_tokens=1800)
    try:
        data = json.loads(result)
    except Exception:
        data = {"summary": result, "features": [], "duplicate_features": []}
    data["sources"] = candidates
    return data


def build_draft(feature):
    prompt = """Create an independent implementation draft for a feature proposal on
Talentshowoff. Never reproduce another site's source code, exact copy, private APIs,
assets, or distinctive branding. Use the proposal only as product inspiration.
Return JSON: title, user_story, acceptance_criteria (array), backend_plan (array),
frontend_plan (array), data_changes (array), security_notes (array), test_plan (array).
Feature proposal: %s""" % json.dumps(feature, ensure_ascii=False)
    result = call_ai(prompt.split("Return JSON:",1)[0], prompt, max_tokens=1800)
    try: return json.loads(result)
    except Exception: return {"title": feature.get("name","Feature"), "draft_text": result}


def scout_id():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Safe implementation builder / GitHub integration
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()  # owner/repository
GITHUB_BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "main").strip() or "main"
GITHUB_API = "https://api.github.com"


def _github_request(path, method="GET", payload=None):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise RuntimeError("GitHub integration is not configured. Set GITHUB_TOKEN and GITHUB_REPO.")
    req = urllib.request.Request(
        GITHUB_API + path,
        method=method,
        headers={
            "Authorization": "Bearer " + GITHUB_TOKEN,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "TalentshowoffFeatureScout/1.0",
            "Content-Type": "application/json",
        },
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
    )
    try:
        with urllib.request.urlopen(req, timeout=FEATURE_SCOUT_TIMEOUT) as r:
            raw = r.read().decode("utf-8", errors="ignore")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError("GitHub API %s: %s" % (e.code, detail[:500]))


def github_repository():
    return _github_request("/repos/" + GITHUB_REPO)


def github_default_branch():
    repo = github_repository()
    return (repo.get("default_branch") or "").strip()


def resolve_github_base_branch():
    """Resolve the branch to build from.

    Never assume 'main' exists. Prefer the configured branch when it exists;
    otherwise use the repository's real default branch. This fixes repositories
    whose default branch is master, trunk, develop, etc.
    """
    repo = github_repository()
    default = (repo.get("default_branch") or "").strip()
    candidates = []
    for b in (GITHUB_BASE_BRANCH, default):
        if b and b not in candidates:
            candidates.append(b)
    for branch in candidates:
        try:
            _github_request("/repos/%s/branches/%s" % (GITHUB_REPO, urllib.parse.quote(branch, safe="")), "GET")
            return branch
        except Exception:
            continue
    raise RuntimeError(
        "No usable GitHub base branch was found. Checked: %s. Repository default: %s."
        % (", ".join(candidates) or "(none)", default or "(unknown)")
    )


def build_code(feature, draft):
    """Ask TSO AI for an independent, reviewable code patch.

    The model returns file-level changes only. The result is stored for creator
    review; it is NOT written to production automatically.
    """
    prompt = """You are the Talentshowoff implementation engineer.
Create an independent implementation for the approved product feature below.
Work with the existing Flask + PostgreSQL/Supabase + plain React/Babel frontend
architecture. Do not copy another site's source code, assets, branding, or
private APIs.

Return STRICT JSON:
{
  "summary": "...",
  "tests": ["..."],
  "files": [
    {"path":"relative/path.py","operation":"add|modify",
     "code":"complete file content or a complete replacement section"}
  ],
  "integration_notes": ["..."],
  "rollback_notes": ["..."]
}

Rules:
- Keep changes minimal and compatible with the existing project.
- Never include secrets, API keys, passwords, cookies, or tokens.
- For an existing file, provide a complete replacement file only when practical;
  otherwise provide a clearly delimited replacement block with enough context
  for a human reviewer.
- Do not claim the code has been executed.
Feature proposal:
%s

Existing implementation draft:
%s
""" % (json.dumps(feature, ensure_ascii=False), json.dumps(draft, ensure_ascii=False))
    result = call_ai(prompt.split("Return STRICT JSON:", 1)[0], prompt, max_tokens=5000)
    try:
        data = json.loads(result)
        if not isinstance(data, dict) or not isinstance(data.get("files"), list):
            raise ValueError("AI returned an invalid code plan.")
        return data
    except Exception:
        return {
            "summary": "The AI returned a non-JSON implementation draft. Manual review is required.",
            "files": [],
            "raw": result[:12000],
            "integration_notes": [],
            "rollback_notes": [],
        }


def _github_file_sha(path, branch):
    try:
        obj = _github_request(
            "/repos/%s/contents/%s?ref=%s" % (
                GITHUB_REPO,
                urllib.parse.quote(path, safe="/"),
                urllib.parse.quote(branch, safe="")
            )
        )
        return obj.get("sha")
    except Exception:
        return None


def create_feature_branch_and_commit(proposal_id, title, code_plan):
    """Create a review branch from the actual repository default/base branch.

    This intentionally does not merge or deploy. Creator approval only creates
    a reviewable GitHub branch/commit; production still requires a normal PR
    merge/deployment.
    """
    base = resolve_github_base_branch()
    ref = _github_request("/repos/%s/git/ref/heads/%s" % (GITHUB_REPO, urllib.parse.quote(base, safe="")))
    base_sha = ref.get("object", {}).get("sha")
    if not base_sha:
        raise RuntimeError("GitHub base branch '%s' has no commit SHA." % base)

    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", (title or "feature").lower()).strip("-")[:48] or "feature"
    branch = "tso-feature/%s-%s" % (safe, proposal_id[:8])
    _github_request(
        "/repos/%s/git/refs" % GITHUB_REPO,
        "POST",
        {"ref": "refs/heads/" + branch, "sha": base_sha},
    )

    committed = []
    for item in (code_plan.get("files") or [])[:30]:
        path = str(item.get("path") or "").lstrip("/")
        code = item.get("code")
        if not path or not isinstance(code, str) or not code.strip():
            continue
        if path.startswith(".git/") or path.startswith(".env") or "secret" in path.lower():
            continue
        sha = _github_file_sha(path, branch)
        payload = {
            "message": "feat: TSO Feature Scout - %s" % (title or "feature"),
            "content": base64.b64encode(code.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        _github_request(
            "/repos/%s/contents/%s" % (GITHUB_REPO, urllib.parse.quote(path, safe="/")),
            "PUT",
            payload,
        )
        committed.append(path)

    return {
        "repository": GITHUB_REPO,
        "base_branch": base,
        "branch": branch,
        "files": committed,
        "review_url": "https://github.com/%s/tree/%s" % (GITHUB_REPO, urllib.parse.quote(branch, safe="")),
    }
