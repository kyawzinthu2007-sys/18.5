"""
Idea Map / Architecture Sketch generator for TSO Edu.

Turns an essay into:
  1. A structural diagram (SVG): thesis -> paragraph main ideas -> supporting
     points, built entirely from the essay's own text using lightweight
     heuristics (paragraph splitting, topic-sentence detection, connector
     words). No external AI/LLM call — self-contained, deterministic, free.
  2. An optional "artistic sketch" layer: decorative hand-drawn-style shapes
     (organic blobs, connecting flourishes) rendered around the diagram for
     visual flavour. Also pure SVG, no image-generation API.

Both are returned as SVG markup strings so the frontend can drop them
straight into the DOM (or offer them as a downloadable .svg file).
"""

import re
import math
import random
import html as htmllib

from .writing_coach import sentences, words, TRANSITIONS

# ---------------------------------------------------------------------------
# 1. Structural extraction
# ---------------------------------------------------------------------------

_ALL_CONNECTORS = sorted({w for lvl in TRANSITIONS.values() for w in lvl}, key=len, reverse=True)

_OPENER_MARKERS = [
    'i agree', 'i disagree', 'i believe', 'in my opinion', 'i would argue', 'i argue',
    'this essay argues', 'this essay will', 'i strongly believe', 'i partly agree',
    'i completely agree', 'i do not agree', 'should', 'ought to', 'is beneficial',
    'is harmful', 'advantages outweigh', 'disadvantages outweigh', 'both views',
]

_FIRST_PARA_HINTS = ['first', 'firstly', 'to begin', 'one reason', 'one of the main',
                      'the first', 'primarily', 'to start']
_LAST_PARA_HINTS = ['in conclusion', 'to conclude', 'to sum up', 'overall', 'in summary',
                     'taken together', 'on balance', 'ultimately', 'finally']


