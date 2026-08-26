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
# Fault-kind taxonomy for this repository (humanize).
#
#   kind  0 (act  5) numeric literal off-by-one -- EVERY literal / digit run
#   kind  1 (act  6) comparison strictness      (<  <-> <=,  >  <-> >=)
#   kind  2 (act  7) comparison direction       (<  <-> >,   <= <-> >=)
#   kind  3 (act  8) equality / identity / membership flips
#   kind  4 (act  9) exhaustive comparison-operator substitution (safety net)
#   kind  5 (act 10) additive operator confusion (+ <-> -, += <-> -=, sign)
#   kind  6 (act 11) exhaustive arithmetic-operator substitution
#   kind  7 (act 12) boolean literal flip / `not` insertion + removal
#   kind  8 (act 13) and/or confusion (also all/any)
#   kind  9 (act 14) swapped operands / swapped call arguments
#   kind 10 (act 15) slice & index bound off-by-one
#   kind 11 (act 16) constant magnitude & domain-constant swap
#   kind 12 (act 17) name / attribute / method / marker-string confusion
#   kind 13 (act 18) off-by-one term insertion & removal (`x` <-> `x - 1`)
#   kind 14 (act 19) same-line identifier cross-substitution
#   kind 15 (act 20) call-wrapper insertion & removal (abs/int/round/str/...)
#
# The router numbers acts k + 5 within a wrap-around act space, so the act
# index is recovered as (act - 5) modulo the act-space size.
#
# observe() deliberately reports the whole contiguous kind space: applicability
# is decided inside each act (an act that does not apply returns []).  Missing a
# candidate is fatal, an extra candidate is cheap.
# ===========================================================================

N_KINDS = 16
FIRST_ACT = 5
ACT_SPACE = 16


# ---------------------------------------------------------------------------
# generic text helpers
# ---------------------------------------------------------------------------

def _split_eol(line):
    m = re.search(r"[\r\n]+\Z", line)
    if m:
        return line[: m.start()], m.group(0)
    return line, ""


def _rep(body, s, e, new):
    return body[:s] + new + body[e:]


_ATOM = (
    r"(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\[[^\[\]]*\]|\([^()]*\))*"
    r"|\d[\d_]*(?:\.\d+)?(?:[eE][-+]?\d+)?"
    r"|\"[^\"]*\"|'[^']*')"
)
_ATOM_END = re.compile(_ATOM + r"[ \t]*\Z")
_ATOM_START = re.compile(r"[ \t]*(" + _ATOM + r")")
_ATOM_ANY = re.compile(_ATOM)

_KEYWORDS = {
    "if", "elif", "else", "for", "in", "not", "and", "or", "return", "while",
    "def", "class", "import", "from", "is", "None", "True", "False", "lambda",
    "yield", "raise", "assert", "with", "as", "pass", "break", "continue",
    "del", "global", "try", "except", "finally", "await", "async",
}

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")": "(", "]": "[", "}": "{"}


def _groups(body):
    """All balanced bracket groups as (open_idx, close_idx, open_char)."""
    stack = []
    res = []
    for i, ch in enumerate(body):
        if ch in _OPEN:
            stack.append((ch, i))
        elif ch in _CLOSE:
            if stack and stack[-1][0] == _CLOSE[ch]:
                o, oi = stack.pop()
                res.append((oi, i, o))
            elif stack:
                stack.pop()
    return res


def _split_commas(s):
    parts = []
    depth = 0
    cur = []
    for ch in s:
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        if ch == "," and depth <= 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _slot(p):
    core = p.strip()
    lead = p[: len(p) - len(p.lstrip())]
    trail = p[len(p.rstrip()):] if core else ""
    return lead, core, trail


_FIELD_RE = re.compile(r"\{([^{}]*)\}")


def _fields(body):
    """Expression spans inside f-string replacement fields: (start, end, text).

    Seed fault 1 lived inside one of these, so every act has to be able to see
    through `f"...{expr}..."` -- the expression part only, never the !conv or
    the :format spec.
    """
    res = []
    for m in _FIELD_RE.finditer(body):
        inner = m.group(1)
        if not inner.strip():
            continue
        depth = 0
        cut = len(inner)
        for i, ch in enumerate(inner):
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif depth == 0 and ch == ":":
                cut = i
                break
            elif depth == 0 and ch == "!" and inner[i:i + 2] != "!=":
                cut = i
                break
        expr = inner[:cut]
        if not expr.strip():
            continue
        s = m.start(1)
        res.append((s, s + cut, expr))
    return res


def _expr_start(left):
    """Index in `left` where the value expression begins (past `x = `/`return`)."""
    best = len(left) - len(left.lstrip())
    depth = 0
    for i, ch in enumerate(left):
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        elif depth == 0 and ch == "=":
            if left[i - 1: i] in ("=", "!", "<", ">", "+", "-", "*", "/", "%"):
                continue
            if left[i + 1: i + 2] == "=":
                continue
            best = i + 1
    m = re.match(r"\A(\s*)(return|yield|assert)\s+", left)
    if m and m.end() > best:
        best = m.end()
    while best < len(left) and left[best] in " \t":
        best += 1
    return best


def _neg_expr(e):
    core = e.strip()
    if not core:
        return ""
    if core.startswith("-"):
        return core[1:].lstrip()
    return "-" + core


