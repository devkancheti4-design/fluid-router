# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 devkancheti4-design
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details. You should have received a copy
# of the license along with this program. If not, see
# <https://www.gnu.org/licenses/>.
"""EXTENDED ACT DICTIONARY -- the 'company custom file' hypothesis.

Router untouched and imported verbatim. Only the mechanical body grows:
  * four new acts covering the fault classes the shipped four cannot express
  * the crude-transform fix the README already names: try EVERY literal on a
    line, not just re.search(r"\d+") which takes the first.

The kind -> act mapping is still never written down. It is inferred by the
router from the single shipped worked example (fault kind 0 -> act 5).
"""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from fluid_router import route as router
WORKED_EXAMPLE = (0, 5)


# ---------------------------------------------------------------------------
# YOUR JOB: fill in observe() and acts() below.
#
#   observe(line) -> list of integer fault KINDS this line could exhibit.
#                    Kind numbers must start at 0 and be contiguous.
#
#   acts(line, act) -> list of EVERY candidate replacement line this act offers.
#                      Act number for kind k is ALWAYS k + 5 (the router derives
#                      this from one worked example; do not hard-code a mapping,
#                      just number your acts 5, 6, 7, ... in kind order).
#
# Return [] when an act does not apply. Never return the input line unchanged.
# Pure text transforms only -- no AST, no imports beyond re.
# ---------------------------------------------------------------------------

# ===========================================================================
# low-level text helpers (no AST, only re + plain string scanning)
# ===========================================================================

_OPEN = "([{"
_CLOSE = ")]}"
_NUL = "\x00"


