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
r"""EXTENDED ACT DICTIONARY -- the 'company custom file' hypothesis.

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
# Low level lexical helpers.  Everything here is pure text; the only structural
# trick is a mask of the line in which the *contents* of string literals and
# comments are replaced by underscores so that bracket / comma / keyword
# scanning is not confused by punctuation that lives inside a quoted regex
# (this codebase is full of quoted regexes).
# ===========================================================================

_ACT_BASE = WORKED_EXAMPLE[1] - WORKED_EXAMPLE[0]   # == 5
_N_KINDS = 16                                       # router wraps modulo 16
_ACT_RING = 16


def _mask(line):
    """Same-length copy of *line* with string/comment interiors neutralised."""
    out = []
    i = 0
    n = len(line)
    quote = None
    while i < n:
        ch = line[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:
                out.append("__")
                i += 2
                continue
            if line.startswith(quote, i):
                out.append("_" * len(quote))
                i += len(quote)
                quote = None
                continue
            out.append("_")
            i += 1
            continue
        if ch == "#":
            out.append("_" * (n - i))
            break
        if ch in "\"'":
            quote = ch * 3 if line.startswith(ch * 3, i) else ch
            out.append("_" * len(quote))
            i += len(quote)
            continue
        out.append(ch)
        i += 1
    m = "".join(out)
    if len(m) < len(line):
        m = m + "_" * (len(line) - len(m))
    return m[: len(line)]


def _depths(m):
    """Nesting depth of every character of the masked line."""
    d = []
    lvl = 0
    for ch in m:
        if ch in ")]}":
            lvl = lvl - 1 if lvl > 0 else 0
            d.append(lvl)
        else:
            d.append(lvl)
            if ch in "([{":
                lvl += 1
    return d


def _groups(m):
    """All balanced bracket pairs -> (open_idx, close_idx, open_char)."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    res = []
    for i, ch in enumerate(m):
        if ch in "([{":
            stack.append((ch, i))
        elif ch in ")]}":
            if stack and stack[-1][0] == pairs[ch]:
                o, oi = stack.pop()
                res.append((oi, i, o))
            else:
                del stack[:]
    return res


def _split_top(text, sep=","):
    """Split *text* on top-level occurrences of the single char *sep*."""
    m = _mask(text)
    d = _depths(m)
    parts = []
    start = 0
    for i, ch in enumerate(m):
        if ch == sep and d[i] == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _put(line, s, e, new):
    return line[:s] + new + line[e:]


# --- operator tokenisation -------------------------------------------------

_TOKENS = [
    "**=", "//=", "<<=", ">>=",
    "==", "!=", "<=", ">=", "//", "**", "<<", ">>",
    "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
    "<", ">", "+", "-", "*", "/", "%", "&", "|", "^", "=",
]
_TOKENS.sort(key=len, reverse=True)

_CMP = ("==", "!=", "<=", ">=", "<", ">")
_SHIFT = ("<<", ">>")
_ARITH = ("+", "-", "*", "/", "//", "%", "**")
_BITS = ("&", "|", "^")
_AUG = ("+=", "-=", "*=", "/=", "//=", "%=", "**=", "&=", "|=", "^=", "<<=", ">>=")


def _op_sites(line, wanted):
    """(start, end, token) for every operator token of *line* in *wanted*.

    Longest match wins, so ``>=`` is one site and never two.  ``->`` is *not*
    a token, which is deliberate: a broken ``) ->= bool:`` then exposes a real
    ``>=`` site whose repair back to ``>`` restores the annotation arrow.
    """
    sites = []
    i = 0
    n = len(line)
    while i < n:
        for tok in _TOKENS:
            if line.startswith(tok, i):
                if tok in wanted:
                    sites.append((i, i + len(tok), tok))
                i += len(tok)
                break
        else:
            i += 1
    return sites


def _is_plain_assign(line, s, e, tok):
    """True for a statement-level ``=`` (spaces both sides), not a kwarg."""
    if tok != "=":
        return True
    return s > 0 and line[s - 1] == " " and e < len(line) and line[e] == " "


def _cross(line, sites, repls, guard=None):
    out = []
    for s, e, tok in sites:
        if guard is not None and not guard(line, s, e, tok):
            continue
        for r in repls:
            if r == tok:
                continue
            out.append(_put(line, s, e, r))
    return out


# --- word level helpers ----------------------------------------------------