# ---------------------------------------------------------------------------
# numeric helpers
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"(?<![\w.])(\d[\d_]*)(?![\w.])")
_FLOAT_RE = re.compile(r"(?<![\w.])(\d[\d_]*\.\d+)(?![\w.])")
_SCI_RE = re.compile(r"(?<![\w.])(\d[\d_]*(?:\.\d+)?)([eE])([-+]?)(\d+)(?![\w.])")
_DIGITS_RE = re.compile(r"\d+")
# a numeric literal that may carry a unary minus (never a binary subtraction)
_SIGNED_FLOAT_RE = re.compile(
    r"(?<![\w.])(-?\d[\d_]*\.\d+)(?![\w.])"
)
_SIGNED_INT_RE = re.compile(
    r"(?<![\w.])(-\d[\d_]*)(?![\w.])"
)


def _fmt_ints(v, txt):
    """Render integer `v` the way `txt` was rendered (grouping / zero pad)."""
    if v < 0:
        return []
    outs = []
    s = str(v)
    if "_" in txt:
        outs.append(format(v, "_"))
        outs.append(s)
    else:
        if len(txt) > 1 and txt[0] == "0":
            outs.append(s.zfill(len(txt)))
        outs.append(s)
        # this codebase writes big literals both ways (1_000 and 1000)
        if v >= 1000:
            outs.append(format(v, "_"))
    seen = set()
    res = []
    for o in outs:
        if o not in seen:
            seen.add(o)
            res.append(o)
    return res


def _fmt_float(x):
    x = round(x, 10)
    if x == int(x) and abs(x) < 1e15:
        return "%.1f" % x
    return repr(x)


# ===========================================================================
# act 5 -- numeric literal off-by-one, at EVERY site
# ===========================================================================

def _act_numeric(body):
    out = []

    # whole integer literals (incl. 1_000_000 style grouping)
    for m in _INT_RE.finditer(body):
        txt = m.group(1)
        try:
            v = int(txt.replace("_", ""))
        except ValueError:
            continue
        for nv in (v + 1, v - 1, v + 2, v - 2):
            for s in _fmt_ints(nv, txt):
                out.append(_rep(body, m.start(1), m.end(1), s))

    # float literals (also with a leading unary minus, so 0.3 <-> -0.2 works)
    for m in _SIGNED_FLOAT_RE.finditer(body):
        txt = m.group(1)
        try:
            v = float(txt.replace("_", ""))
        except ValueError:
            continue
        dec = len(txt.split(".")[1]) if "." in txt else 1
        for nv in (v + 1, v - 1, v + 0.1, v - 0.1, v + 0.5, v - 0.5, -v):
            out.append(_rep(body, m.start(1), m.end(1), _fmt_float(nv)))
            # doctest output keeps trailing zeros ("1.00", "14308.40"),
            # so offer every plausible decimal width too
            for w in range(1, 5):
                if w == dec and abs(nv - v) < 1e-12:
                    continue
                out.append(_rep(body, m.start(1), m.end(1),
                                "%.*f" % (w, round(nv, 10))))
        for w in range(1, 5):
            out.append(_rep(body, m.start(1), m.end(1),
                            "%.*f" % (w, round(v, 10))))

    # signed integer literals: -1 <-> 1, -30 <-> -29, ...
    for m in _SIGNED_INT_RE.finditer(body):
        txt = m.group(1)
        try:
            v = int(txt.replace("_", ""))
        except ValueError:
            continue
        for nv in (v + 1, v - 1, -v, -v + 1, -v - 1):
            if nv == v:
                continue
            s = ("-" + format(-nv, "_")) if (nv < 0 and "_" in txt) \
                else str(nv)
            out.append(_rep(body, m.start(1), m.end(1), s))

    # scientific literals: perturb mantissa and exponent
    for m in _SCI_RE.finditer(body):
        mant, ee, sign, expo = m.group(1), m.group(2), m.group(3), m.group(4)
        try:
            ev = int(sign + expo) if sign else int(expo)
        except ValueError:
            continue
        for nev in (ev + 1, ev - 1, ev + 3, ev - 3):
            ns = "-" if nev < 0 else ("+" if sign == "+" else "")
            out.append(_rep(body, m.start(), m.end(),
                            "%s%s%s%d" % (mant, ee, ns, abs(nev))))
        try:
            mv = float(mant)
        except ValueError:
            mv = None
        if mv is not None:
            for nmv in (mv + 1, mv - 1):
                if nmv < 0:
                    continue
                nm = str(int(nmv)) if nmv == int(nmv) and "." not in mant \
                    else _fmt_float(nmv)
                out.append(_rep(body, m.start(), m.end(),
                                "%s%s%s%s" % (nm, ee, sign, expo)))

    # catch-all: EVERY raw digit run (format specs "%0.2f", ids like part1, ...)
    for m in _DIGITS_RE.finditer(body):
        txt = m.group(0)
        v = int(txt)
        prev_ch = body[m.start() - 1] if m.start() else ""
        next_ch = body[m.end()] if m.end() < len(body) else ""
        # zero padding only matters for runs that live inside a wider rendered
        # number ("1,000,000", "%0.2f") -- not for ordinary Python literals
        padded = txt[0] == "0" or prev_ch in ",." or next_ch == ","
        for nv in (v + 1, v - 1):
            if nv < 0:
                continue
            s = str(nv)
            if len(txt) > 1 and txt[0] == "0":
                s = s.zfill(len(txt))
            out.append(_rep(body, m.start(), m.end(), s))
            if padded:
                for w in range(len(txt), len(txt) + 4):
                    out.append(_rep(body, m.start(), m.end(), str(nv).zfill(w)))
        # digit-count slips: a run that gained or lost a digit
        if padded:
            out.append(_rep(body, m.start(), m.end(), txt.zfill(len(txt) + 1)))
            out.append(_rep(body, m.start(), m.end(), txt.zfill(len(txt) + 2)))
        out.append(_rep(body, m.start(), m.end(), txt + "0"))
        if len(txt) > 1:
            out.append(_rep(body, m.start(), m.end(), txt[1:]))
            out.append(_rep(body, m.start(), m.end(), txt[:-1]))

    return out