def _split_paragraphs(text):
    """Split on blank lines; fall back to sentence-count chunking if the
    essay was pasted as one dense block with no paragraph breaks."""
    raw = [p.strip() for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    if len(raw) >= 2:
        return raw
    # single block: chunk into ~3-5 sentence groups so we still get a map
    ss = sentences(text)
    if not ss:
        return [text.strip()] if text.strip() else []
    chunk_size = max(2, math.ceil(len(ss) / 4))
    return [' '.join(ss[i:i + chunk_size]) for i in range(0, len(ss), chunk_size)]


def _topic_sentence(paragraph):
    """Heuristic: the topic sentence is usually the first sentence, unless a
    later sentence carries a stronger connector/position marker."""
    ss = sentences(paragraph)
    if not ss:
        return '', []
    best_idx = 0
    best_score = -1
    for i, s in enumerate(ss):
        low = s.lower()
        score = 0
        if i == 0:
            score += 2
        for m in _OPENER_MARKERS:
            if m in low:
                score += 2
        for c in _ALL_CONNECTORS:
            if re.search(rf'\b{re.escape(c)}\b', low):
                score += 1
                break
        if score > best_score:
            best_score = score
            best_idx = i
    topic = ss[best_idx]
    support = [s for j, s in enumerate(ss) if j != best_idx]
    return topic, support


def _shorten(s, limit=70):
    s = re.sub(r'\s+', ' ', s).strip()
    if len(s) <= limit:
        return s
    cut = s[:limit].rsplit(' ', 1)[0]
    return cut + '…'


def _gist_main_point(paragraph, topic, limit=78):
    """Create a concise gist for a paragraph instead of dumping its first
    sentence into the map. The gist keeps the paragraph's central claim and
    removes common introductory/filler phrases."""
    ss = sentences(paragraph)
    base = topic or (ss[0] if ss else paragraph)
    base = re.sub(r'^\s*(firstly|first of all|to begin with|in addition|moreover|furthermore|however|therefore|thus|overall|in conclusion|to conclude)[,:]\s*', '', base, flags=re.I)
    # Prefer the first two content clauses when a sentence is very long.
    base = re.sub(r'\s+', ' ', base).strip(' ,;:')
    return _shorten(base, limit)


def _label_for_paragraph(idx, total, topic_low):
    if idx == 0:
        return 'Introduction / Thesis'
    if idx == total - 1 and total > 2:
        for h in _LAST_PARA_HINTS:
            if h in topic_low:
                return 'Conclusion'
    for h in _FIRST_PARA_HINTS:
        if h in topic_low:
            return f'Main Point {idx}'
    return f'Main Point {idx}'


def extract_structure(text, essay_title=None):
    """Return a structure dict:
    {
      'thesis': str,
      'branches': [ {'label': str, 'topic': str, 'supports': [str, ...]}, ... ]
    }
    """
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return {'thesis': '', 'branches': []}

    branches = []
    thesis = essay_title.strip() if essay_title and essay_title.strip() else ''

    for idx, para in enumerate(paragraphs):
        topic, support = _topic_sentence(para)
        if not topic:
            continue
        label = _label_for_paragraph(idx, len(paragraphs), topic.lower())
        if idx == 0 and not thesis:
            thesis = _shorten(topic, 90)
            # The essay's own opening topic sentence becomes the thesis
            # node itself, so it doesn't also need a separate branch.
            # Only add an "Introduction" branch if the intro paragraph
            # develops a distinct supporting idea beyond the thesis line.
            if support:
                branches.append({
                    'label': 'Paragraph 1 · Main point',
                    'topic': _gist_main_point(para, topic, 78),
                    'supports': [_shorten(s, 55) for s in support[:3]],
                })
            continue
        branches.append({
            'label': f'Paragraph {idx + 1} · Main point',
            'topic': _gist_main_point(para, topic, 78),
            'supports': [_shorten(s, 55) for s in support[:3]],
        })

    if not thesis:
        thesis = _shorten(paragraphs[0], 90)

    return {'thesis': thesis, 'branches': branches[:8]}


# ---------------------------------------------------------------------------
# 2. SVG structural diagram (radial mind-map layout)
# ---------------------------------------------------------------------------

_ESC = htmllib.escape


def _is_myanmar_text(text):
    return bool(re.search(r'[\u1000-\u109F]', str(text or '')))

def _grapheme_units(text):
    # Lightweight Unicode-grapheme grouping for Burmese: base characters are
    # kept together with following combining marks so wrapping never leaves
    # vowel/diacritic signs floating on a different line.
    import unicodedata
    units=[]
    cur=''
    for ch in str(text or ''):
        if ch.isspace():
            if cur: units.append(cur); cur=''
            units.append(' ')
            continue
        cat=unicodedata.category(ch)
        if cur and cat in ('Mn','Mc'):
            cur += ch
        else:
            if cur: units.append(cur)
            cur=ch
    if cur: units.append(cur)
    return units

def _wrap_text(text, max_chars=22, max_lines=3):
    text=re.sub(r'\s+', ' ', str(text or '')).strip()
    if not text: return []
    # Burmese text cannot safely be wrapped by spaces because many words are
    # written without whitespace. Use grapheme units for Myanmar; retain
    # normal word wrapping for English.
    if _is_myanmar_text(text):
        units=_grapheme_units(text)
        lines=[]; cur=''; width=0
        for unit in units:
            unit_w=1
            if unit==' ':
                if cur and not cur.endswith(' '): cur+=' '; width+=1
                continue
            if width+unit_w>max_chars and cur.strip():
                lines.append(cur.strip()); cur=unit; width=1
            else:
                cur+=unit; width+=unit_w
        if cur.strip(): lines.append(cur.strip())
    else:
        words_=text.split(' ')
        lines=[]; cur=''
        for w in words_:
            trial=(cur+' '+w).strip()
            if len(trial)>max_chars and cur:
                lines.append(cur); cur=w
            else: cur=trial
        if cur: lines.append(cur)
    # Never silently clip text inside a box. If the requested max_lines is
    # exceeded, return all lines; the layout code derives the box height from
    # the same result, so every line remains visible.
    return lines


def _text_block(x, y, text, size=13, weight='500', fill='#1f2937', anchor='middle', max_chars=22, max_lines=3):
    lines = _wrap_text(text, max_chars, max_lines)
    out = [f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
           f'text-anchor="{anchor}" font-family="Segoe UI, Helvetica, Arial, sans-serif">']
    for i, line in enumerate(lines):
        dy = 0 if i == 0 else size + 3
        out.append(f'<tspan x="{x}" dy="{dy}">{_ESC(line)}</tspan>')
    out.append('</text>')
    return ''.join(out)


def _block_height(text, size, max_chars, max_lines, line_gap=3):
    """Height (px) needed to render _text_block without clipping/overflow,
    so box sizes can be derived from actual wrapped content instead of a
    fixed guess."""
    n_lines = max(1, len(_wrap_text(text, max_chars, max_lines)))
    return n_lines * size + (n_lines - 1) * line_gap


def _arrow_len_for_text(text, min_len=26, max_len=64, short_chars=18, long_chars=90):
    """Map a node's text length to an arrow/gap length, so short text gets a
    short connector and long text gets a longer one (instead of every arrow
    sharing one fixed gap regardless of what it's pointing to). Clamped to
    [min_len, max_len] so very short or very long text can't collapse or
    stretch the layout unreasonably."""
    n = len(str(text or '').strip())
    if n <= short_chars:
        return min_len
    if n >= long_chars:
        return max_len
    frac = (n - short_chars) / float(long_chars - short_chars)
    return min_len + frac * (max_len - min_len)


def _compute_layout(structure, width=1100):
    """Single source of truth for the tree's geometry. Both the renderer and
    the height calculator call this so they can never disagree (which was
    the root cause of text overflowing its box before).

    Column width and box width are solved together (not clamped
    independently) so a box can never end up wider than the column that
    positions it: previously node_w/leaf_w had a hard floor (176px) that
    could exceed the column width once there were enough branches to
    squeeze columns below that floor, silently overlapping neighbouring
    boxes. Instead, once a minimum readable box width no longer fits at the
    requested canvas width, the canvas itself grows (returned as
    'required_width') rather than letting boxes collide — the frontend/SVG
    viewBox uses this width so the map simply gets wider/scrollable instead
    of overlapping."""
    branches = structure.get('branches') or []
    n = max(1, len(branches))

    margin_x = 50
    col_gutter = 24  # minimum guaranteed empty space between adjacent columns
    min_box_w = 150  # hard floor below which text becomes unreadable

    thesis_y_center = 86
    thesis_text_chars = 48
    thesis_h = max(104, 34 + _block_height(structure.get('thesis',''), 14, thesis_text_chars, 6))
    # Widths are content-aware. This gives long gists more room while still
    # fitting several branches across the canvas. Text is wrapped again after
    # width is selected, so box height always matches the rendered content.
    longest_branch = max([len((b.get('label','') + ' ' + b.get('topic','')).strip()) for b in branches] or [20])
    desired_node_w = min(290, max(210, 190 + int(longest_branch * 0.75)))
    node_pad_y = 16
    longest_leaf = max([len(s) for b in branches for s in (b.get('supports') or [])] or [20])
    desired_leaf_w = min(280, max(200, 185 + int(longest_leaf * 0.65)))
    leaf_pad_y = 12

    # The thesis -> branch arrow length adapts to the longest branch text
    # (topic + label combined), so a page of short, punchy branch topics
    # gets a tighter connector than one with long, wordy topics.
    thesis_arrow_lens = [
        _arrow_len_for_text((b.get('label', '') + ' ' + b.get('topic', '')).strip(), min_len=54, max_len=118)
        for b in branches
    ] or [54]
    row_gap = max(thesis_arrow_lens)

    # Solve column width and canvas width together. Start from the width the
    # caller asked for; if fitting `n` columns of at least `min_box_w` (plus
    # gutter) would force columns narrower than that floor, grow the canvas
    # instead of shrinking boxes past readability — this is what guarantees
    # boxes never overlap regardless of how many branches there are.
    box_w_cap = max(desired_node_w, desired_leaf_w)
    min_col_w = min_box_w + col_gutter
    usable_w = width - 2 * margin_x
    col_w = usable_w / n
    if col_w < min_col_w:
        col_w = min_col_w
        usable_w = col_w * n
        width = usable_w + 2 * margin_x
    # Box width fills its column up to the content-desired width, always
    # leaving the gutter as a hard guarantee — never a floor that can exceed
    # the column, which was the root cause of overlapping boxes.
    node_w = max(min_box_w, min(desired_node_w, col_w - col_gutter))
    leaf_w = max(min_box_w, min(desired_leaf_w, col_w - col_gutter))

    # Font sizes scale down slightly as columns get tighter (many branches),
    # so wrapped text keeps comfortable margins inside a narrower box instead
    # of hugging its edges.
    tightness = min(1.0, col_w / 260.0)
    label_size = round(11 * (0.82 + 0.18 * tightness), 1)
    topic_size = round(12.5 * (0.82 + 0.18 * tightness), 1)
    leaf_text_size = round(10.5 * (0.82 + 0.18 * tightness), 1)

    total_cols_w = col_w * n
    start_x = margin_x + (usable_w - total_cols_w) / 2 + col_w / 2
    col_x = [start_x + i * col_w for i in range(n)]

    branch_layout = []
    max_node_h = 0
    for branch in branches:
        node_chars = max(18, int(node_w / (topic_size * 0.62)))
        label_chars = max(18, int(node_w / (label_size * 0.58)))
        label_h = _block_height(branch['label'], label_size, label_chars, 4)
        topic_h = _block_height(branch['topic'], topic_size, node_chars, 8)
        node_h = max(node_pad_y * 2 + label_h + 6 + topic_h, 60)
        max_node_h = max(max_node_h, node_h)
        leaves = []
        for sup in (branch.get('supports') or []):
            leaf_chars = max(18, int(leaf_w / (leaf_text_size * 0.62)))
            sup_h = _block_height(sup, leaf_text_size, leaf_chars, 8)
            # Each leaf's incoming arrow scales with that leaf's own text —
            # a short supporting point gets a short arrow, a long one gets
            # more room to breathe before the box starts.
            leaf_arrow_len = _arrow_len_for_text(sup, min_len=26, max_len=64)
            leaves.append((sup, leaf_pad_y * 2 + sup_h, leaf_arrow_len))
        branch_layout.append({'leaves': leaves})
    for bl in branch_layout:
        bl['node_h'] = max_node_h

    main_row_y = thesis_y_center + thesis_h / 2 + row_gap
    # Give each branch its own vertical position. This makes the thesis ->
    # branch connector genuinely adjustable: longer branch text gets a
    # slightly longer connector/greater gap, while short text stays compact.
    min_branch_arrow = min(thesis_arrow_lens) if thesis_arrow_lens else 54
    branch_y = [main_row_y + max(0, (a - min_branch_arrow) * 0.55) for a in thesis_arrow_lens]
    branch_leaves_start_y = [y + max_node_h / 2 + 50 for y in branch_y]

    max_column_bottom = max(branch_leaves_start_y or [main_row_y])
    for bl, leaves_y in zip(branch_layout, branch_leaves_start_y):
        y = leaves_y
        for _, leaf_h, leaf_arrow_len in bl['leaves']:
            y += leaf_h + leaf_arrow_len
        max_column_bottom = max(max_column_bottom, y)

    return {
        'n': n, 'margin_x': margin_x, 'thesis_y_center': thesis_y_center,
        'thesis_h': thesis_h, 'row_gap': row_gap, 'node_w': node_w,
        'node_pad_y': node_pad_y, 'label_size': label_size, 'topic_size': topic_size,
        'leaf_w': leaf_w, 'leaf_pad_y': leaf_pad_y, 'leaf_text_size': leaf_text_size,
        'col_x': col_x, 'col_w': col_w, 'branch_layout': branch_layout,
        'main_row_y': main_row_y, 'branch_y': branch_y,
        'branch_leaves_start_y': branch_leaves_start_y,
        'bottom_y': max_column_bottom,
        'required_width': width,
    }


_PALETTE = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#ef4444', '#84cc16']


def _arrow_marker_defs():
    """Reusable arrowhead markers per palette color, used on connectors so
    the tree reads like a clear flow (topic -> detail).

    Two sizes per color: a larger head for the thicker thesis->branch
    connectors (stroke-width 2.5) and a smaller one for the thinner
    branch->leaf connectors (stroke-width 1.8), so the arrowhead's size
    always looks proportionate to the line it caps instead of one fixed
    size reading as too small on a thick line or too heavy on a thin one.
    refX is set to the tip of the triangle (10) rather than short of it, so
    the arrow's point lands exactly at the path's end coordinate — i.e.
    right at the target box's edge — instead of overshooting into the box
    or stopping short and leaving a visible gap."""
    defs = []
    for i, color in enumerate(_PALETTE):
        # main connector arrowhead (larger, matches stroke-width 2.5)
        defs.append(
            f'<marker id="arrow{i}" viewBox="0 0 10 10" refX="9.5" refY="5" '
            f'markerWidth="8" markerHeight="8" orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
            f'<path d="M0,0.5 L10,5 L0,9.5 Z" fill="{color}"/></marker>'
        )
        # leaf connector arrowhead (smaller, matches stroke-width 1.8)
        defs.append(
            f'<marker id="arrowLeaf{i}" viewBox="0 0 10 10" refX="9.5" refY="5" '
            f'markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
            f'<path d="M0,0.5 L10,5 L0,9.5 Z" fill="{color}"/></marker>'
        )
    return ''.join(defs)


def render_structure_svg(structure, width=1100, height=None):
    """Top-down tree layout: thesis banner at the top, main-point nodes in a
    row beneath it, and each main point's supporting ideas stacked in a
    column directly under their parent, joined by arrows — a clear, tidy
    outline/architecture read (topic on top, detail underneath flowing down
    via arrows), not a radial mind-map. Box heights are computed from the
    actual wrapped text so labels never overflow their container."""
    thesis = structure.get('thesis') or 'Untitled Essay'
    branches = structure.get('branches') or []
    L = _compute_layout(structure, width)
    width = L['required_width']  # canvas grows instead of squeezing boxes into overlap
    n = L['n']
    col_x = L['col_x']
    node_w = L['node_w']
    label_size, topic_size = L['label_size'], L['topic_size']
    leaf_w, leaf_text_size = L['leaf_w'], L['leaf_text_size']
    thesis_y_center, thesis_h = L['thesis_y_center'], L['thesis_h']
    main_row_y = L['main_row_y']
    branch_y = L.get('branch_y', [main_row_y] * n)
    branch_leaves_start_y = L.get('branch_leaves_start_y', [main_row_y + L['node_h']/2 + 50 if 'node_h' in L else main_row_y + 100] * n)
    margin_x = L['margin_x']
    height = height or max(560, int(L['bottom_y'] + 60))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="100%" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
    ]
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fafaf9"/>')
    parts.append(
        '<defs><radialGradient id="thesisGrad" cx="50%" cy="35%" r="75%">'
        '<stop offset="0%" stop-color="#eef2ff"/><stop offset="100%" stop-color="#e0e7ff"/>'
        '</radialGradient></defs>'
    )
    parts.append(f'<defs>{_arrow_marker_defs()}</defs>')

    cx = width / 2

    # connector lines from thesis down to each main point (drawn first, under
    # nodes). Every branch shares the same row (by), but the curve itself is
    # drawn longer/shorter — via how far its control points bow out — in
    # proportion to that branch's own text length, so a short topic reads
    # with a short, direct arrow and a long topic reads with a longer,
    # more deliberate one, even though both land in the same row.
    for i in range(n):
        bx = col_x[i]
        by = branch_y[i] if i < len(branch_y) else main_row_y
        color_idx = i % len(_PALETTE)
        color = _PALETTE[color_idx]
        top_y = thesis_y_center + thesis_h / 2
        node_h = L['branch_layout'][i]['node_h'] if i < len(L['branch_layout']) else 60
        # Clearance before the box top matches the main-connector arrowhead
        # size (see _arrow_marker_defs) so the arrow tip lands right at the
        # box edge rather than clipping into it or floating short of it.
        bottom_target = by - node_h / 2 - 9
        branch = branches[i] if i < len(branches) else {'label': '', 'topic': ''}
        arrow_len = _arrow_len_for_text((branch.get('label', '') + ' ' + branch.get('topic', '')).strip(), min_len=54, max_len=118)
        # Bow the curve's control points out horizontally in proportion to
        # arrow_len (clamped) so longer-text branches get a visibly longer,
        # more relaxed arc instead of every connector looking identical.
        bow = min(arrow_len * 0.55, abs(bx - cx) + 40)
        bow_dir = 1 if bx >= cx else -1
        mid_y = (top_y + bottom_target) / 2
        c1x = cx + bow_dir * bow * 0.3
        c2x = bx - bow_dir * bow * 0.3
        parts.append(
            f'<path d="M{cx:.1f},{top_y:.1f} C{c1x:.1f},{mid_y:.1f} {c2x:.1f},{mid_y:.1f} {bx:.1f},{bottom_target:.1f}" '
            f'stroke="{color}" stroke-width="2.5" fill="none" opacity="0.65" marker-end="url(#arrow{color_idx})"/>'
        )

    # thesis banner (drawn after connectors, before main nodes)
    thesis_w = min(560, width - 2 * margin_x)
    parts.append(
        f'<rect x="{cx - thesis_w/2:.1f}" y="{thesis_y_center - thesis_h/2:.1f}" width="{thesis_w}" height="{thesis_h}" '
        f'rx="18" fill="url(#thesisGrad)" stroke="#4f46e5" stroke-width="3"/>'
    )
    parts.append(_text_block(cx, thesis_y_center - 18, 'THESIS / TOPIC', size=11, weight='700', fill='#4f46e5', max_chars=40, max_lines=1))
    parts.append(_text_block(cx, thesis_y_center + 14, thesis, size=14, weight='700', fill='#312e81', max_chars=48, max_lines=6))

    # main-point nodes + their supporting-idea columns
    for i, branch in enumerate(branches):
        color_idx = i % len(_PALETTE)
        color = _PALETTE[color_idx]
        bx = col_x[i]
        by = branch_y[i] if i < len(branch_y) else main_row_y
        node_h = L['branch_layout'][i]['node_h']
        parts.append(
            f'<rect x="{bx - node_w/2:.1f}" y="{by - node_h/2:.1f}" width="{node_w}" height="{node_h}" '
            f'rx="14" fill="white" stroke="{color}" stroke-width="2.5"/>'
        )
        node_chars = max(18, int(node_w / (topic_size * 0.62)))
        label_chars = max(18, int(node_w / (label_size * 0.58)))
        label_h = _block_height(branch['label'], label_size, label_chars, 4)
        topic_h = _block_height(branch['topic'], topic_size, node_chars, 8)
        block_total = label_h + 6 + topic_h
        top_of_text = by - block_total / 2
        parts.append(_text_block(bx, top_of_text + label_size * 0.8, branch['label'], size=label_size, weight='700', fill=color, max_chars=label_chars, max_lines=4))
        parts.append(_text_block(bx, top_of_text + label_h + 6 + topic_size * 0.85, branch['topic'], size=topic_size, weight='500', fill='#374151', max_chars=node_chars, max_lines=8))

        # Each supporting idea's incoming arrow is drawn at the length
        # _compute_layout already assigned it (leaf_arrow_len), so a short
        # supporting sentence gets a short arrow and a long one gets a
        # longer arrow — directly adjustable per node, not one fixed gap.
        leaves = L['branch_layout'][i]['leaves']
        prev_bottom = by + node_h / 2
        cursor_y = branch_leaves_start_y[i] if i < len(branch_leaves_start_y) else (by + node_h / 2 + 50)
        for sup, leaf_h, leaf_arrow_len in leaves:
            ly_top = cursor_y
            ly_center = ly_top + leaf_h / 2
            arrow_gap = 10
            parts.append(
                f'<path d="M{bx:.1f},{prev_bottom + 4:.1f} L{bx:.1f},{ly_top - arrow_gap:.1f}" '
                f'stroke="{color}" stroke-width="1.8" opacity="0.65" marker-end="url(#arrowLeaf{color_idx})"/>'
            )
            parts.append(
                f'<rect x="{bx - leaf_w/2:.1f}" y="{ly_top:.1f}" width="{leaf_w}" height="{leaf_h}" '
                f'rx="10" fill="{color}" opacity="0.07" stroke="{color}" stroke-width="1.2"/>'
            )
            leaf_chars = max(18, int(leaf_w / (leaf_text_size * 0.62)))
            sup_text_h = _block_height(sup, leaf_text_size, leaf_chars, 4)
            parts.append(_text_block(bx, ly_center - sup_text_h/2 + leaf_text_size * 0.85, sup, size=leaf_text_size, weight='400', fill='#4b5563', max_chars=leaf_chars, max_lines=8))
            prev_bottom = ly_top + leaf_h
            cursor_y = ly_top + leaf_h + leaf_arrow_len

    parts.append('</svg>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# 3. Optional artistic sketch overlay (decorative, deterministic per-essay)
# ---------------------------------------------------------------------------

def _compute_height(structure, width=1100):
    """Shared height calc so the diagram, sketch and combined outputs all
    agree on canvas size (keeps the tree tidy instead of clipped/stretched).
    Delegates to _compute_layout, the single source of truth for geometry."""
    L = _compute_layout(structure, width)
    return max(560, int(L['bottom_y'] + 60))


def _compute_canvas_size(structure, width=1100):
    """Resolve the actual (width, height) the diagram will render at. Width
    can grow past the requested value when there are enough branches that
    boxes would otherwise be squeezed narrower than a readable minimum —
    see _compute_layout's 'required_width'. All renderers call this so the
    diagram, sketch and combined SVGs always agree on canvas size."""
    L = _compute_layout(structure, width)
    resolved_width = L['required_width']
    height = max(560, int(L['bottom_y'] + 60))
    return resolved_width, height


def render_artistic_sketch_svg(structure, seed=None, width=1100, height=None):
    """Generates a soft, hand-drawn-style decorative background: organic
    blobs and sketchy flourishes whose color/count are derived from the
    essay's own branch count, so it feels tied to the content without
    calling any image-generation service. Kept subtle (low opacity, fewer
    shapes) so the structural tree on top stays clear and easy to read."""
    branches = structure.get('branches') or []
    width, resolved_height = _compute_canvas_size(structure, width)
    height = height or resolved_height
    n = max(2, min(5, len(branches)))
    rnd = random.Random(seed if seed is not None else len(structure.get('thesis', '')))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="100%">'
    ]
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fffdf7"/>')

    # scattered organic "blob" shapes, kept near the edges and very light so
    # they read as a subtle sketchy backdrop rather than visual clutter
    for i in range(n):
        color = _PALETTE[i % len(_PALETTE)]
        edge = rnd.choice(['left', 'right'])
        bx = rnd.uniform(width * 0.02, width * 0.14) if edge == 'left' else rnd.uniform(width * 0.86, width * 0.98)
        by = rnd.uniform(height * 0.1, height * 0.9)
        base_r = rnd.uniform(24, 46)
        points = []
        steps = 8
        for s in range(steps):
            ang = 2 * math.pi * s / steps
            r = base_r * rnd.uniform(0.8, 1.2)
            points.append((bx + r * math.cos(ang), by + r * math.sin(ang)))
        d = f'M{points[0][0]:.1f},{points[0][1]:.1f} '
        for k in range(1, len(points) + 1):
            p0 = points[k - 1]
            p1 = points[k % len(points)]
            mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
            d += f'Q{p0[0]:.1f},{p0[1]:.1f} {mx:.1f},{my:.1f} '
        d += 'Z'
        parts.append(f'<path d="{d}" fill="{color}" opacity="0.05"/>')
        parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.3" opacity="0.18"/>')

    parts.append('</svg>')
    return ''.join(parts)