def _word_sites(m, word):
    return [mt.span() for mt in re.finditer(r"\b" + re.escape(word) + r"\b", m)]


def _swap_words(line, a, b):
    """Every single-site swap of word *a* -> *b* and *b* -> *a*, plus the
    global swap of both when several sites exist."""
    m = _mask(line)
    out = []
    for src, dst in ((a, b), (b, a)):
        spans = _word_sites(m, src)
        for s, e in spans:
            out.append(_put(line, s, e, dst))
        if len(spans) > 1:
            new = line
            for s, e in reversed(spans):
                new = _put(new, s, e, dst)
            out.append(new)
    return out


def _swap_text(line, a, b, masked=False):
    """Single-site substring substitutions in both directions."""
    hay = _mask(line) if masked else line
    out = []
    for src, dst in ((a, b), (b, a)):
        start = 0
        while True:
            i = hay.find(src, start)
            if i < 0:
                break
            out.append(_put(line, i, i + len(src), dst))
            start = i + 1
    return out


# --- atom extraction (for operand swapping) --------------------------------

_ATOMCH = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.")


def _atom_left(m, i):
    """Span of the expression atom that ends just before index *i*."""
    j = i
    while j > 0 and m[j - 1] == " ":
        j -= 1
    end = j
    if end == 0:
        return None
    for _ in range(8):
        if j > 0 and m[j - 1] in ")]}":
            depth = 0
            k = j - 1
            while k >= 0:
                if m[k] in ")]}":
                    depth += 1
                elif m[k] in "([{":
                    depth -= 1
                    if depth == 0:
                        break
                k -= 1
            if k < 0:
                return None
            j = k
            while j > 0 and m[j - 1] in _ATOMCH:
                j -= 1
            if j > 0 and m[j - 1] in ")]}":
                continue
            break
        while j > 0 and m[j - 1] in _ATOMCH:
            j -= 1
        break
    if j >= end:
        return None
    return (j, end)


def _atom_right(m, i):
    """Span of the expression atom that starts at/after index *i*."""
    n = len(m)
    j = i
    while j < n and m[j] == " ":
        j += 1
    start = j
    if start >= n:
        return None
    if m[j] in "+-~":
        j += 1
    while j < n and m[j] in _ATOMCH:
        j += 1
    for _ in range(8):
        if j < n and m[j] in "([{":
            depth = 0
            k = j
            while k < n:
                if m[k] in "([{":
                    depth += 1
                elif m[k] in ")]}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if k >= n:
                return None
            j = k + 1
            while j < n and m[j] in _ATOMCH:
                j += 1
            continue
        break
    if j <= start:
        return None
    return (start, j)