# ===========================================================================
# comparison-operator machinery (acts 6, 7, 8, 9)
# ===========================================================================

_CMP_SITE = re.compile(r"(?<![-<>=!+*/%])(<=|>=|==|!=|<|>)(?!=)")
_ALL_CMP = ("<", "<=", ">", ">=", "==", "!=")

_STRICTNESS = {"<": ["<="], "<=": ["<"], ">": [">="], ">=": [">"]}
_MIRROR = {"<": [">"], ">": ["<"], "<=": [">="], ">=": ["<="]}
_EQUALITY = {
    "==": ["!=", ">=", "<="],
    "!=": ["==", ">", "<"],
    ">=": ["=="],
    "<=": ["=="],
    ">": ["!="],
    "<": ["!="],
}


def _cmp_act(body, table):
    out = []
    for m in _CMP_SITE.finditer(body):
        op = m.group(1)
        for new in table.get(op, ()):
            out.append(_rep(body, m.start(1), m.end(1), new))
    return out


def _act_strictness(body):
    return _cmp_act(body, _STRICTNESS)


def _act_mirror(body):
    return _cmp_act(body, _MIRROR)


def _find_word(body, word):
    return list(re.finditer(r"\b" + word + r"\b", body))


def _act_equality(body):
    out = _cmp_act(body, _EQUALITY)

    # is / is not
    for m in re.finditer(r"\bis\s+not\b", body):
        out.append(_rep(body, m.start(), m.end(), "is"))
    for m in re.finditer(r"\bis\b", body):
        if re.match(r"\s+not\b", body[m.end():]):
            continue
        out.append(_rep(body, m.start(), m.end(), "is not"))

    # in / not in
    for m in re.finditer(r"\bnot\s+in\b", body):
        out.append(_rep(body, m.start(), m.end(), "in"))
    for m in re.finditer(r"\bin\b", body):
        if re.search(r"\bnot\s+\Z", body[: m.start()]):
            continue
        out.append(_rep(body, m.start(), m.end(), "not in"))

    return out


def _act_cmp_substitution(body):
    out = []
    for m in _CMP_SITE.finditer(body):
        op = m.group(1)
        for new in _ALL_CMP:
            if new == op:
                continue
            out.append(_rep(body, m.start(1), m.end(1), new))
    return out


# ===========================================================================
# arithmetic-operator machinery (acts 10, 11)
# ===========================================================================

# binary operator sites: something atom-ish on the left, atom-ish on the right
_BINOP_SITE = re.compile(
    r"(?<=[\w\)\]\"\'])[ \t]*(\*\*|//|[+\-*/])[ \t]*(?=[\w\(\[\"\'])"
)
# `%`: spaced form (`value % 100`) and tight form (`a%b`), but never the "%d"
# of a format spec, which is always preceded by a quote or a brace.
_MODOP_SITE = re.compile(
    r"(?<=[\w\)\]\"\'])[ \t]*(%)[ \t]*(?=[\w\(\[\"\'])"
)
_MODOP_TIGHT = re.compile(r"(?<=[\w\)\]])(%)(?=[\w\(\[])")
_AUGOP_SITE = re.compile(r"(\*\*=|//=|[+\-*/%]=)(?!=)")
_UNARY_MINUS = re.compile(r"(?<=[\(\[,=<>+\-*/%: ])(-)(?=[A-Za-z_\(\d])")

_ARITH = ("+", "-", "*", "/", "//", "%", "**")


def _binop_sites(body):
    sites = []
    for m in _BINOP_SITE.finditer(body):
        sites.append((m.start(1), m.end(1), m.group(1)))
    for m in _MODOP_SITE.finditer(body):
        sites.append((m.start(1), m.end(1), m.group(1)))
    for m in _MODOP_TIGHT.finditer(body):
        sites.append((m.start(1), m.end(1), m.group(1)))
    seen = set()
    uniq = []
    for s, e, op in sorted(sites):
        if (s, e) in seen:
            continue
        seen.add((s, e))
        uniq.append((s, e, op))
    return uniq


def _act_additive(body):
    out = []
    for s, e, op in _binop_sites(body):
        if op == "+":
            out.append(_rep(body, s, e, "-"))
        elif op == "-":
            out.append(_rep(body, s, e, "+"))
    for m in _AUGOP_SITE.finditer(body):
        op = m.group(1)
        if op == "+=":
            out.append(_rep(body, m.start(1), m.end(1), "-="))
        elif op == "-=":
            out.append(_rep(body, m.start(1), m.end(1), "+="))
    # unary sign: drop it, or introduce one
    for m in _UNARY_MINUS.finditer(body):
        out.append(_rep(body, m.start(1), m.end(1), ""))
    for m in re.finditer(r"(?:[\(\[,]|=|\breturn\b|[ \t])[ \t]*(?=[A-Za-z_\d])",
                         body):
        out.append(_rep(body, m.end(), m.end(), "-"))
    return out