def render_combined_svg(structure, include_sketch=True, width=1100, height=None):
    """Layers the artistic sketch (background) beneath the structural
    diagram (foreground) in a single SVG document."""
    width, resolved_height = _compute_canvas_size(structure, width)
    height = height or resolved_height
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="100%" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
    ]
    if include_sketch:
        sketch_inner = render_artistic_sketch_svg(structure, width=width, height=height)
        sketch_inner = re.sub(r'^<svg[^>]*>|</svg>$', '', sketch_inner.strip())
        parts.append(f'<g opacity="1">{sketch_inner}</g>')
    structure_inner = render_structure_svg(structure, width=width, height=height)
    structure_inner = re.sub(r'^<svg[^>]*>.*?<rect[^>]*fill="#fafaf9"/>|</svg>$', '', structure_inner.strip(), flags=re.S)
    parts.append(structure_inner)
    parts.append('</svg>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# 4. Public entry point
# ---------------------------------------------------------------------------

def generate_idea_map(text, essay_title=None, include_sketch=True):
    structure = extract_structure(text, essay_title)
    diagram_svg = render_structure_svg(structure)
    sketch_svg = render_artistic_sketch_svg(structure) if include_sketch else None
    combined_svg = render_combined_svg(structure, include_sketch=include_sketch)
    return {
        'ok': True,
        'structure': structure,
        'diagram_svg': diagram_svg,
        'sketch_svg': sketch_svg,
        'combined_svg': combined_svg,
    }