def _uniq(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _mask(line):
    """Same-length copy of `line` with string/char literal *contents* and
    trailing comments blanked to NUL, so structural scans never trip over
    commas, brackets, operators or keywords living inside a regex literal."""
    out = list(line)
    i = 0
    n = len(line)
    quote = None
    while i < n:
        c = line[i]
        if quote is not None:
            if c == "\\":
                out[i] = _NUL
                if i + 1 < n:
                    out[i + 1] = _NUL
                i += 2
                continue
            if c == quote:
                quote = None
            else:
                out[i] = _NUL
            i += 1
            continue
        if c == '"' or c == "'":
            quote = c
            i += 1
            continue
        if c == "#":
            for j in range(i, n):
                out[j] = _NUL
            break
        i += 1
    return "".join(out)


def _brackets(ms):
    """[(open_idx, close_idx, open_char)] for every balanced pair."""
    stack = []
    out = []
    for i, c in enumerate(ms):
        if c in _OPEN:
            stack.append((i, c))
        elif c in _CLOSE:
            if stack:
                o, oc = stack.pop()
                out.append((o, i, oc))
    out.sort()
    return out


def _top_cuts(ms, a, b, sep=","):
    depth = 0
    cuts = []
    for i in range(a, b):
        c = ms[i]
        if c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth -= 1
        elif depth == 0 and c == sep:
            cuts.append(i)
    return cuts


def _parts(ms, a, b, sep=","):
    """Spans of the top-level `sep`-separated parts of ms[a:b], stripped."""
    cuts = _top_cuts(ms, a, b, sep)
    if not cuts:
        return []
    spans = []
    prev = a
    for c in cuts + [b]:
        s, e = prev, c
        while s < e and ms[s] in " \t":
            s += 1
        while e > s and ms[e - 1] in " \t":
            e -= 1
        spans.append((s, e))
        prev = c + 1
    return spans


def _permute(line, spans, perm):
    """Rebuild `line` with the text of the given spans reordered by `perm`."""
    if len(spans) != len(perm):
        return None
    out = [line[: spans[0][0]]]
    for i, p in enumerate(perm):
        out.append(line[spans[p][0]: spans[p][1]])
        if i + 1 < len(spans):
            out.append(line[spans[i][1]: spans[i + 1][0]])
    out.append(line[spans[-1][1]:])
    return "".join(out)


def _swap(line, s1, e1, s2, e2):
    if e1 > s2:
        return None
    return line[:s1] + line[s2:e2] + line[e1:s2] + line[s1:e1] + line[e2:]


def _rep(line, s, e, new):
    return line[:s] + new + line[e:]


def _perms(n):
    """All non-identity permutations for small n (n<=3); pairwise swaps above."""
    idx = list(range(n))
    if n == 2:
        return [[1, 0]]
    if n == 3:
        return [
            [0, 2, 1], [1, 0, 2], [2, 1, 0],
            [1, 2, 0], [2, 0, 1],
        ]
    out = []
    for i in range(n):
        for j in range(i + 1, n):
            p = list(idx)
            p[i], p[j] = p[j], p[i]
            out.append(p)
    return out


# --- operand scanning -------------------------------------------------------

_WORDY = "_.\x00'\""


def _left_operand(ms, i):
    """Span of the operand ending just before index i (an operator)."""
    j = i
    while j > 0 and ms[j - 1] in " \t":
        j -= 1
    end = j
    depth = 0
    while j > 0:
        c = ms[j - 1]
        if c in _CLOSE:
            depth += 1
            j -= 1
        elif c in _OPEN:
            if depth == 0:
                break
            depth -= 1
            j -= 1
        elif depth > 0:
            j -= 1
        elif c.isalnum() or c in _WORDY:
            j -= 1
        else:
            break
    if j >= end:
        return None
    return (j, end)


def _right_operand(ms, i):
    """Span of the operand starting just after index i (end of an operator)."""
    n = len(ms)
    j = i
    while j < n and ms[j] in " \t":
        j += 1
    start = j
    depth = 0
    while j < n:
        c = ms[j]
        if c in _OPEN:
            depth += 1
            j += 1
        elif c in _CLOSE:
            if depth == 0:
                break
            depth -= 1
            j += 1
        elif depth > 0:
            j += 1
        elif c.isalnum() or c in _WORDY:
            j += 1
        else:
            break
    if j <= start:
        return None
    return (start, j)


# --- token site finders -----------------------------------------------------

_CMP_RE = re.compile(r"(?<![-<>=!+*/%|&^])(<=|>=|==|!=|<|>)(?![=<>])")
_ADD_RE = re.compile(r"(?<=[\w\)\]\}\"'\x00])[ \t]*([+\-])[ \t]*(?=[\w\(\[\{\"'\x00])")
_MUL_RE = re.compile(r"(?<=[\w\)\]\}\"'\x00])[ \t]*(\*\*|//|[*/%])[ \t]*(?=[\w\(\[\{\"'\x00])")
_AUG_RE = re.compile(r"(\+=|-=|\*=|/=|//=|%=|\|=|&=)")
_STR_RE = re.compile(r"""(['"])(?:\\.|(?!\1).)*?\1""")
_INT_RE = re.compile(r"\d+")


def _cmp_sites(ms):
    return [(m.start(1), m.end(1), m.group(1)) for m in _CMP_RE.finditer(ms)]


def _add_sites(ms):
    return [(m.start(1), m.end(1), m.group(1)) for m in _ADD_RE.finditer(ms)]


def _mul_sites(ms):
    out = []
    for m in _MUL_RE.finditer(ms):
        s = m.start(1)
        k = s - 1
        while k >= 0 and ms[k] in " \t":
            k -= 1
        if k >= 0 and ms[k] in "\"'" and m.group(1) == "%":
            continue  # printf-style string formatting, not arithmetic
        out.append((s, m.end(1), m.group(1)))
    return out


def _int_sites(line):
    """Every integer literal on the line, including digits inside regex
    literals (quantifiers like {1,3} are real off-by-one targets here)."""
    out = []
    for m in _INT_RE.finditer(line):
        s, e = m.span()
        before = line[s - 1] if s > 0 else ""
        after = line[e] if e < len(line) else ""
        if before.isalpha() or before == "_":
            continue
        if after.isalpha() or after == "_":
            continue
        out.append((s, e, int(m.group())))
    return out


def _word_sites(ms, word):
    return [m.span() for m in re.finditer(r"\b%s\b" % re.escape(word), ms)]


def _subscripts(ms):
    """[(open, close)] for `[` pairs that are subscripts (not list literals)."""
    out = []
    for o, c, oc in _brackets(ms):
        if oc != "[":
            continue
        k = o - 1
        while k >= 0 and ms[k] in " \t":
            k -= 1
        if k < 0:
            continue
        p = ms[k]
        if p.isalnum() or p in "_)]\"'" or p == _NUL:
            out.append((o, c))
    return out


# ===========================================================================
# the acts, in kind order (kind k -> act k+5)
# ===========================================================================

def _act_int_offbyone(line, ms):
    """kind 0: off-by-one on ANY integer literal on the line -- every site."""
    out = []
    for s, e, v in _int_sites(line):
        for nv in (v + 1, v - 1):
            if nv < 0:
                continue
            out.append(_rep(line, s, e, str(nv)))
    return out


def _act_addsub(line, ms):
    """kind 1: additive operator confusion, + <-> - , += <-> -= , unary sign."""
    out = []
    for s, e, op in _add_sites(ms):
        out.append(_rep(line, s, e, "-" if op == "+" else "+"))
    for m in _AUG_RE.finditer(ms):
        op = m.group(1)
        if op == "+=":
            out.append(_rep(line, m.start(), m.end(), "-="))
            out.append(_rep(line, m.start(), m.end(), "="))
        elif op == "-=":
            out.append(_rep(line, m.start(), m.end(), "+="))
            out.append(_rep(line, m.start(), m.end(), "="))
        elif op == "*=":
            out.append(_rep(line, m.start(), m.end(), "/="))
        elif op == "/=":
            out.append(_rep(line, m.start(), m.end(), "*="))
    # unary minus added / removed:  x = -offset  <->  x = offset
    for m in re.finditer(r"(?<=[=,(\[ ])-(?=[\w(])", ms):
        out.append(_rep(line, m.start(), m.end(), ""))
    for m in re.finditer(r"(?<=[=(,] )(?=[\w(])", ms):
        out.append(_rep(line, m.start(), m.start(), "-"))
    return out


def _act_cmp_strictness(line, ms):
    """kind 2: comparison strictness, < <-> <= and > <-> >= , at every site."""
    flip = {"<": "<=", "<=": "<", ">": ">=", ">=": ">"}
    out = []
    for s, e, op in _cmp_sites(ms):
        if op in flip:
            out.append(_rep(line, s, e, flip[op]))
    return out


def _act_equality(line, ms):
    """kind 3: equality/inequality and comparison direction, is/in negation."""
    out = []
    alts = {
        "==": ["!=", ">=", "<=", ">", "<"],
        "!=": ["==", ">", "<"],
        "<": [">", ">=", "=="],
        ">": ["<", "<=", "=="],
        "<=": [">=", ">", "=="],
        ">=": ["<=", "<", "=="],
    }
    for s, e, op in _cmp_sites(ms):
        for new in alts.get(op, []):
            out.append(_rep(line, s, e, new))
    for m in re.finditer(r"\bis\s+not\b", ms):
        out.append(_rep(line, m.start(), m.end(), "is"))
    for m in re.finditer(r"\bis\b(?!\s+not\b)", ms):
        out.append(_rep(line, m.start(), m.end(), "is not"))
    for m in re.finditer(r"\bnot\s+in\b", ms):
        out.append(_rep(line, m.start(), m.end(), "in"))
    for m in re.finditer(r"(?<!\bnot )\bin\b", ms):
        out.append(_rep(line, m.start(), m.end(), "not in"))
    return out


def _act_bool_literal(line, ms):
    """kind 4: boolean literal / sentinel flips at every site."""
    out = []
    for s, e in _word_sites(ms, "True"):
        out.append(_rep(line, s, e, "False"))
        out.append(_rep(line, s, e, "None"))
    for s, e in _word_sites(ms, "False"):
        out.append(_rep(line, s, e, "True"))
        out.append(_rep(line, s, e, "None"))
    for s, e in _word_sites(ms, "None"):
        out.append(_rep(line, s, e, "True"))
        out.append(_rep(line, s, e, "False"))
    for s, e in _word_sites(ms, "break"):
        out.append(_rep(line, s, e, "continue"))
    for s, e in _word_sites(ms, "continue"):
        out.append(_rep(line, s, e, "break"))
    return out


def _act_and_or(line, ms):
    """kind 5: and/or confusion at every site."""
    out = []
    for s, e in _word_sites(ms, "and"):
        out.append(_rep(line, s, e, "or"))
    for s, e in _word_sites(ms, "or"):
        out.append(_rep(line, s, e, "and"))
    return out


def _act_slice_index(line, ms):
    """kind 6: off-by-one / off-by-a-term on slice bounds and indices."""
    out = []
    for o, c in _subscripts(ms):
        a, b = o + 1, c
        inner = line[a:b]
        minner = ms[a:b]
        colons = _top_cuts(ms, a, b, ":")
        if colons:
            spans = _parts(ms, a, b, ":")
            for i, (ps, pe) in enumerate(spans):
                txt = line[ps:pe]
                if not txt:
                    continue
                m = re.match(r"^(-?\d+)$", txt)
                if m:
                    v = int(m.group(1))
                    for nv in (v + 1, v - 1):
                        out.append(_rep(line, ps, pe, str(nv)))
                else:
                    out.append(_rep(line, ps, pe, txt + " + 1"))
                    out.append(_rep(line, ps, pe, txt + " - 1"))
                    m2 = re.match(r"^(.*?)\s*([+-])\s*(\d+)$", txt)
                    if m2:
                        base, op, num = m2.group(1), m2.group(2), int(m2.group(3))
                        out.append(_rep(line, ps, pe, base))
                        other = "-" if op == "+" else "+"
                        out.append(_rep(line, ps, pe, "%s %s %d" % (base, other, num)))
                # dropping the bound entirely
                out.append(_rep(line, ps, pe, ""))
            if len(spans) == 2 and line[spans[0][0]:spans[0][1]] and line[spans[1][0]:spans[1][1]]:
                sw = _permute(line, spans, [1, 0])
                if sw:
                    out.append(sw)
        else:
            txt = inner
            if not txt or "," in minner:
                continue
            if re.match(r"^-?\d+$", txt):
                v = int(txt)
                out.append(_rep(line, a, b, str(v + 1)))
                out.append(_rep(line, a, b, str(v - 1)))
            else:
                out.append(_rep(line, a, b, txt + " + 1"))
                out.append(_rep(line, a, b, txt + " - 1"))
                m2 = re.match(r"^(.*?)\s*([+-])\s*(\d+)$", txt)
                if m2:
                    base, op, num = m2.group(1), m2.group(2), int(m2.group(3))
                    out.append(_rep(line, a, b, base))
                    other = "-" if op == "+" else "+"
                    out.append(_rep(line, a, b, "%s %s %d" % (base, other, num)))
        # slice <-> index style confusion on the whole subscript
        if colons and len(_parts(ms, a, b, ":")) == 2:
            first = line[_parts(ms, a, b, ":")[0][0]:_parts(ms, a, b, ":")[0][1]]
            second = line[_parts(ms, a, b, ":")[1][0]:_parts(ms, a, b, ":")[1][1]]
            if first and not second:
                out.append(_rep(line, a, b, ":" + first))
            if second and not first:
                out.append(_rep(line, a, b, second + ":"))
    return out


def _act_swap_operands(line, ms):
    """kind 7: swapped operands -- around binary operators, between
    comma-separated elements, and between keyword-argument values."""
    out = []
    sites = _cmp_sites(ms) + _add_sites(ms) + _mul_sites(ms)
    for s, e, op in sites:
        lo = _left_operand(ms, s)
        ro = _right_operand(ms, e)
        if not lo or not ro:
            continue
        sw = _swap(line, lo[0], lo[1], ro[0], ro[1])
        if sw:
            out.append(sw)

    regions = []
    for o, c, oc in _brackets(ms):
        regions.append((o + 1, c, oc, o))
    # assignment target list / rhs at statement level
    eqs = [m.start() for m in re.finditer(r"(?<![=!<>+\-*/%|&^])=(?!=)", ms)
           if not _in_brackets(ms, m.start())]
    if eqs:
        regions.append((0, eqs[0], None, -1))
        regions.append((eqs[0] + 1, len(ms), None, -1))
    else:
        regions.append((0, len(ms), None, -1))

    for a, b, oc, opos in regions:
        spans = _parts(ms, a, b, ",")
        spans = [(s, e) for (s, e) in spans if e > s]
        if len(spans) < 2 or len(spans) > 6:
            continue
        for perm in _perms(len(spans)):
            cand = _permute(line, spans, perm)
            if cand:
                out.append(cand)
        # keyword-argument VALUE swaps (name=value, name2=value2)
        kv = []
        for s, e in spans:
            m = re.match(r"^([A-Za-z_]\w*)\s*=\s*", ms[s:e])
            if m and not ms[s:e].startswith("=="):
                kv.append((s + m.end(), e))
        for i in range(len(kv)):
            for j in range(i + 1, len(kv)):
                sw = _swap(line, kv[i][0], kv[i][1], kv[j][0], kv[j][1])
                if sw:
                    out.append(sw)
    return out


def _in_brackets(ms, i):
    depth = 0
    for k in range(i):
        if ms[k] in _OPEN:
            depth += 1
        elif ms[k] in _CLOSE:
            depth -= 1
    return depth > 0


def _act_muldiv(line, ms):
    """kind 8: multiplicative / mixed arithmetic operator confusion."""
    alts = {
        "*": ["/", "//", "+", "-", "%", "**"],
        "/": ["*", "//", "+", "-", "%"],
        "//": ["/", "*", "%", "+", "-"],
        "%": ["//", "*", "/", "+", "-"],
        "**": ["*", "/", "+", "-"],
    }
    out = []
    for s, e, op in _mul_sites(ms):
        for new in alts.get(op, []):
            out.append(_rep(line, s, e, new))
    for s, e, op in _add_sites(ms):
        for new in ("*", "//", "/"):
            out.append(_rep(line, s, e, new))
    return out


def _act_int_other(line, ms):
    """kind 9: larger literal perturbations, constant-family confusion, and
    dropping / adding a whole `+ k` term."""
    out = []
    sites = _int_sites(line)
    values = [v for (_, _, v) in sites]
    families = [
        [2, 8, 10, 16],
        [0, 1, 2, 3],
        [12, 24, 60],
        [6, 3, 4, 5],
        [100, 1000, 10],
        [1, 2, 3, 4, 5, 6, 7, 8, 9],
    ]
    pool = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 60, 100]
    for s, e, v in sites:
        cands = [v + 2, v - 2, v + 3, v - 3, v * 2, v // 2, 0, 1]
        if v <= 100:
            cands.extend(pool)
        if v <= 12:
            # group-index / month / base arithmetic in this codebase lives
            # entirely in this range: offer the whole range at every site.
            cands.extend(range(0, 13))
        for fam in families:
            if v in fam:
                cands.extend(fam)
        for other in values:
            cands.append(other)
        for nv in _uniq(cands):
            if nv < 0 or nv == v:
                continue
            out.append(_rep(line, s, e, str(nv)))
    # drop / duplicate an additive term:  n + 1  ->  n     and   n  ->  n + 1
    for m in re.finditer(r"[ \t]*([+\-])[ \t]*(\d+)", ms):
        s, e = m.span()
        before = ms[s - 1] if s > 0 else ""
        if before.isalnum() or before in "_)]\"'" or before == _NUL:
            out.append(_rep(line, s, e, ""))
    return out


_PAIRS = [
    ("mm", "dd"), ("dd", "hms"), ("mm", "hms"),
    ("ymd", "mdy"), ("mdy", "dmy"), ("ymd", "dmy"), ("dmy", "d_m_y"),
    ("am", "tz"), ("hms", "tz"),
    ("pos", "endpos"), ("start", "end"), ("start", "stop"),
    ("fixed", "named"), ("_fixed_fields", "_named_fields"),
    ("fixed_fields", "named_fields"),
    ("_group_to_name_map", "_name_to_group_map"),
    ("_search_re", "_match_re"), ("__search_re", "__match_re"),
    ("search", "match"), ("groups", "groupdict"), ("group", "groups"),
    ("fill", "align"), ("width", "precision"), ("align", "type"),
    ("zero", "fill"), ("grouping", "precision"), ("type", "format"),
    ("base", "sign"), ("format", "string"), ("string", "format"),
    ("name", "group"), ("field", "group"),
    ("min", "max"), ("first", "last"), ("append", "extend"),
    ("lower", "upper"), ("ljust", "rjust"), ("rjust", "center"),
    ("startswith", "endswith"), ("isdigit", "isalpha"), ("isalpha", "isalnum"),
    ("strip", "lstrip"), ("lstrip", "rstrip"), ("keys", "values"),
    ("H", "M"), ("M", "S"), ("H", "S"),
    ("m", "d"), ("y", "m"), ("d", "y"),
    ("tzh", "tzm"), ("n", "m"), ("k", "n"), ("i", "n"), ("s", "e"),
    ("int", "float"), ("len", "int"),
    ("_group_index", "_group_to_name_map"),
    ("split", "rsplit"), ("find", "rfind"), ("index", "find"),
    ("sub", "subn"), ("get", "pop"), ("setdefault", "get"),
    ("any", "all"),
]


def _act_name_confusion(line, ms):
    """kind 10: neighbouring-identifier confusion -- every occurrence.

    Scans the RAW line, not the masked one: in this codebase half of these
    names live inside string literals as dictionary keys (format["width"],
    format.get("precision"), ...), and key confusion is the same fault."""
    out = []
    for a, b in _PAIRS:
        for x, y in ((a, b), (b, a)):
            for s, e in _word_sites(line, x):
                out.append(_rep(line, s, e, y))
    return out


def _act_not(line, ms):
    """kind 11: a missing / spurious `not` (and any/all inversion)."""
    out = []
    for m in re.finditer(r"\bnot\s+", ms):
        out.append(_rep(line, m.start(), m.end(), ""))
    for kw in ("if", "elif", "while", "return", "and", "or", "assert"):
        for m in re.finditer(r"\b%s\s+" % kw, ms):
            if re.match(r"\bnot\b", ms[m.end():]):
                continue
            out.append(_rep(line, m.end(), m.end(), "not "))
    for s, e in _word_sites(ms, "any"):
        out.append(_rep(line, s, e, "all"))
    for s, e in _word_sites(ms, "all"):
        out.append(_rep(line, s, e, "any"))
    return out


_STR_FAMILIES = [
    ["bB", "oO", "xX"],
    ["b", "o", "x", "d", "n"],
    ["B", "O", "X"],
    ["AM", "PM"],
    ["-", "+"],
    ["<", ">", "=", "^"],
    ["0", "1"],
    [".", "_", "-"],
    ["Z", "UTC"],
    ["ti", "tg", "ta", "te", "th", "tc", "tt", "ts"],
    ["%y", "%Y"], ["%H", "%I"], ["%m", "%M"], ["%d", "%D"],
]


def _act_string_literal(line, ms):
    """kind 12: single-token damage inside a string / regex literal."""
    out = []
    lits = [m.span() for m in _STR_RE.finditer(line)]
    for s, e in lits:
        if e - s < 2:
            continue
        q = line[s]
        inner_s, inner_e = s + 1, e - 1
        inner = line[inner_s:inner_e]
        for fam in _STR_FAMILIES:
            if inner in fam:
                for alt in fam:
                    if alt != inner:
                        out.append(_rep(line, inner_s, inner_e, alt))
        # regex-level single token flips, at every site inside the literal
        for m in re.finditer(r"[+*?]", inner):
            for alt in ("+", "*", "?"):
                if alt != m.group(0):
                    out.append(_rep(line, inner_s + m.start(), inner_s + m.end(), alt))
        for m in re.finditer(r"\\[dwsDWS]", inner):
            tok = m.group(0)
            for alt in ("\\d", "\\w", "\\s", "\\S", "\\D"):
                if alt != tok:
                    out.append(_rep(line, inner_s + m.start(), inner_s + m.end(), alt))
        for m in re.finditer(r"[-+<>=^]", inner):
            flip = {"-": "+", "+": "-", "<": ">", ">": "<", "=": "^", "^": "="}
            out.append(_rep(line, inner_s + m.start(), inner_s + m.end(),
                            flip[m.group(0)]))
    # swap two string literals with each other
    for i in range(len(lits)):
        for j in range(i + 1, len(lits)):
            sw = _swap(line, lits[i][0], lits[i][1], lits[j][0], lits[j][1])
            if sw:
                out.append(sw)
    return out


_ACTS = [
    _act_int_offbyone,     # kind 0  -> act 5
    _act_addsub,           # kind 1  -> act 6
    _act_cmp_strictness,   # kind 2  -> act 7
    _act_equality,         # kind 3  -> act 8
    _act_bool_literal,     # kind 4  -> act 9
    _act_and_or,           # kind 5  -> act 10
    _act_slice_index,      # kind 6  -> act 11
    _act_swap_operands,    # kind 7  -> act 12
    _act_muldiv,           # kind 8  -> act 13
    _act_int_other,        # kind 9  -> act 14
    _act_name_confusion,   # kind 10 -> act 15
    _act_not,              # kind 11 -> act 16
    _act_string_literal,   # kind 12 -> act 17
]

_FIRST_ACT = WORKED_EXAMPLE[1] - WORKED_EXAMPLE[0]
_ACT_MODULUS = 16


def observe(line):
    k = []
    if line is None:
        return k
    # Every kind is offered for every line: an act that has nothing to say
    # simply returns [], and a missing candidate is far more expensive than
    # a spurious one.
    for i in range(len(_ACTS)):
        k.append(i)
    return k


def acts(line, act):
    out = []
    if line is None:
        return out
    try:
        idx = int(act) - _FIRST_ACT
    except (TypeError, ValueError):
        return out
    if idx < 0 or idx >= len(_ACTS):
        # the router numbers acts cyclically (it wraps once it runs out of
        # slots); undo the wrap the same way it was applied.
        idx = (int(act) - _FIRST_ACT) % _ACT_MODULUS
    if idx < 0 or idx >= len(_ACTS):
        return out
    ms = _mask(line)
    try:
        out = _ACTS[idx](line, ms) or []
    except Exception:
        out = []
    out = [c for c in out if isinstance(c, str) and c.strip() and c != line]
    return _uniq(out)

def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