def _act_arith_substitution(body):
    out = []
    for s, e, op in _binop_sites(body):
        for new in _ARITH:
            if new == op:
                continue
            out.append(_rep(body, s, e, new))
    for m in _AUGOP_SITE.finditer(body):
        op = m.group(1)
        for new in _ARITH:
            cand = new + "="
            if cand == op:
                continue
            out.append(_rep(body, m.start(1), m.end(1), cand))
    return out


# ===========================================================================
# act 12 -- boolean literals and `not`
# ===========================================================================

def _act_boolean(body):
    out = []
    for m in re.finditer(r"\bTrue\b", body):
        out.append(_rep(body, m.start(), m.end(), "False"))
    for m in re.finditer(r"\bFalse\b", body):
        out.append(_rep(body, m.start(), m.end(), "True"))

    # drop a `not`
    for m in re.finditer(r"\bnot[ \t]+", body):
        if re.search(r"\bis[ \t]+\Z", body[: m.start()]):
            continue
        if re.match(r"in\b", body[m.end():]):
            continue
        out.append(_rep(body, m.start(), m.end(), ""))

    # introduce a `not`
    for m in re.finditer(r"\b(if|elif|while|return|and|or|assert)[ \t]+", body):
        if re.match(r"not\b", body[m.end():]):
            continue
        out.append(_rep(body, m.end(), m.end(), "not "))
    for m in re.finditer(r"\bnot[ \t]+", body):
        out.append(_rep(body, m.end(), m.end(), "not "))
    # generic: a `not` can go missing anywhere a word begins
    for m in re.finditer(r"[ \t(](?=[A-Za-z_`'\"(\[])", body):
        if re.match(r"not\b", body[m.end():]):
            continue
        out.append(_rep(body, m.end(), m.end(), "not "))
    return out


# ===========================================================================
# act 13 -- and / or
# ===========================================================================

def _act_andor(body):
    out = []
    for m in re.finditer(r"\band\b", body):
        out.append(_rep(body, m.start(), m.end(), "or"))
    for m in re.finditer(r"\bor\b", body):
        out.append(_rep(body, m.start(), m.end(), "and"))
    for m in re.finditer(r"\ball\b", body):
        out.append(_rep(body, m.start(), m.end(), "any"))
    for m in re.finditer(r"\bany\b", body):
        out.append(_rep(body, m.start(), m.end(), "all"))
    return out


# ===========================================================================
# act 14 -- swapped operands / swapped arguments
# ===========================================================================

_SWAP_OPS = re.compile(
    r"(\*\*=|//=|[-+*/%]=|\*\*|//|<=|>=|==|!=|[-+*/%<>=])"
)
# a bare dotted name, so `x = f(a, b)` can transpose to `f = x(a, b)`
_NAME_END = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*[ \t]*\Z")
_NAME_START = re.compile(r"[ \t]*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")


def _swap_around(body, s, e, end_re=None, start_re=None):
    left = body[:s]
    right = body[e:]
    ml = (end_re or _ATOM_END).search(left)
    mr = (start_re or _ATOM_START).match(right)
    if not ml or not mr:
        return None
    la = left[ml.start():].rstrip()
    lpad = left[ml.start() + len(la):]
    ra = mr.group(1)
    rpad = right[: mr.start(1)]
    if not la or not ra or la == ra:
        return None
    return (left[: ml.start()] + ra + lpad + body[s:e] + rpad + la
            + right[mr.end(1):])


def _act_swap(body):
    out = []

    # swap the two operands of every binary/comparison/assignment operator
    for m in _SWAP_OPS.finditer(body):
        if body[m.start():m.start() + 2] == "->":
            continue
        if body[m.start() - 1: m.start() + 1] == "->":
            continue
        for er, sr in ((None, None), (_NAME_END, _NAME_START)):
            cand = _swap_around(body, m.start(), m.end(), er, sr)
            if cand:
                out.append(cand)
    for m in re.finditer(r"[ \t]+(?:and|or|in|is)[ \t]+", body):
        for er, sr in ((None, None), (_NAME_END, _NAME_START)):
            cand = _swap_around(body, m.start(), m.end(), er, sr)
            if cand:
                out.append(cand)

    # swap arguments / elements inside every bracket group
    for oi, ci, och in _groups(body):
        inner = body[oi + 1: ci]
        if not inner.strip():
            continue
        parts = _split_commas(inner)
        if len(parts) < 2 or len(parts) > 6:
            continue
        slots = [_slot(p) for p in parts]
        n = len(slots)
        pairs = [(i, i + 1) for i in range(n - 1)]
        if n <= 4:
            pairs += [(i, j) for i in range(n) for j in range(i + 2, n)]
        for i, j in pairs:
            new = list(slots)
            new[i] = (slots[i][0], slots[j][1], slots[i][2])
            new[j] = (slots[j][0], slots[i][1], slots[j][2])
            rebuilt = ",".join(a + b + c for a, b, c in new)
            out.append(body[: oi + 1] + rebuilt + body[ci:])

    # swap the targets of a tuple assignment: `years, days = ...`
    m = re.match(r"\A([ \t]*)([A-Za-z_][\w\s,.\[\]]*?)[ \t]*=[ \t]*(?!=)(.*)\Z",
                 body)
    if m and "," in m.group(2):
        parts = _split_commas(m.group(2))
        slots = [_slot(p) for p in parts]
        for i in range(len(slots)):
            for j in range(i + 1, len(slots)):
                new = list(slots)
                new[i] = (slots[i][0], slots[j][1], slots[i][2])
                new[j] = (slots[j][0], slots[i][1], slots[j][2])
                lhs = ",".join(a + b + c for a, b, c in new)
                out.append(m.group(1) + lhs + " = " + m.group(3))

    # swap two f-string replacement fields:  f"{a}/{b}" -> f"{b}/{a}"
    flds = _fields(body)
    for i in range(len(flds)):
        for j in range(i + 1, len(flds)):
            s1, e1, x1 = flds[i]
            s2, e2, x2 = flds[j]
            if x1 == x2:
                continue
            out.append(body[:s1] + x2 + body[e1:s2] + x1 + body[e2:])

    # swap the branches of a conditional expression:
    #   `a if cond else b`  ->  `b if cond else a`
    out.extend(_ternary_swaps(body))

    # transpose the two sides of an assignment: `x = f(y)` -> `f(y) = x`
    asg = _top_level_assign(body)
    if asg:
        indent, lhs, rhs = asg
        out.append(indent + rhs + " = " + lhs)
    return out