def _uniq(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ===========================================================================
# Literal helpers
# ===========================================================================

_INT_RE = re.compile(r"(?<![\w.])(\d+)(?![\w.])")
_HEX_RE = re.compile(r"(?<![\w.])(0[xX])([0-9A-Fa-f]+)(?![\w.])")


def _int_shifts(line):
    out = []
    for mt in _HEX_RE.finditer(line):
        pre, body = mt.group(1), mt.group(2)
        try:
            v = int(body, 16)
        except ValueError:
            continue
        for nv in (v - 1, v + 1):
            if nv < 0:
                continue
            txt = format(nv, "x")
            if body.isupper() or (body.upper() == body and body.isalnum()):
                txt = txt.upper()
            txt = txt.rjust(len(body), "0")
            out.append(_put(line, mt.start(), mt.end(), pre + txt))
    for mt in _INT_RE.finditer(line):
        body = mt.group(1)
        try:
            v = int(body)
        except ValueError:
            continue
        s, e = mt.start(), mt.end()
        for nv in (v - 1, v + 1):
            txt = str(nv)
            if len(body) > 1 and body[0] == "0" and nv >= 0:
                txt = txt.rjust(len(body), "0")
            out.append(_put(line, s, e, txt))
        # sign handling: a literal carrying a unary minus is off-by-one in the
        # other direction, and a bare literal may have lost its minus.
        j = s - 1
        while j >= 0 and line[j] == " ":
            j -= 1
        if j >= 0 and line[j] == "-":
            k = j - 1
            while k >= 0 and line[k] == " ":
                k -= 1
            if k < 0 or line[k] in "([{,:=<>+-*/%&|^ ":
                out.append(_put(line, j, e, str(v)))
                for nv in (-v - 1, -v + 1):
                    out.append(_put(line, j, e, str(nv)))
        else:
            out.append(_put(line, s, e, "-" + body))
    return out


def _string_spans(line):
    """Spans of the string literals of *line* (quotes included)."""
    m = _mask(line)
    spans = []
    i = 0
    n = len(line)
    while i < n:
        if m[i] == "_" and line[i] in "\"'":
            j = i + 1
            while j < n and m[j] == "_":
                j += 1
            spans.append((i, j))
            i = j
        else:
            i += 1
    return spans


# ===========================================================================
# The acts
# ===========================================================================

_OPCHARS = "=<>!+-*/%&|^~"

_RUN_REPL = (
    "->", ">>>", "<", "<=", ">", ">=", "==", "!=", "=",
    "+", "-", "*", "/", "//", "**", "%", "&", "|", "^", "<<", ">>",
    "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "//=", "**=", "<<=", ">>=",
)


def _op_runs(line):
    """Maximal runs of operator characters, length >= 2.

    Maximal-munch tokenisation cannot see every operator hiding in a run:
    ``-==`` lexes as ``-=`` then ``=``, yet the repair wanted is the arrow
    ``->``.  Treating the whole run as one site sidesteps the ambiguity.
    """
    m = _mask(line)
    out = []
    for mt in re.finditer("[" + re.escape(_OPCHARS) + "]{2,4}", m):
        run = mt.group(0)
        # docstring rules ("------", "======") are not operators
        if len(run) > 2 and len(set(run)) == 1:
            continue
        out.append((mt.start(), mt.end(), run))
    return out


def _act_comparison(line):
    """Comparison strictness / direction / equality at EVERY comparison site,
    plus whole-operator-run rewrites (annotation arrows, glued operators)."""
    repl = ("<", "<=", ">", ">=", "==", "!=", "<<", ">>", "->")
    sites = _op_sites(line, set(_CMP) | set(_SHIFT))
    out = _cross(line, sites, repl)
    out += _cross(line, _op_runs(line), _RUN_REPL)
    return out


def _act_membership(line):
    """is / is not / in / not in / == confusion."""
    m = _mask(line)
    out = []
    for mt in re.finditer(r"\bis\s+not\b", m):
        out.append(_put(line, mt.start(), mt.end(), "is"))
        out.append(_put(line, mt.start(), mt.end(), "!="))
        out.append(_put(line, mt.start(), mt.end(), "=="))
    for mt in re.finditer(r"\bis\b(?!\s+not\b)", m):
        out.append(_put(line, mt.start(), mt.end(), "is not"))
        out.append(_put(line, mt.start(), mt.end(), "=="))
        out.append(_put(line, mt.start(), mt.end(), "in"))
    for mt in re.finditer(r"\bnot\s+in\b", m):
        out.append(_put(line, mt.start(), mt.end(), "in"))
    for mt in re.finditer(r"(?<!\bnot\s)\bin\b", m):
        out.append(_put(line, mt.start(), mt.end(), "not in"))
        out.append(_put(line, mt.start(), mt.end(), "is"))
        out.append(_put(line, mt.start(), mt.end(), "=="))
    for s, e, tok in _op_sites(line, {"==", "!="}):
        out.append(_put(line, s, e, "is" if tok == "==" else "is not"))
        out.append(_put(line, s, e, "in" if tok == "==" else "not in"))
    return out


def _act_andor(line):
    """and <-> or at every site, plus the word/bitwise mix-up."""
    m = _mask(line)
    out = []
    for word, other, sym in (("and", "or", "&"), ("or", "and", "|")):
        for s, e in _word_sites(m, word):
            out.append(_put(line, s, e, other))
            out.append(_put(line, s, e, sym))
    for s, e, tok in _op_sites(line, set(_BITS)):
        if tok == "&":
            out.append(_put(line, s, e, "and"))
            out.append(_put(line, s, e, "or"))
        elif tok == "|":
            out.append(_put(line, s, e, "or"))
            out.append(_put(line, s, e, "and"))
    return out


def _act_int(line):
    """Off-by-one on EVERY integer literal (decimal and hex, strings too)."""
    return _int_shifts(line)


def _act_arith(line):
    """+ - * / // % ** confusion at every site."""
    repl = ("+", "-", "*", "/", "//", "%", "**", "&", "|")
    sites = _op_sites(line, set(_ARITH))
    return _cross(line, sites, repl)


def _act_bitwise(line):
    """& | ^ << >> confusion at every site."""
    repl = ("&", "|", "^", "<<", ">>", "+", "-", "*")
    sites = _op_sites(line, set(_BITS) | set(_SHIFT))
    return _cross(line, sites, repl)


def _act_assign(line):
    """= vs == vs augmented assignment confusion."""
    out = []
    aug_repl = ("=", "+=", "-=", "*=", "/=", "//=", "%=", "&=", "|=", "^=",
                "<<=", ">>=")
    out += _cross(line, _op_sites(line, set(_AUG)), aug_repl + ("==",))
    out += _cross(line, _op_sites(line, {"="}), aug_repl + ("==", "!="),
                  guard=_is_plain_assign)
    out += _cross(line, _op_sites(line, {"==", "!="}), aug_repl,
                  guard=lambda l, s, e, t: l[:s].strip() != "")
    return out


def _act_bool(line):
    """True / False / None literal flips at every site."""
    out = []
    out += _swap_words(line, "True", "False")
    m = _mask(line)
    for s, e in _word_sites(m, "True"):
        out.append(_put(line, s, e, "1"))
        out.append(_put(line, s, e, "None"))
    for s, e in _word_sites(m, "False"):
        out.append(_put(line, s, e, "0"))
        out.append(_put(line, s, e, "None"))
    for s, e in _word_sites(m, "None"):
        out.append(_put(line, s, e, "True"))
        out.append(_put(line, s, e, "False"))
    return out


def _act_not(line):
    """Missing / spurious ``not``."""
    m = _mask(line)
    out = []
    # removal at every site
    for mt in re.finditer(r"\bnot\s+", m):
        out.append(_put(line, mt.start(), mt.end(), ""))
    for mt in re.finditer(r"\bnot\b", m):
        out.append(_put(line, mt.start(), mt.end(), ""))
    # insertion after the usual condition introducers
    for mt in re.finditer(
        r"\b(if|elif|while|return|assert|yield|and|or)\s+(?!not\b)", m
    ):
        out.append(_put(line, mt.end(), mt.end(), "not "))
    # bare "if(" style and lambda bodies
    for mt in re.finditer(r"\blambda\b[^:]*:\s*(?!not\b)", m):
        out.append(_put(line, mt.end(), mt.end(), "not "))
    # any position that starts an operand: after a bracket, comma, assignment
    # or binary operator -- covers e.g. "* (not args.exp)".
    for mt in re.finditer(r"[(\[{,=:&|^+\-*%]\s*(?=[A-Za-z_(\[])", m):
        pos = mt.end()
        if m[pos:pos + 4] == "not ":
            continue
        out.append(_put(line, pos, pos, "not "))
    # start of the expression on a bare statement line
    lead = len(line) - len(line.lstrip())
    if lead < len(line) and not re.match(r"\s*(?:not\b|[)\]}#])", line[lead:]):
        out.append(_put(line, lead, lead, "not "))
    return [c for c in out if c.strip()]


def _bound_alts(p):
    """Off-by-one / sign / arithmetic-tail variants of one slice bound."""
    alts = []
    if not p:
        return ["0", "1", "2", "3", "-1", "-2", "None"]
    if p.startswith("-"):
        alts.append(p[1:].strip())
    else:
        alts.append("-" + p)
    if re.fullmatch(r"-?\d+", p):
        v = int(p)
        alts.append(str(v - 1))
        alts.append(str(v + 1))
    else:
        alts.append(p + " - 1")
        alts.append(p + " + 1")
    # a spurious "+ 1" / "- 1" tail is the classic injected off-by-one
    tail = re.match(r"^(.*\S)\s*[-+]\s*\d+$", p)
    if tail:
        alts.append(tail.group(1))
    return alts


def _index_variants(inner):
    """Candidate rewrites for the text inside a [...] group."""
    outs = []
    parts = _split_top(inner, ":")
    if len(parts) == 1:
        p = parts[0].strip()
        if not p:
            return outs
        outs.extend(_bound_alts(p))
        # an index may be a slice that lost one of its bounds
        for other in ("", "-1", "0", "1", "2", "None"):
            outs.append(p + ":" + other)
            outs.append(other + ":" + p)
    else:
        stripped = [p.strip() for p in parts]
        if len(stripped) >= 2:
            sw = list(stripped)
            sw[0], sw[1] = sw[1], sw[0]
            outs.append(":".join(sw))
            outs.append(":".join([stripped[0]] + [""] + stripped[2:]))
            outs.append(":".join([""] + stripped[1:]))
            outs.append(stripped[0])
            outs.append(stripped[1])
        for idx in range(len(stripped)):
            p = stripped[idx]
            alts = _bound_alts(p)
            if p:
                alts.append("")
            for a in alts:
                cp = list(stripped)
                cp[idx] = a
                outs.append(":".join(cp))
    return outs


def _act_slice(line):
    """Off-by-one / mis-placed slice and index bounds, every bracket group."""
    m = _mask(line)
    out = []
    for oi, ci, och in _groups(m):
        if och != "[":
            continue
        # only subscripts, not list literals: something must precede the '['
        prev = m[:oi].rstrip()
        if not prev or prev[-1] not in (_ATOMCH | set(")]}")):
            continue
        inner = line[oi + 1: ci]
        for v in _index_variants(inner):
            out.append(_put(line, oi + 1, ci, v))
        # tuple subscripts: each comma-separated element is its own index
        elems = _split_top(inner, ",")
        if len(elems) > 1:
            base = oi + 1
            for el in elems:
                ee = base + len(el)
                stripped = el.strip()
                off = len(el) - len(el.lstrip())
                if stripped:
                    for v in _index_variants(stripped):
                        out.append(
                            _put(line, base + off, base + off + len(stripped), v)
                        )
                base = ee + 1
    return out


def _act_operands(line):
    """Swap the two operands of every binary operator on the line."""
    m = _mask(line)
    wanted = set(_CMP) | set(_SHIFT) | set(_ARITH) | set(_BITS)
    out = []
    # scan the MASKED line: reordering text around an operator that lives
    # inside a string literal only ever produces garbage.
    for s, e, tok in _op_sites(m, wanted):
        if s == 0:
            continue
        left = _atom_left(m, s)
        right = _atom_right(m, e)
        if not left or not right:
            continue
        ls, le = left
        rs, re_ = right
        if le > s or rs < e:
            continue
        out.append(line[:ls] + line[rs:re_] + line[le:rs] + line[ls:le] + line[re_:])
    # word operators: in / is / and / or
    for word in ("in", "is", "and", "or"):
        for s, e in _word_sites(m, word):
            left = _atom_left(m, s)
            right = _atom_right(m, e)
            if not left or not right:
                continue
            ls, le = left
            rs, re_ = right
            if le > s or rs < e:
                continue
            out.append(
                line[:ls] + line[rs:re_] + line[le:rs] + line[ls:le] + line[re_:]
            )
    return out


_STMT_KW = r"(?:return|yield|assert|del|raise|await|global|nonlocal)"


def _join_items(items):
    """Re-join comma separated items, not inventing space before an empty
    trailing item (so a trailing comma survives a swap)."""
    s = ""
    for idx, it in enumerate(items):
        if idx:
            s += "," + (" " if it else "")
        s += it
    return s


def _act_commas(line):
    """Swap adjacent comma separated items: call arguments, tuple targets,
    unpacking, ``for`` targets, literal collections."""
    m = _mask(line)
    out = []
    # inside every bracket group
    for oi, ci, och in _groups(m):
        inner = line[oi + 1: ci]
        parts = _split_top(inner, ",")
        if len(parts) < 2:
            continue
        for i in range(len(parts) - 1):
            cp = list(parts)
            a, b = cp[i], cp[i + 1]
            la = a[: len(a) - len(a.lstrip())]
            lb = b[: len(b) - len(b.lstrip())]
            ta = a[len(a.rstrip()):]
            tb = b[len(b.rstrip()):]
            cp[i] = la + b.strip() + ta
            cp[i + 1] = lb + a.strip() + tb
            out.append(_put(line, oi + 1, ci, ",".join(cp)))
        if len(parts) > 2:
            cp = list(parts)
            cp[0], cp[-1] = cp[-1].strip(), " " + cp[0].strip()
            out.append(_put(line, oi + 1, ci, ",".join(cp)))
    # statement level, split first on top-level '='
    body_start = len(line) - len(line.lstrip())
    kw = re.match(r"\s*" + _STMT_KW + r"\s+", m)
    if kw:
        body_start = kw.end()
    body = line[body_start:]
    if body and not body.rstrip().endswith(":") and not re.search(
        r"\b(for|while|with|lambda|def|class|import)\b", _mask(body)
    ):
        segs = _split_top(body, "=")
        pos = body_start
        for seg in segs:
            parts = _split_top(seg, ",")
            if len(parts) >= 2:
                lead = seg[: len(seg) - len(seg.lstrip())]
                trail = seg[len(seg.rstrip()):]
                items = [p.strip() for p in parts]
                for i in range(len(items) - 1):
                    cp = list(items)
                    cp[i], cp[i + 1] = cp[i + 1], cp[i]
                    out.append(
                        _put(line, pos, pos + len(seg),
                             lead + _join_items(cp) + trail)
                    )
            pos += len(seg) + 1
    # for-loop targets
    for mt in re.finditer(r"\bfor\s+", m):
        rest = m[mt.end():]
        im = re.search(r"\s+in\s+", rest)
        if not im:
            continue
        ts, te = mt.end(), mt.end() + im.start()
        target = line[ts:te]
        parts = _split_top(target, ",")
        if len(parts) >= 2:
            for i in range(len(parts) - 1):
                cp = [p.strip() for p in parts]
                cp[i], cp[i + 1] = cp[i + 1], cp[i]
                out.append(_put(line, ts, te, ", ".join(cp)))
    return out


def _act_ternary(line):
    """Swap the branches of ``A if C else B``; swap string literals."""
    m = _mask(line)
    d = _depths(m)
    out = []
    elses = [(e.start(), e.end()) for e in re.finditer(r"\belse\b", m)]
    for tm in re.finditer(r"\bif\b", m):
        i0, i1 = tm.start(), tm.end()
        lvl = d[i0]
        pick = None
        for es, ee in elses:
            if es > i1 and d[es] == lvl:
                pick = (es, ee)
                break
        if pick is None:
            continue
        es, ee = pick
        # left boundary of branch A
        a_start = 0
        j = i0 - 1
        while j >= 0:
            ch = m[j]
            if d[j] < lvl and ch in "([{":
                a_start = j + 1
                break
            if d[j] == lvl and ch in ",:":
                a_start = j + 1
                break
            if (d[j] == lvl and ch == "=" and
                    (j == 0 or m[j - 1] not in "=!<>+-*/%&|^") and
                    (j + 1 >= len(m) or m[j + 1] != "=")):
                a_start = j + 1
                break
            j -= 1
        kw = re.match(r"\s*(?:" + _STMT_KW + r"|lambda[^:]*:)\s*", line[a_start:i0])
        if kw:
            a_start += kw.end()
        # right boundary of branch B
        b_end = len(line)
        for k in range(ee, len(m)):
            ch = m[k]
            if d[k] < lvl and ch in ")]}":
                b_end = k
                break
            if d[k] == lvl and ch == ",":
                b_end = k
                break
        segA = line[a_start:i0]
        segC = line[i1:es]
        segB = line[ee:b_end]
        if not segA.strip() or not segB.strip() or not segC.strip():
            continue
        lead = segA[: len(segA) - len(segA.lstrip())]
        trail = segB[len(segB.rstrip()):]
        out.append(
            line[:a_start] + lead + segB.strip() + " if " + segC.strip()
            + " else " + segA.strip() + trail + line[b_end:]
        )
        # also: condition negated form is a different act; here also offer the
        # "wrong branch duplicated" style repair of swapping only via else
        out.append(
            line[:a_start] + lead + segA.strip() + " if " + segC.strip()
            + " else " + segB.strip() + trail + line[b_end:]
        )
    # swap adjacent string literals
    spans = _string_spans(line)
    for i in range(len(spans) - 1):
        (s1, e1), (s2, e2) = spans[i], spans[i + 1]
        out.append(line[:s1] + line[s2:e2] + line[e1:s2] + line[s1:e1] + line[e2:])
    if len(spans) > 2:
        (s1, e1), (s2, e2) = spans[0], spans[-1]
        out.append(line[:s1] + line[s2:e2] + line[e1:s2] + line[s1:e1] + line[e2:])
    return out


_STOP_IDENTS = frozenset("""
False None True and as assert async await break class continue def del elif else
except finally for from global if import in is lambda nonlocal not or pass raise
return try while with yield self cls print len range enumerate zip map filter
super object property staticmethod classmethod format join split isinstance
Exception ValueError TypeError ImportError StopIteration Optional Union List
Dict Tuple Callable Iterable Iterator Any Pattern Match cast overload partial
typing re os sys
""".split())


def _act_ident_swap(line):
    """Swap every pair of identifiers appearing on the line (operand mix-ups
    such as first/second, lows/highs, sep/pre_sep)."""
    m = _mask(line)
    names = []
    for mt in re.finditer(r"[A-Za-z_]\w*", m):
        nm = mt.group(0)
        if nm in _STOP_IDENTS or nm in names:
            continue
        names.append(nm)
        if len(names) >= 9:
            break
    out = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            pat = re.compile(r"\b(" + re.escape(a) + r"|" + re.escape(b) + r")\b")
            pieces = []
            last = 0
            for mt in pat.finditer(m):
                pieces.append(line[last:mt.start()])
                pieces.append(b if mt.group(0) == a else a)
                last = mt.end()
            pieces.append(line[last:])
            out.append("".join(pieces))
    return out


# Domain vocabulary of this code base plus the usual generic confusions.
_WORD_PAIRS = [
    ("lower", "upper"), ("casefold", "lower"), ("casefold", "upper"),
    ("swapcase", "casefold"), ("swapcase", "lower"), ("title", "capitalize"),
    ("lstrip", "rstrip"), ("lstrip", "strip"), ("rstrip", "strip"),
    ("startswith", "endswith"), ("min", "max"), ("first", "second"),
    ("low", "high"), ("lows", "highs"), ("start", "stop"), ("left", "right"),
    ("any", "all"), ("append", "extend"), ("append", "insert"),
    ("int", "float"), ("str", "bytes"), ("isinstance", "issubclass"),
    ("break", "continue"), ("sorted", "reversed"), ("reverse", "sort"),
    ("break", "pass"), ("continue", "pass"), ("return", "yield"),
    ("elif", "if"), ("while", "if"),
    ("keys", "values"), ("items", "keys"), ("major", "minor"),
    ("minor", "patch"), ("major", "patch"), ("next", "iter"),
    ("encode", "decode"), ("chr", "ord"), ("index", "count"),
    ("pop", "append"), ("update", "get"), ("get", "pop"),
    ("numeric", "digits"), ("digits", "decimals"), ("numeric", "decimals"),
    ("numeric_chars", "digit_chars"), ("digit_chars", "decimal_chars"),
    ("numeric_chars", "decimal_chars"),
    ("digits_no_decimals", "numeric_no_decimals"),
    ("try_float", "try_int"), ("fast_float", "fast_int"),
    ("float_num", "exp"), ("nan", "inf"),
    ("int_sign", "int_nosign"),
    ("float_sign_exp", "float_nosign_exp"),
    ("float_sign_noexp", "float_nosign_noexp"),
    ("float_sign_exp", "float_sign_noexp"),
    ("float_nosign_exp", "float_nosign_noexp"),
    ("get_thousands_sep", "get_decimal_point"),
    ("thousands_sep", "decimal_point"),
    ("sep", "pre_sep"), ("null_string", "null_string_max"),
    ("null_string_locale", "null_string_locale_max"),
    ("null_string", "null_string_locale"),
    ("null_string_max", "null_string_locale_max"),
    ("input_transform", "original_func"),
    ("normalize_input", "compose_input"),
    ("string_func", "bytes_func"), ("bytes_func", "num_func"),
    ("string_func", "num_func"),
    ("dumb", "lowfirst"), ("use_locale", "dumb"), ("group_letters", "use_locale"),
    ("split_val", "val"), ("path_parts", "suffixes"), ("base", "suffixes"),
    ("treat_base", "iter"), ("presort", "reverse"),
    ("FLOAT", "INT"), ("SIGNED", "UNSIGNED"), ("LOCALEALPHA", "LOCALENUM"),
    ("IGNORECASE", "LOWERCASEFIRST"), ("GROUPLETTERS", "UNGROUPLETTERS"),
    ("NANLAST", "NUMAFTER"), ("PATH", "LOCALE"), ("NOEXP", "SIGNED"),
    ("REAL", "FLOAT"), ("DEFAULT", "INT"), ("PRESORT", "PATH"),
    ("NS_DUMB", "LOCALEALPHA"), ("CAPITALFIRST", "GROUPLETTERS"),
    ("COMPATIBILITYNORMALIZE", "LOCALEALPHA"),
    ("NFD", "NFKD"), ("NFC", "NFKC"), ("NFD", "NFC"), ("NFKD", "NFKC"),
    ("U", "A"), ("ASCII", "UNICODE"), ("VERBOSE", "UNICODE"),
    ("dumb_sort", "get_strxfrm"),
]

_TEXT_PAIRS = [
    ("(?<=", "(?<!"), ("(?=", "(?!"),
    ('"+inf"', '"-inf"'), ("'+inf'", "'-inf'"),
    ('"+"', '"-"'), ("'+'", "'-'"),
    ("+inf", "-inf"), ("float(\"inf\")", "float(\"-inf\")"),
    (".lower()", ".upper()"), (".casefold()", ".lower()"),
    (" or ", " | "), (" and ", " & "),
    ("[0]", "[-1]"), ("[0]", "[1]"), ("[-1]", "[1]"),
    ("\\d", "\\w"), ("\\w", "\\s"), ("\\d", "\\s"),
    ("^", "$"),
]


# Substitutions worth trying in one direction only (the reverse would fire on
# nearly every line and buy nothing).
_TEXT_ONEWAY = [
    ("(?:", "("), ("(?P<", "("), ("+?", "+"), ("*?", "*"),
]


def _act_vocab(line):
    """Known token substitutions drawn from this code base's vocabulary."""
    out = []
    for a, b in _WORD_PAIRS:
        if re.search(r"\b(" + re.escape(a) + r"|" + re.escape(b) + r")\b", line):
            out += _swap_words(line, a, b)
    for a, b in _TEXT_PAIRS:
        if a in line or b in line:
            out += _swap_text(line, a, b)
    for a, b in _TEXT_ONEWAY:
        start = 0
        while True:
            i = line.find(a, start)
            if i < 0:
                break
            out.append(_put(line, i, i + len(a), b))
            start = i + 1
    return out


_QUANT = ("+", "*", "?")


def _act_regex_text(line):
    """Edits confined to the interior of string literals: regex quantifiers,
    anchors, escapes, and the small character tweaks this code base uses."""
    out = []
    spans = _string_spans(line)
    if not spans:
        return out
    for s, e in spans:
        body = line[s:e]
        for i, ch in enumerate(body):
            if ch in _QUANT:
                for q in _QUANT:
                    if q != ch:
                        out.append(_put(line, s + i, s + i + 1, q))
                out.append(_put(line, s + i, s + i + 1, ""))
            elif ch in "^$":
                out.append(_put(line, s + i, s + i + 1, "$" if ch == "^" else "^"))
            elif ch in "<>":
                out.append(_put(line, s + i, s + i + 1, ">" if ch == "<" else "<"))
            elif ch in "!=":
                out.append(_put(line, s + i, s + i + 1, "=" if ch == "!" else "!"))
            elif ch in "+-" and len(body) > 2:
                out.append(_put(line, s + i, s + i + 1, "-" if ch == "+" else "+"))
        # a dropped quantifier: re-insert after a group, a class or an escape
        for i in range(1, len(body)):
            prev = body[i - 1]
            here = body[i] if i < len(body) else ""
            if here in _QUANT:
                continue
            if prev in ")]}" or (i >= 2 and body[i - 2] == "\\"):
                for q in _QUANT:
                    out.append(_put(line, s + i, s + i, q))
        # greedy / lazy
        j = body.find("?)")
        while j >= 0:
            out.append(_put(line, s + j, s + j + 1, ""))
            j = body.find("?)", j + 1)
    return out


# ===========================================================================
# Dispatch
# ===========================================================================

_ACTS = (
    _act_comparison,    # kind 0
    _act_membership,    # kind 1
    _act_andor,         # kind 2
    _act_int,           # kind 3
    _act_arith,         # kind 4
    _act_bitwise,       # kind 5
    _act_assign,        # kind 6
    _act_bool,          # kind 7
    _act_not,           # kind 8
    _act_slice,         # kind 9
    _act_operands,      # kind 10
    _act_commas,        # kind 11
    _act_ternary,       # kind 12
    _act_ident_swap,    # kind 13
    _act_vocab,         # kind 14
    _act_regex_text,    # kind 15
)


def observe(line):
    """Every kind is admissible: the acts themselves decide applicability by
    returning [] when they find no site.  Kinds are 0..15, contiguous."""
    k = []
    if line is None:
        return k
    for i in range(_N_KINDS):
        k.append(i)
    return k


def acts(line, act):
    out = []
    if line is None:
        return out
    try:
        kind = (int(act) - _ACT_BASE) % _ACT_RING
    except (TypeError, ValueError):
        return out
    if kind < 0 or kind >= len(_ACTS):
        return out
    try:
        out = list(_ACTS[kind](line))
    except Exception:
        out = []
    out = _uniq(out)
    if len(out) > 600:
        out = out[:600]
    return [c for c in out if c != line]


def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
