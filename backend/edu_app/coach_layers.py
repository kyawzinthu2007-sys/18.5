"""TSO Edu Personal Writing Coach layers.

Deterministic learning features built on top of the existing writing analysis:
1) Writing Coach guidance
2) Personal Writing Profile
3) Personalized Improvement Plan
4) TSO Writing Score
5) Before/After comparison
6) Mistake Memory

This module deliberately does not make another AI/API call. It turns the
existing analysis payload into durable, student-facing learning data.
"""
from datetime import datetime, timezone

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
SCORE_LABELS = {
    "grammar_accuracy": "Grammar accuracy",
    "grammar_complexity": "Grammar complexity",
    "vocabulary_range": "Vocabulary range",
    "vocabulary_precision": "Vocabulary precision",
    "cohesion": "Cohesion",
    "coherence": "Coherence",
    "task_relevance": "Task relevance",
    "sentence_variety": "Sentence variety",
    "development": "Idea development",
}

COACH_RULES = {
    "grammar_accuracy": (
        "Strengthen grammar accuracy first.",
        "Check articles, verb forms, agreement and sentence boundaries before adding more advanced vocabulary."
    ),
    "grammar_complexity": (
        "Build more controlled complex sentences.",
        "Practice combining ideas with although, whereas, because, which and other accurate clause structures."
    ),
    "vocabulary_range": (
        "Expand vocabulary range.",
        "Replace repeated basic words only when the alternative preserves the exact meaning and fits the context."
    ),
    "vocabulary_precision": (
        "Improve vocabulary precision.",
        "Choose words for meaning and collocation, not simply because they sound more advanced."
    ),
    "cohesion": (
        "Improve cohesion between ideas.",
        "Use linking words only when they accurately show contrast, cause, addition, sequence or consequence."
    ),
    "coherence": (
        "Make the argument easier to follow.",
        "Give each paragraph one clear controlling idea and connect each example back to the main argument."
    ),
    "task_relevance": (
        "Stay closer to the question.",
        "Make sure the thesis and every body paragraph directly answer the task rather than discussing a nearby topic."
    ),
    "sentence_variety": (
        "Increase sentence variety.",
        "Mix concise statements with controlled compound and complex sentences instead of repeating one pattern."
    ),
    "development": (
        "Develop ideas further.",
        "Support major claims with a reason, example, consequence or explanation instead of stopping after the claim."
    ),
}


def _next_level(level):
    try:
        i = LEVELS.index(str(level).upper())
    except ValueError:
        i = 0
    return LEVELS[min(len(LEVELS) - 1, i + 1)]


def _level_distance(a, b):
    try:
        return abs(LEVELS.index(str(a).upper()) - LEVELS.index(str(b).upper()))
    except ValueError:
        return 0