def _top_level_assign(body):
    depth = 0
    for i, ch in enumerate(body):
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        elif depth == 0 and ch == "=":
            if body[i - 1: i] in ("=", "!", "<", ">", "+", "-", "*", "/", "%",
                                  ":"):
                continue
            if body[i + 1: i + 2] == "=":
                continue
            lhs = body[:i].strip()
            rhs = body[i + 1:].strip()
            indent = body[: len(body) - len(body.lstrip())]
            if not lhs or not rhs or lhs == rhs:
                return None
            return indent, lhs, rhs
    return None


def _ternary_swaps(body):
    out = []
    depth = 0
    ifs = []
    elses = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        elif depth == 0:
            if body.startswith(" if ", i):
                ifs.append(i)
            elif body.startswith(" else ", i):
                elses.append(i)
        i += 1
    for a in ifs:
        for b in elses:
            if b <= a + 4:
                continue
            left = body[:a]
            cond = body[a + 4: b]
            right = body[b + 6:]
            if not cond.strip() or not right.strip():
                continue
            st = _expr_start(left)
            true_branch = left[st:]
            if not true_branch.strip():
                continue
            out.append(left[:st] + right + " if " + cond + " else "
                       + true_branch)
            # also: negate-free reordering of just the condition operands
            out.append(left[:st] + true_branch + " if " + right + " else "
                       + cond)
    return out


# ===========================================================================
# act 15 -- slice and index bounds
# ===========================================================================

def _shift_expr(e, allow_empty):
    lead, core, trail = _slot(e)

    def wrap(x):
        return lead + x + trail

    out = []
    if core == "":
        if allow_empty:
            out += ["0", "1", "-1", "2", "-2"]
        return out

    if re.fullmatch(r"[-+]?\d+", core):
        v = int(core)
        for nv in (v + 1, v - 1, -v, v + 2, v - 2):
            if nv == v:
                continue
            out.append(wrap(str(nv)))
        if allow_empty:
            out.append("")
        return out

    m = re.fullmatch(r"(.*\S)[ \t]*([+-])[ \t]*(\d+)", core)
    if m:
        base, op, num = m.group(1), m.group(2), int(m.group(3))
        out.append(wrap(base))
        out.append(wrap("%s %s %d" % (base, "+" if op == "-" else "-", num)))
        for nn in (num + 1, num - 1):
            if nn == 0:
                out.append(wrap(base))
            elif nn > 0:
                out.append(wrap("%s %s %d" % (base, op, nn)))
        if allow_empty:
            out.append("")
        return out

    out.append(wrap(core + " - 1"))
    out.append(wrap(core + " + 1"))
    if core.startswith("-"):
        out.append(wrap(core[1:].lstrip()))
    else:
        out.append(wrap("-" + core))
    if allow_empty:
        out.append("")
    return out


def _act_slice(body):
    out = []
    for oi, ci, och in _groups(body):
        if och != "[":
            continue
        inner = body[oi + 1: ci]
        variants = set()
        if ":" in inner and "{" not in inner:
            parts = inner.split(":")
            for i, p in enumerate(parts):
                for np in _shift_expr(p, True):
                    new = list(parts)
                    new[i] = np
                    variants.add(":".join(new))
            if len(parts) == 2:
                variants.add(parts[1] + ":" + parts[0])
                # every recombination of the bounds and their sign flips:
                # covers  [:-1] <-> [1:],  [:1] <-> [-1:],  [:-1] <-> [:]
                pool = {""}
                for p in parts:
                    c = p.strip()
                    if c:
                        pool.add(c)
                        pool.add(_neg_expr(c))
                        m2 = re.fullmatch(r"[-+]?\d+", c)
                        if m2:
                            v = int(c)
                            pool.add(str(v + 1))
                            pool.add(str(v - 1))
                            pool.add(str(-(v + 1)))
                            pool.add(str(-(v - 1)))
                for lo in pool:
                    for hi in pool:
                        variants.add(lo + ":" + hi)
        else:
            for np in _shift_expr(inner, False):
                variants.add(np)
            core = inner.strip()
            if core:
                variants.add(":" + core)
                variants.add(core + ":")
        for v in variants:
            out.append(body[: oi + 1] + v + body[ci:])
    return out


# ===========================================================================
# act 16 -- constant magnitude / domain-constant swap
# ===========================================================================

_CONST_NEIGHBOURS = {
    0: (1, 2), 1: (0, 2, 3), 2: (1, 3, 4), 3: (2, 4, 6, 12),
    4: (3, 5, 8), 5: (4, 6, 10, 12), 6: (5, 7, 12), 7: (6, 8, 5),
    8: (7, 9), 9: (8, 10), 10: (9, 11, 12, 16, 100, 1000),
    11: (10, 12), 12: (11, 13, 10, 24, 60), 13: (12, 14, 11),
    16: (15, 17, 10), 20: (19, 21, 24), 23: (24, 22),
    24: (23, 25, 12, 60, 7, 48, 3600), 28: (29, 30, 27),
    29: (28, 30), 30: (29, 31, 28, 24, 7, 365, 12),
    31: (30, 32, 28, 29, 12), 33: (32, 34, 30, 3, 36),
    52: (53, 51, 12), 59: (60, 58), 60: (59, 61, 24, 30, 3600, 100, 1000),
    64: (63, 65, 32), 99: (100, 98), 100: (99, 101, 10, 1000, 60),
    128: (127, 129, 256), 255: (256, 254), 256: (255, 257, 128, 512),
    360: (365, 359, 361), 364: (365, 363), 365: (366, 364, 360, 12, 30, 52),
    366: (365, 367), 999: (1000, 998), 1000: (1024, 999, 1001, 100, 10000, 60),
    1024: (1000, 1023, 1025, 2048, 512), 1440: (1441, 1439, 3600, 24, 60),
    3599: (3600, 3598), 3600: (3599, 3601, 60, 86400, 24, 1440, 360),
    3601: (3600, 3602), 86400: (3600, 86399, 86401, 24),
    100000: (1000000, 10000), 1000000: (100000, 10000000, 1000),
}

_SCALES = (2, 3, 10, 12, 24, 60, 100, 1000)


def _act_constants(body):
    out = []
    for m in _INT_RE.finditer(body):
        txt = m.group(1)
        try:
            v = int(txt.replace("_", ""))
        except ValueError:
            continue
        cands = set()
        for f in _SCALES:
            if v <= 10_000_000:
                cands.add(v * f)
            if f and v % f == 0:
                cands.add(v // f)
        for d in (3, 5, 10, 100):
            cands.add(v + d)
            cands.add(v - d)
        cands.update(_CONST_NEIGHBOURS.get(v, ()))
        cands.add(0)
        cands.add(1)
        for nv in sorted(cands):
            if nv < 0 or nv == v:
                continue
            for s in _fmt_ints(nv, txt):
                out.append(_rep(body, m.start(1), m.end(1), s))

    for m in _FLOAT_RE.finditer(body):
        txt = m.group(1)
        try:
            v = float(txt.replace("_", ""))
        except ValueError:
            continue
        cands = {v * 2, v / 2, v * 10, v / 10, v + 5, v - 5,
                 float(int(v)), float(int(v) + 1)}
        for nv in cands:
            if nv == v:
                continue
            out.append(_rep(body, m.start(1), m.end(1), _fmt_float(nv)))
    return out


# ===========================================================================
# act 17 -- name / attribute / method / marker-string confusion
# ===========================================================================

_PAIRS = [
    ("min", "max"), ("floor", "ceil"), ("floor_token", "ceil_token"),
    ("left", "right"), ("first", "last"), ("start", "end"),
    ("startswith", "endswith"), ("upper", "lower"), ("lstrip", "rstrip"),
    ("append", "insert"), ("append", "extend"), ("keys", "values"),
    ("sorted", "reversed"), ("bisect_left", "bisect_right"),
    ("isinf", "isnan"), ("isfinite", "isinf"),
    ("int", "round"), ("round", "ceil"), ("int", "floor"), ("abs", "int"),
    ("days", "seconds"), ("seconds", "microseconds"), ("days", "microseconds"),
    ("seconds", "milliseconds"), ("milliseconds", "microseconds"),
    ("hours", "minutes"), ("minutes", "seconds"), ("hours", "days"),
    ("years", "months"), ("months", "days"), ("years", "days"),
    ("year", "month"), ("month", "day"), ("day", "hour"), ("hour", "minute"),
    ("minute", "second"), ("second", "millisecond"),
    ("millisecond", "microsecond"), ("second", "microsecond"),
    ("singular", "plural"), ("singular_txt", "plural_txt"),
    ("numerator", "denominator"), ("whole_number", "number"),
    ("binary", "gnu"), ("gnu", "decimal"), ("binary", "decimal"),
    ("head", "tail"), ("part1", "part2"), ("value", "other"),
    ("break", "continue"), ("today", "now"), ("now", "value"),
    ("future", "past"), ("q", "r"), ("exp", "exponent"),
    ("old_bucket", "new_bucket"), ("delta", "value"), ("date", "delta"),
    ("thousands_separator", "decimal_separator"),
    ("thousands_sep", "decimal_sep"),
    ("_gettext", "_ngettext"), ("naturalday", "naturaldate"),
    ("naturaldelta", "naturaltime"), ("ordinal", "largest_ordinal"),
    ("suffix", "suffixes"), ("suppress", "suppress_set"),
    ("min_unit", "minimum_unit"), ("unit", "min_unit"),
    ("today", "tomorrow"), ("tomorrow", "yesterday"), ("today", "yesterday"),
    ("male", "female"), ("base", "exp"), ("space", "unit"),
    ("bytes_", "abs_bytes"), ("format", "value"), ("precision", "digits"),
    ("digits", "exponent"), ("negative_prefix", "prefix"),
    ("power", "powers"), ("chopped", "rounded_value"),
    ("rounded_value", "chopped"), ("texts", "fmts"), ("fmt", "fmts"),
    ("msecs", "usecs"), ("secs", "usecs"), ("secs", "msecs"),
    ("mins", "secs"), ("hours", "secs"), ("days", "secs"),
    ("value", "values"), ("item", "items"), ("locale", "path"),
    ("frac", "number"), ("divisor", "value"), ("quotient", "remainder"),
]

_CHAINS = [
    ["MICROSECONDS", "MILLISECONDS", "SECONDS", "MINUTES", "HOURS", "DAYS",
     "MONTHS", "YEARS"],
]

_NAME_ALT = {}


def _add_alt(a, b):
    _NAME_ALT.setdefault(a, set()).add(b)


for _a, _b in _PAIRS:
    _add_alt(_a, _b)
    _add_alt(_b, _a)
for _chain in _CHAINS:
    for _i, _n in enumerate(_chain):
        for _j, _o in enumerate(_chain):
            if _i != _j:
                _add_alt(_n, _o)

_NAME_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(k) for k in _NAME_ALT),
                             key=len, reverse=True)) + r")\b"
)