def build_coach_payload(result, text, title="", previous=None, history=None, mistakes=None):
    scores = result.get("scores") or {}
    overall = int(round(float(scores.get("overall", 0) or 0)))
    level = str(result.get("level") or "A1").upper()
    target = str(result.get("target_level") or _next_level(level)).upper()

    dimensions = []
    for key, label in SCORE_LABELS.items():
        if key in scores:
            try:
                value = int(round(float(scores[key])))
            except (TypeError, ValueError):
                continue
            dimensions.append({"key": key, "label": label, "score": value})
    dimensions.sort(key=lambda x: x["score"])
    weakest = dimensions[:3]
    strongest = sorted(dimensions, key=lambda x: x["score"], reverse=True)[:2]

    primary = weakest[0]["key"] if weakest else "grammar_accuracy"
    headline, action = COACH_RULES.get(primary, ("Keep improving", "Revise your weakest skill first."))

    # Sentence-boundary errors (comma splices, run-ons, fragments) make a
    # paragraph hard to follow no matter how the other dimensions score, so
    # when any are present in this analysis they override the generic
    # grammar-accuracy coaching line with a specific, actionable one naming
    # the actual problem rather than a general "check verb forms" note.
    boundary_issues = [
        i for i in (result.get("issues") or [])
        if any(k in str(i.get("message", "")) for k in ("comma splice", "run-on", "sentence fragment"))
    ]
    if boundary_issues:
        kinds = sorted({
            "comma splice" if "comma splice" in i["message"] else
            "run-on sentence" if "run-on" in i["message"] else
            "sentence fragment"
            for i in boundary_issues
        })
        headline = "Fix sentence boundaries first."
        action = (
            f"This paragraph has at least one {', '.join(kinds)}. "
            "A reader can't follow the argument until every sentence is one complete, correctly joined idea — "
            "fix these before working on vocabulary or advanced structures."
        )

    coach = {
        "headline": headline,
        "action": action,
        "priority": [{"skill": x["label"], "score": x["score"], "key": x["key"]} for x in weakest],
        "strengths": [{"skill": x["label"], "score": x["score"], "key": x["key"]} for x in strongest],
        "nextTarget": target,
        "tip": f"Your next stretch target is {target}. Improve the lowest-scoring skill before chasing more advanced vocabulary.",
    }

    comparison = {"available": False}
    if previous and isinstance(previous, dict):
        prev_score = int(previous.get("tsoScore", 0) or 0)
        prev_level = str(previous.get("level") or "A1")
        delta = overall - prev_score
        comparison = {
            "available": True,
            "previousScore": prev_score,
            "currentScore": overall,
            "delta": delta,
            "previousLevel": prev_level,
            "currentLevel": level,
            "message": (f"+{delta} points since your previous saved analysis." if delta > 0 else
                        f"{delta} points since your previous saved analysis." if delta < 0 else
                        "Your score is unchanged from the previous saved analysis."),
        }

    # Build a concrete 30-day plan from the three weakest dimensions.
    # The plan is deliberately small and repeatable so learners can complete one
    # visible action each day instead of receiving a vague monthly goal.
    plan_skills = weakest[:3] if weakest else []
    skill_names = [x["label"] for x in plan_skills] or ["Overall writing quality"]
    phases = [
        (1, 7, "Foundation", "Notice the pattern", "Learn the rule, study examples, and correct short sentences."),
        (8, 14, "Practice", "Build control", "Write short responses that deliberately use the target skill."),
        (15, 21, "Application", "Use it in context", "Apply the skill to paragraphs and an IELTS-style task."),
        (22, 28, "Challenge", "Write with confidence", "Complete timed writing and revise your weakest area."),
        (29, 30, "Check-in", "Measure the change", "Take a fresh analysis and compare it with your baseline."),
    ]
    day_actions = [
        "Learn one rule and write 3 examples.", "Correct 5 sentences and explain each correction.",
        "Rewrite 5 basic sentences with better control.", "Write a 70-word paragraph using today's skill.",
        "Find 5 examples in your own writing and fix them.", "Complete a 10-minute focused practice.",
        "Weekly check: write a short paragraph and self-score it.",
    ]
    plan = []
    for day in range(1, 31):
        phase = next(x for x in phases if x[0] <= day <= x[1])
        skill = skill_names[(day - 1) % len(skill_names)]
        action = day_actions[(day - 1) % len(day_actions)]
        if day == 14: action = "Checkpoint: repeat your Day 1 exercise and compare accuracy."
        if day == 21: action = "Checkpoint: write one complete body paragraph without using your notes."
        if day == 29: action = "Baseline review: revisit your first analysis and choose one final target."
        if day == 30: action = "Final assessment: analyze a fresh essay and celebrate your progress."
        plan.append({"day": day, "phase": phase[2], "skill": skill, "focus": phase[3], "task": action})

    # Extract a compact recurring-mistake record from the current analysis.
    current_mistakes = []
    for issue in (result.get("issues") or [])[:20]:
        message = str(issue.get("message") or "")
        # Sentence-boundary errors get their own specific category instead
        # of the generic "grammar" bucket, so mistake memory can show a
        # learner "you have 6 recurring run-on sentences" rather than
        # burying that pattern inside a broad, less actionable "grammar"
        # count alongside unrelated article/tense errors.
        if "comma splice" in message:
            category = "comma_splice"
        elif "run-on" in message:
            category = "run_on_sentence"
        elif "sentence fragment" in message:
            category = "sentence_fragment"
        else:
            category = str(issue.get("type") or issue.get("category") or "writing").lower()
        text_value = str(issue.get("text") or issue.get("message") or "").strip()
        replacement = issue.get("replacement")
        if not text_value:
            continue
        current_mistakes.append({
            "category": category,
            "text": text_value[:180],
            "replacement": str(replacement)[:120] if replacement else None,
            "count": 1,
        })
    for suggestion in (result.get("suggestions") or [])[:20]:
        if str(suggestion.get("category", "")).lower() == "repetition":
            word = str(suggestion.get("word") or "").strip()
            if word:
                current_mistakes.append({"category": "repetition", "text": word[:100], "replacement": suggestion.get("replacement"), "count": int(suggestion.get("count", 2) or 2)})

    # Merge by normalized text/category so recurring errors become memory.
    merged = {}
    for item in list(mistakes or []) + current_mistakes:
        key = (item.get("category", ""), str(item.get("text", "")).strip().lower())
        if not key[1]:
            continue
        old = merged.get(key)
        if old:
            old["count"] = int(old.get("count", 1)) + int(item.get("count", 1) or 1)
            if item.get("replacement"):
                old["replacement"] = item["replacement"]
        else:
            merged[key] = dict(item)
    mistake_memory = list(merged.values())
    mistake_memory.sort(key=lambda x: (-int(x.get("count", 1) or 1), x.get("text", "")))
    mistake_memory = mistake_memory[:20]

    history_entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "title": str(title or "")[:160],
        "tsoScore": overall,
        "level": level,
        "targetLevel": target,
        "wordCount": int((result.get("stats") or {}).get("words", 0) or 0),
    }
    new_history = list(history or [])[-11:] + [history_entry]

    profile = {
        "tsoScore": overall,
        "level": level,
        "targetLevel": target,
        "essayCount": len(new_history),
        "dimensions": dimensions,
        "topStrengths": coach["strengths"],
        "prioritySkills": coach["priority"],
        "lastUpdated": history_entry["at"],
        "history": new_history,
        "mistakes": mistake_memory,
        "improvementPlan": plan,
    }
    return {
        "coach": coach,
        "comparison": comparison,
        "profile": profile,
        "mistakes": mistake_memory,
        "historyEntry": history_entry,
    }