_WRAPPERS = ("reversed", "sorted", "abs", "int", "float", "str", "round",
             "list", "set", "tuple", "len", "intcomma", "_")

_STR_SWAPS = [
    ("%d", "%s"), ("%s", "%d"), ("%d", "%i"), ("%i", "%d"),
    ('", "', '" "'), ('" "', '", "'), ('", "', '"."'),
    ('"-"', '"+"'), ('"+"', '"-"'), ('"<"', '">"'), ('">"', '"<"'),
    ('"."', '","'), ('","', '"."'), ('""', '" "'),
    ("'-'", "'+'"), ("'<'", "'>'"),
]


def _act_names(body):
    out = []
    for m in _NAME_RE.finditer(body):
        for alt in sorted(_NAME_ALT.get(m.group(1), ())):
            out.append(_rep(body, m.start(1), m.end(1), alt))

    # drop a wrapping call: str(x) -> x, reversed(x) -> x, abs(x) -> x ...
    for oi, ci, och in _groups(body):
        if och != "(":
            continue
        mprev = re.search(r"([A-Za-z_]\w*)\Z", body[:oi])
        if not mprev:
            continue
        if mprev.group(1) not in _WRAPPERS:
            continue
        inner = body[oi + 1: ci]
        if not inner.strip() or len(_split_commas(inner)) != 1:
            continue
        out.append(body[: mprev.start(1)] + inner + body[ci + 1:])

    for a, b in _STR_SWAPS:
        idx = 0
        while True:
            i = body.find(a, idx)
            if i < 0:
                break
            out.append(body[:i] + b + body[i + len(a):])
            idx = i + 1
    return out


# ===========================================================================
# act 18 -- off-by-one term insertion / removal
# ===========================================================================

_PM_ONE = re.compile(r"[ \t]*([+-])[ \t]*1\b")


def _act_offbyone_term(body):
    out = []

    # remove an existing "+ 1" / "- 1" term (every site)
    for m in _PM_ONE.finditer(body):
        if m.start() == 0:
            continue
        prev = body[m.start() - 1]
        if not (prev.isalnum() or prev in "_)]\"'"):
            continue
        out.append(_rep(body, m.start(), m.end(), ""))

    # introduce a "+ 1" / "- 1" after each atom that ends a sub-expression
    for m in _ATOM_ANY.finditer(body):
        txt = m.group(0)
        if txt in _KEYWORDS:
            continue
        rest = body[m.end():]
        nxt = rest.lstrip(" \t")
        if nxt and nxt[0] not in ")],:;" and not nxt.startswith("==") \
                and not nxt.startswith("<") and not nxt.startswith(">") \
                and not nxt.startswith("!="):
            continue
        out.append(_rep(body, m.end(), m.end(), " - 1"))
        out.append(_rep(body, m.end(), m.end(), " + 1"))

    # same, but inside f-string replacement fields
    for s, e, expr in _fields(body):
        core = expr.rstrip()
        if not core.strip():
            continue
        p = s + len(core)
        out.append(_rep(body, p, p, " - 1"))
        out.append(_rep(body, p, p, " + 1"))
        m2 = re.search(r"[ \t]*[+-][ \t]*1\Z", core)
        if m2:
            out.append(_rep(body, s + m2.start(), s + m2.end(), ""))
    return out


# ===========================================================================
# act 19 -- same-line identifier cross-substitution
#           (`secs` <-> `usecs`, `min_unit` <-> `unit`, `days` <-> `hours`, ...)
# ===========================================================================

_IDENT_RE = re.compile(r"\b[A-Za-z_]\w*\b")

_NON_SWAPPABLE = _KEYWORDS | {
    "self", "cls", "def", "print", "isinstance", "type", "dt", "math", "re",
    "f", "b", "r", "u",
}


def _act_ident_swap(body):
    names = []
    for m in _IDENT_RE.finditer(body):
        w = m.group(0)
        if w in _NON_SWAPPABLE or w in names:
            continue
        names.append(w)
    if len(names) < 2:
        return []
    out = []
    # one occurrence at a time
    for m in _IDENT_RE.finditer(body):
        w = m.group(0)
        if w in _NON_SWAPPABLE:
            continue
        for other in names:
            if other == w:
                continue
            out.append(_rep(body, m.start(), m.end(), other))

    # every occurrence at once: a genuine transposition of two variables,
    # e.g. `part1 + ... + part2` -> `part2 + ... + part1`
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            pat = re.compile(r"\b(" + re.escape(a) + r"|" + re.escape(b)
                             + r")\b")
            out.append(pat.sub(lambda m2: b if m2.group(1) == a else a, body))
            # and a one-way rename of all occurrences
            out.append(re.sub(r"\b" + re.escape(a) + r"\b", b, body))
            out.append(re.sub(r"\b" + re.escape(b) + r"\b", a, body))
    return out


# ===========================================================================
# act 20 -- call-wrapper insertion / removal
# ===========================================================================

_WRAP_NAMES = ("abs", "int", "round", "float", "str", "len", "reversed",
               "sorted", "list", "set", "tuple", "max", "min", "_",
               "intcomma", "_format_not_finite")

_BARE_IDENT = re.compile(r"(?<![\w.])([A-Za-z_]\w*)(?![\w(])")


def _wrap_spans(body):
    """Every span that could plausibly have lost a surrounding call."""
    spans = []
    for m in _ATOM_ANY.finditer(body):
        if m.group(0) not in _KEYWORDS:
            prev = body[m.start() - 1] if m.start() else ""
            if not (prev.isalnum() or prev in "_."):
                spans.append((m.start(), m.end()))
    for m in _BARE_IDENT.finditer(body):
        if m.group(1) not in _KEYWORDS:
            spans.append((m.start(1), m.end(1)))
    # whole arguments / elements of every bracket group
    for oi, ci, och in _groups(body):
        inner = body[oi + 1: ci]
        if not inner.strip():
            continue
        pos = oi + 1
        for part in _split_commas(inner):
            lead, core, trail = _slot(part)
            if core and core not in _KEYWORDS:
                spans.append((pos + len(lead), pos + len(lead) + len(core)))
            pos += len(part) + 1
    # the whole right-hand side of an assignment / return expression
    asg = _top_level_assign(body)
    if asg:
        i = body.rindex(asg[2])
        spans.append((i, i + len(asg[2])))
    m = re.match(r"\A\s*(?:return|yield|assert)\s+(\S.*?)\s*\Z", body)
    if m:
        spans.append((m.start(1), m.end(1)))
    seen = set()
    uniq = []
    for sp in spans:
        if sp in seen or sp[0] >= sp[1]:
            continue
        seen.add(sp)
        uniq.append(sp)
    return uniq


def _act_wrapper(body):
    out = []

    # removal: any single-argument call  name(inner) -> inner
    for oi, ci, och in _groups(body):
        if och != "(":
            continue
        mprev = re.search(r"([A-Za-z_][\w.]*)\Z", body[:oi])
        if not mprev:
            continue
        inner = body[oi + 1: ci]
        if not inner.strip() or len(_split_commas(inner)) != 1:
            continue
        out.append(body[: mprev.start(1)] + inner + body[ci + 1:])
        # keep the call, drop only the outermost name (rare, but cheap)
        out.append(body[: mprev.start(1)] + inner.strip() + body[ci + 1:])

    # insertion: wrap each plausible span in a common numeric/text helper
    for s, e in _wrap_spans(body):
        txt = body[s:e]
        for w in _WRAP_NAMES:
            out.append(body[:s] + w + "(" + txt + ")" + body[e:])

    # insertion inside f-string replacement fields: f"{x:.0f}" -> f"{abs(x):.0f}"
    for s, e, expr in _fields(body):
        core = expr.strip()
        if not core:
            continue
        lead = expr[: len(expr) - len(expr.lstrip())]
        trail = expr[len(expr.rstrip()):]
        for w in _WRAP_NAMES:
            out.append(body[:s] + lead + w + "(" + core + ")" + trail
                       + body[e:])
    return out


# ===========================================================================
# dispatch
# ===========================================================================

_ACT_FNS = [
    _act_numeric,              # act 5   (kind 0)
    _act_strictness,           # act 6   (kind 1)
    _act_mirror,               # act 7   (kind 2)
    _act_equality,             # act 8   (kind 3)
    _act_cmp_substitution,     # act 9   (kind 4)
    _act_additive,             # act 10  (kind 5)
    _act_arith_substitution,   # act 11  (kind 6)
    _act_boolean,              # act 12  (kind 7)
    _act_andor,                # act 13  (kind 8)
    _act_swap,                 # act 14  (kind 9)
    _act_slice,                # act 15  (kind 10)
    _act_constants,            # act 16  (kind 11)
    _act_names,                # act 17  (kind 12)
    _act_offbyone_term,        # act 18  (kind 13)
    _act_ident_swap,           # act 19  (kind 14)
    _act_wrapper,              # act 20  (kind 15)
]


def observe(line):
    k = []
    if not isinstance(line, str):
        return k
    # Applicability is decided per-act; report the full contiguous kind space
    # so no candidate is ever lost to an over-eager pre-filter.
    for i in range(N_KINDS):
        k.append(i)
    return k


def acts(line, act):
    out = []
    if not isinstance(line, str):
        return out
    # the router hands back act numbers in a wrap-around space; recover the
    # kind index the same way it was produced.
    idx = (act - FIRST_ACT) % ACT_SPACE
    if idx >= len(_ACT_FNS):
        idx = act - FIRST_ACT
    if idx < 0 or idx >= len(_ACT_FNS):
        return out
    body, eol = _split_eol(line)
    try:
        raw = _ACT_FNS[idx](body)
    except Exception:
        raw = []
    seen = set()
    for c in raw:
        if not isinstance(c, str) or c == body:
            continue
        full = c + eol
        if full == line or full in seen:
            continue
        seen.add(full)
        out.append(full)
    return [c for c in out if c != line]


def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
