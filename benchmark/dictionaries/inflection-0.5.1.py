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
# low level helpers -- string / comment masking so that operator surgery only
# ever touches real code, while literal surgery can still reach inside quotes.
# ===========================================================================

_NUL = "\x00"

_STR_RE = re.compile(
    r'''[rRbBuUfF]{0,3}(?:"""(?:\\.|(?!""")[\s\S])*?"""'''
    r"""|'''(?:\\.|(?!''')[\s\S])*?'''"""
    r'''|"(?:\\.|[^"\\])*"'''
    r"""|'(?:\\.|[^'\\])*')"""
)


def _string_spans(line):
    """Spans (start, end) of every complete string literal on the line."""
    return [mo.span() for mo in _STR_RE.finditer(line)]


def _mask(line):
    """Same-length copy of `line` with string literals and trailing comments
    blanked to NUL, so operator scans never fire inside text."""
    chars = list(line)
    covered = [False] * len(line)
    for a, b in _string_spans(line):
        for i in range(a, b):
            chars[i] = _NUL
            covered[i] = True
    for i, ch in enumerate(line):
        if ch == "#" and not covered[i]:
            for j in range(i, len(line)):
                chars[j] = _NUL
            break
    return "".join(chars)


def _uniq(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _splice(line, start, end, text):
    return line[:start] + text + line[end:]


def _prev_ns(masked, i):
    """previous non-space character index, or -1"""
    j = i - 1
    while j >= 0 and masked[j] in " \t":
        j -= 1
    return j


def _matching(masked, i, openc="(", closec=")"):
    """index of the bracket matching the one at i, or -1"""
    depth = 0
    for j in range(i, len(masked)):
        c = masked[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _top_level_parts(masked, a, b):
    """split masked[a:b] on top level commas -> list of (start, end) spans"""
    parts = []
    depth = 0
    start = a
    for j in range(a, b):
        c = masked[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append((start, j))
            start = j + 1
    parts.append((start, b))
    return parts


def _shift_expr(expr, delta):
    """'3' -> '4';  'i' -> 'i + 1';  'i + 1' -> 'i';  '-1' -> '0'  ..."""
    e = expr.strip()
    if not e:
        return None
    if re.fullmatch(r"-?\d+", e):
        return str(int(e) + delta)
    mo = re.fullmatch(r"(.+?)\s*([-+])\s*(\d+)", e)
    if mo:
        base = mo.group(1).strip()
        val = int(mo.group(3)) * (1 if mo.group(2) == "+" else -1)
        val += delta
        if val == 0:
            return base
        return "%s %s %d" % (base, "+" if val > 0 else "-", abs(val))
    return "%s %s %d" % (e, "+" if delta > 0 else "-", abs(delta))


# ===========================================================================
# act 5 (kind 0) -- comparison operators: strictness, direction, equality,
#                   membership and identity.  EVERY site on the line.
# ===========================================================================

_CMP_OPS = ["==", "!=", "<=", ">=", "<", ">"]
_CMP_RE = re.compile(r"==|!=|<=|>=|<|>")


def _act_comparison(line):
    m = _mask(line)
    out = []
    for mo in _CMP_RE.finditer(m):
        s, e = mo.span()
        op = mo.group()
        prev = m[s - 1] if s > 0 else ""
        nxt = m[e] if e < len(m) else ""
        if op in ("<", ">"):
            # skip  ->  ,  <<  ,  >>  ,  =<  and friends
            if prev in "-<>=!*/+%" or nxt in "<>=":
                continue
        for alt in _CMP_OPS:
            if alt != op:
                out.append(_splice(line, s, e, alt))

    # membership / identity
    for mo in re.finditer(r"\bnot\s+in\b", m):
        out.append(_splice(line, mo.start(), mo.end(), "in"))
    for mo in re.finditer(r"\bin\b", m):
        s = mo.start()
        if re.search(r"\bnot\s+$", m[:s]):
            continue
        if re.search(r"\bfor\b", m[:s]):
            continue  # `for x in y` -> `for x not in y` is not a thing
        out.append(_splice(line, s, mo.end(), "not in"))
    for mo in re.finditer(r"\bis\s+not\b", m):
        out.append(_splice(line, mo.start(), mo.end(), "is"))
    for mo in re.finditer(r"\bis\b(?!\s+not\b)", m):
        out.append(_splice(line, mo.start(), mo.end(), "is not"))
    return out


# ===========================================================================
# act 6 (kind 1) -- integer literals.  EVERY digit run on the line, including
#                   the ones living inside string literals (regex group
#                   backreferences r'\1', repetition counts {2,}, ...).
# ===========================================================================


def _int_sites(line):
    spans = _string_spans(line)

    def in_string(i):
        return any(a < i < b for a, b in spans)

    sites = []
    for mo in re.finditer(r"\d+", line):
        s, e = mo.span()
        prev = line[s - 1] if s > 0 else ""
        nxt = line[e] if e < len(line) else ""
        backref = prev == "\\"
        if not backref:
            if prev.isalnum() or prev == "_":
                continue  # part of an identifier (utf8, sha256, group1)
            # r'\1ies' and "1st" keep their digit; utf8_x style does not
            if (nxt.isalnum() or nxt == "_") and not in_string(s):
                continue
            if prev == "." and s >= 2 and line[s - 2].isdigit():
                continue  # fraction of a float / version string
            if nxt == "." and e + 1 < len(line) and line[e + 1].isdigit():
                continue
        val = int(mo.group())
        start = s
        if prev == "-":
            before = line[s - 2] if s >= 2 else ""
            if before == "" or not (before.isalnum() or before in "_)]}\"'"):
                start = s - 1
                val = -val
        sites.append((start, e, val))
    return sites


def _act_int_literal(line):
    out = []
    sites = _int_sites(line)
    for s, e, n in sites:
        vals = [n + 1, n - 1]
        if abs(n) >= 10:
            vals += [n // 10, n * 10]
        if n in (0, 1, 2, -1):
            vals += [0, 1, 2, -1, -2]
        for v in vals:
            if v == n:
                continue
            out.append(_splice(line, s, e, str(v)))
    # two literals that traded places -- r'\2_\1' for r'\1_\2', (13, 11, 12)
    for i in range(len(sites)):
        for j in range(i + 1, len(sites)):
            (s1, e1, n1), (s2, e2, n2) = sites[i], sites[j]
            if n1 == n2:
                continue
            new = (line[:s1] + str(n2) + line[e1:s2] + str(n1) + line[e2:])
            out.append(new)
    return out


# ===========================================================================
# act 7 (kind 2) -- boolean literal flips (default arguments, flags, keyword
#                   arguments).  EVERY site on the line.
# ===========================================================================


def _act_boolean(line):
    m = _mask(line)
    out = []
    for mo in re.finditer(r"\bTrue\b", m):
        out.append(_splice(line, mo.start(), mo.end(), "False"))
    for mo in re.finditer(r"\bFalse\b", m):
        out.append(_splice(line, mo.start(), mo.end(), "True"))
    for mo in re.finditer(r"\bNone\b", m):
        out.append(_splice(line, mo.start(), mo.end(), "True"))
        out.append(_splice(line, mo.start(), mo.end(), "False"))
    return out


# ===========================================================================
# act 8 (kind 3) -- boolean connectives: and/or confusion, and a missing or a
#                   spurious `not`.
# ===========================================================================


def _act_logic(line):
    m = _mask(line)
    out = []
    for mo in re.finditer(r"\band\b", m):
        out.append(_splice(line, mo.start(), mo.end(), "or"))
    for mo in re.finditer(r"\bor\b", m):
        out.append(_splice(line, mo.start(), mo.end(), "and"))
    for mo in re.finditer(r"\ball\b(?=\s*\()", m):
        out.append(_splice(line, mo.start(), mo.end(), "any"))
    for mo in re.finditer(r"\bany\b(?=\s*\()", m):
        out.append(_splice(line, mo.start(), mo.end(), "all"))

    # drop a `not`
    for mo in re.finditer(r"\bnot\s+", m):
        if re.match(r"\bnot\s+in\b", m[mo.start():]):
            continue
        if re.search(r"\bis\s+$", m[:mo.start()]):
            continue
        out.append(_splice(line, mo.start(), mo.end(), ""))
    # introduce a `not`
    for mo in re.finditer(r"\b(?:if|elif|while|return|assert|and|or)\s+", m):
        s, e = mo.span()
        if m[e:e + 4] == "not ":
            continue
        rest = line[e:]
        if not rest.strip():
            continue
        out.append(_splice(line, e, e, "not "))

    # truthiness test written as an explicit None test, and back again
    for mo in re.finditer(r"\s+is\s+not\s+None\b", m):
        out.append(_splice(line, mo.start(), mo.end(), ""))
    for mo in re.finditer(r"\s+is\s+None\b", m):
        stripped = _splice(line, mo.start(), mo.end(), "")
        out.append(stripped)
        cut = None
        for c in re.finditer(r"\b(?:if|elif|while|return|assert|and|or)\s+",
                             m[:mo.start()]):
            cut = c
        if cut:
            out.append(stripped[:cut.end()] + "not " + stripped[cut.end():])
    mo = re.match(r"^(\s*(?:el)?if\s+|\s*while\s+)(.+?)(:\s*)$", m)
    if mo:
        cond = line[mo.start(2):mo.end(2)]
        if re.fullmatch(r"(?:not\s+)?[A-Za-z_][\w\.]*", cond.strip()):
            head, tail = line[:mo.start(2)], line[mo.end(2):]
            bare = re.sub(r"^not\s+", "", cond.strip())
            out.append(head + bare + " is None" + tail)
            out.append(head + bare + " is not None" + tail)
    return out


# ===========================================================================
# act 9 (kind 4) -- arithmetic / additive / multiplicative operator confusion.
#                   EVERY binary site on the line.
# ===========================================================================

_ARITH_ALT = {
    "+": ["-", "*", "%", "//", "/"],
    "-": ["+", "*", "//", "%", "/"],
    "*": ["+", "-", "/", "//", "%", "**"],
    "/": ["*", "//", "%", "+", "-"],
    "//": ["/", "*", "%", "+", "-"],
    "%": ["//", "*", "/", "+", "-"],
    "**": ["*", "//", "+"],
}
_ARITH_RE = re.compile(r"\*\*|//|[-+*/%]")


def _act_arithmetic(line):
    m = _mask(line)
    out = []
    for mo in _ARITH_RE.finditer(m):
        s, e = mo.span()
        op = mo.group()
        if op == "-" and e < len(m) and m[e] == ">":
            continue  # return annotation arrow
        if e < len(m) and m[e] == "=" and (e + 1 >= len(m) or m[e + 1] != "="):
            continue  # augmented assignment, handled below
        if s > 0 and m[s - 1] == "=":
            continue
        j = _prev_ns(m, s)
        if j < 0:
            continue
        p = m[j]
        if not (p.isalnum() or p == "_" or p in ")]}" + _NUL + "\"'"):
            continue  # unary / unpacking / decorator, not a binary operator
        for alt in _ARITH_ALT.get(op, []):
            out.append(_splice(line, s, e, alt))
    for mo in re.finditer(r"(\*\*|//|[-+*/%])=", m):
        s, e = mo.span()
        op = mo.group(1)
        for alt in _ARITH_ALT.get(op, []):
            out.append(_splice(line, s, e, alt + "="))
    return out


# ===========================================================================
# act 10 (kind 5) -- swapped operands: either side of a binary operator, or
#                    two adjacent arguments of a call.
# ===========================================================================

_OPERAND = (
    r"(?:[A-Za-z_]\w*(?:\.\w+|\([^()]*\)|\[[^\[\]]*\])*"
    r"|\d+"
    r"|'(?:\\.|[^'\\])*'"
    r'|"(?:\\.|[^"\\])*")'
)
_BINOP = r"(?:==|!=|<=|>=|<|>|\*\*|//|[-+*/%])"
_SWAP_RE = re.compile(
    r"(" + _OPERAND + r")(\s*)(" + _BINOP + r")(\s*)(" + _OPERAND + r")"
)


def _act_swap(line):
    m = _mask(line)
    out = []

    # --- operands of a binary operator -------------------------------------
    for mo in _SWAP_RE.finditer(line):
        s = mo.start()
        if s < len(m) and m[s] == _NUL and not line[s] in "\"'":
            continue
        op = mo.group(3)
        if op in ("<", ">") and line[max(0, s - 1):s] == "-":
            continue
        new = mo.group(5) + mo.group(2) + op + mo.group(4) + mo.group(1)
        out.append(_splice(line, mo.start(), mo.end(), new))

    # --- adjacent call arguments -------------------------------------------
    for i, ch in enumerate(m):
        if ch not in "([":
            continue
        if ch == "(" and not (i > 0 and (m[i - 1].isalnum() or m[i - 1] == "_")):
            continue
        close = _matching(m, i)
        if close < 0:
            continue
        parts = _top_level_parts(m, i + 1, close)
        if len(parts) < 2:
            continue
        texts = [line[a:b] for a, b in parts]
        for k in range(len(texts) - 1):
            new = list(texts)
            new[k], new[k + 1] = _swap_keep_space(new[k], new[k + 1])
            out.append(line[:i + 1] + ",".join(new) + line[close:])
        if len(texts) > 2:
            new = list(texts)
            new[0], new[-1] = _swap_keep_space(new[0], new[-1])
            out.append(line[:i + 1] + ",".join(new) + line[close:])

    # --- nested calls applied in the wrong order ---------------------------
    for mo in re.finditer(
            r"\b([A-Za-z_][\w\.]*)(\(\s*)([A-Za-z_][\w\.]*)(\([^()]*\))(\s*\))",
            m):
        outer, inner = mo.group(1), mo.group(3)
        if outer == inner:
            continue
        new = (inner + mo.group(2) + outer + line[mo.start(4):mo.end(4)] +
               mo.group(5))
        out.append(_splice(line, mo.start(), mo.end(), new))
    return out


def _swap_keep_space(a, b):
    """swap the cores of two argument texts but keep their surrounding space"""
    ma = re.match(r"^(\s*)(.*?)(\s*)$", a, re.S)
    mb = re.match(r"^(\s*)(.*?)(\s*)$", b, re.S)
    return (ma.group(1) + mb.group(2) + ma.group(3),
            mb.group(1) + ma.group(2) + mb.group(3))


# ===========================================================================
# act 11 (kind 6) -- slice and index bounds: off-by-one on either end, and the
#                    colon on the wrong side.
# ===========================================================================


def _act_slice(line):
    m = _mask(line)
    out = []
    for i, ch in enumerate(m):
        if ch != "[":
            continue
        close = _matching(m, i)
        if close < 0:
            continue
        inner_masked = m[i + 1:close]
        if "," in inner_masked or "[" in inner_masked:
            continue
        inner = line[i + 1:close]
        variants = []
        if inner_masked.count(":") == 1:
            cut = inner_masked.index(":")
            lo, hi = inner[:cut], inner[cut + 1:]
            for d in (1, -1):
                if lo.strip():
                    nl = _shift_expr(lo, d)
                    if nl is not None:
                        variants.append(nl + ":" + hi)
                if hi.strip():
                    nh = _shift_expr(hi, d)
                    if nh is not None:
                        variants.append(lo + ":" + nh)
            if lo.strip() and not hi.strip():
                variants.append(":" + lo.strip())
            if hi.strip() and not lo.strip():
                variants.append(hi.strip() + ":")
            if lo.strip() and hi.strip():
                variants.append(hi.strip() + ":" + lo.strip())
        elif ":" not in inner_masked and inner.strip():
            for d in (1, -1):
                nv = _shift_expr(inner, d)
                if nv is not None:
                    variants.append(nv)
            core = inner.strip()
            variants.append(core + ":")
            variants.append(":" + core)
        for v in variants:
            out.append(line[:i + 1] + v + line[close:])
    return out


# ===========================================================================
# act 12 (kind 7) -- the paired vocabulary of this library: upper/lower,
#                    singular/plural, PLURALS/SINGULARS, search/match, and the
#                    small constant families ('st'/'nd'/'rd'/'th', 'NFKD'...).
# ===========================================================================

_WORD_PAIRS = [
    ("upper", "lower"),
    ("uppercase", "lowercase"),
    ("singular", "plural"),
    ("singulars", "plurals"),
    ("SINGULARS", "PLURALS"),
    ("singularize", "pluralize"),
    ("camelize", "underscore"),
    ("dasherize", "underscore"),
    ("capitalize", "title"),
    ("titleize", "humanize"),
    ("search", "match"),
    ("match", "fullmatch"),
    ("sub", "subn"),
    ("startswith", "endswith"),
    ("lstrip", "rstrip"),
    ("strip", "lstrip"),
    ("split", "rsplit"),
    ("find", "rfind"),
    ("index", "rindex"),
    ("partition", "rpartition"),
    ("ljust", "rjust"),
    ("encode", "decode"),
    ("min", "max"),
    ("first", "last"),
    ("start", "end"),
    ("left", "right"),
    ("append", "extend"),
    ("keys", "values"),
    ("word", "string"),
    ("group", "groups"),
    ("insert", "append"),
    ("add", "discard"),
    ("normalize", "normalise"),
]

_WORD_FAMILIES = [
    ["lower", "upper", "capitalize", "title", "casefold", "swapcase"],
    ["strip", "lstrip", "rstrip"],
    ["search", "match", "fullmatch"],
    ["sub", "subn"],
    ["startswith", "endswith"],
    ["split", "rsplit", "splitlines"],
    ["find", "rfind", "index", "rindex"],
    ["insert", "append"],
    ["min", "max"],
    ["abs", "int"],
    ["all", "any"],
]

_CONST_FAMILIES = [
    ["st", "nd", "rd", "th"],
    ["NFKD", "NFKC", "NFD", "NFC"],
    ["ignore", "strict", "replace", "backslashreplace"],
    ["ascii", "utf-8", "latin-1"],
    ["_", "-", " ", ".", "/", ""],
]


def _act_vocabulary(line):
    m = _mask(line)
    out = []
    subs = [(a, b) for a, b in _WORD_PAIRS] + [(b, a) for a, b in _WORD_PAIRS]
    for fam in _WORD_FAMILIES:
        for src in fam:
            for dst in fam:
                if src != dst:
                    subs.append((src, dst))
    for src, dst in subs:
        for mo in re.finditer(r"\b%s\b" % re.escape(src), m):
            out.append(_splice(line, mo.start(), mo.end(), dst))
    # constant families inside string literals whose whole content matches
    for s, e in _string_spans(line):
        lit = line[s:e]
        mo = re.match(r"^([rRbBuUfF]{0,3})(['\"])([\s\S]*)\2$", lit)
        if not mo:
            continue
        pre, q, body = mo.group(1), mo.group(2), mo.group(3)
        for fam in _CONST_FAMILIES:
            if body in fam:
                for alt in fam:
                    if alt != body:
                        out.append(_splice(line, s, e, pre + q + alt + q))
    return out


# ===========================================================================
# act 13 (kind 8) -- regex token surgery inside string literals: quantifiers,
#                    anchors, class negation, capturing vs non-capturing,
#                    alternation order, character-class shorthands.
# ===========================================================================

# (pattern matching the token, literal text that replaces it)
_RX_TOKEN_SWAPS = [
    (r"\\b", "\\B"), (r"\\B", "\\b"),
    (r"\\d", "\\w"), (r"\\w", "\\d"),
    (r"\\s", "\\S"), (r"\\S", "\\s"),
    (r"\\Z", "$"), (r"\\Z", "\\z"), (r"\\z", "\\Z"),
    (r"\\A", "^"), (r"\^", "\\A"),
    (r"\$", "\\Z"),
]

_RX_META = set("\\()[]^$|*+?{}.")


def _looks_regexy(pre, body):
    if "r" in pre.lower():
        return True
    return any(ch in _RX_META for ch in body)


def _act_regex_token(line):
    out = []
    for s, e in _string_spans(line):
        lit = line[s:e]
        mo = re.match(r"^([rRbBuUfF]{0,3})(['\"]{1,3})([\s\S]*)\2$", lit)
        if not mo:
            continue
        pre, q, body = mo.group(1), mo.group(2), mo.group(3)
        if not _looks_regexy(pre, body):
            continue
        bodies = []
        if not body:
            if "r" in pre.lower():
                bodies += ["$", "^"]
            for nb in bodies:
                out.append(_splice(line, s, e, pre + q + nb + q))
            continue

        # quantifier confusion, every site
        for i, ch in enumerate(body):
            if ch == "+":
                bodies.append(body[:i] + "*" + body[i + 1:])
                bodies.append(body[:i] + "?" + body[i + 1:])
            elif ch == "*":
                bodies.append(body[:i] + "+" + body[i + 1:])
                bodies.append(body[:i] + "?" + body[i + 1:])
            elif ch == "?" and (i == 0 or body[i - 1] != "("):
                bodies.append(body[:i] + body[i + 1:])
                bodies.append(body[:i] + "*" + body[i + 1:])
                bodies.append(body[:i] + "+" + body[i + 1:])

        # a quantifier that went missing:  (passer)sby$  vs  (passer)s?by$
        for i in range(1, len(body) + 1):
            p = body[i - 1]
            if p == "(":
                bodies.append(body[:i] + "?" + body[i:])   # (i) -> (?i)
                continue
            if p in "|\\?*+{^$":
                continue          # nothing quantifiable just before here
            if i < len(body) and body[i] in "?*+{":
                continue
            escaped = i >= 2 and body[i - 2] == "\\"
            bodies.append(body[:i] + "?" + body[i:])
            if p in "])" or escaped:
                bodies.append(body[:i] + "+" + body[i:])
                bodies.append(body[:i] + "*" + body[i:])

        # token shorthands
        for src, dst in _RX_TOKEN_SWAPS:
            for mo2 in re.finditer(src, body):
                bodies.append(body[:mo2.start()] + dst + body[mo2.end():])

        # class negation
        for mo2 in re.finditer(r"\[\^", body):
            bodies.append(body[:mo2.start()] + "[" + body[mo2.end():])
        for mo2 in re.finditer(r"\[(?!\^)", body):
            bodies.append(body[:mo2.start()] + "[^" + body[mo2.end():])

        # capturing vs non capturing
        for mo2 in re.finditer(r"\(\?:", body):
            bodies.append(body[:mo2.start()] + "(" + body[mo2.end():])
        for mo2 in re.finditer(r"\((?!\?)", body):
            bodies.append(body[:mo2.start()] + "(?:" + body[mo2.end():])

        # anchors
        for mo2 in re.finditer(r"\^", body):
            bodies.append(body[:mo2.start()] + body[mo2.end():])
        if body.endswith("$"):
            bodies.append(body[:-1])
        else:
            bodies.append(body + "$")
        mo2 = re.match(r"^(\(\?[a-zA-Z]+\))?", body)
        head = mo2.group(0) if mo2 else ""
        if not body[len(head):].startswith("^"):
            bodies.append(head + "^" + body[len(head):])
        # an anchor that went missing from a branch:  (?:|_) vs (?:^|_)
        for i in range(len(body)):
            if body[i] in "(|" and body[i + 1:i + 2] != "^":
                bodies.append(body[:i + 1] + "^" + body[i + 1:])
            if body[i] in ")|" and body[i - 1:i] not in ("$", ""):
                bodies.append(body[:i] + "$" + body[i:])
        for mo2 in re.finditer(r"\(\?[a-zA-Z]+\)|\(\?[a-zA-Z]*:", body):
            if body[mo2.end():mo2.end() + 1] != "^":
                bodies.append(body[:mo2.end()] + "^" + body[mo2.end():])

        # inline flags
        for mo2 in re.finditer(r"\(\?[a-zA-Z]+\)", body):
            bodies.append(body[:mo2.start()] + body[mo2.end():])
        if not body.startswith("(?i)"):
            bodies.append("(?i)" + body)

        # alternation written with the wrong connective
        for i, ch in enumerate(body):
            if ch in "|&.":
                for alt in "|&.":
                    if alt != ch:
                        bodies.append(body[:i] + alt + body[i + 1:])

        # alternation order inside a group
        for mo2 in re.finditer(r"\(([^()|]*)\|([^()|]*)\)", body):
            bodies.append(body[:mo2.start()] + "(" + mo2.group(2) + "|" +
                          mo2.group(1) + ")" + body[mo2.end():])

        for nb in bodies:
            if nb != body and q not in nb:
                out.append(_splice(line, s, e, pre + q + nb + q))
    return out


# ===========================================================================
# the dictionary itself
# ===========================================================================

_ACTS = [
    _act_comparison,    # kind 0 -> act 5
    _act_int_literal,   # kind 1 -> act 6
    _act_boolean,       # kind 2 -> act 7
    _act_logic,         # kind 3 -> act 8
    _act_arithmetic,    # kind 4 -> act 9
    _act_swap,          # kind 5 -> act 10
    _act_slice,         # kind 6 -> act 11
    _act_vocabulary,    # kind 7 -> act 12
    _act_regex_token,   # kind 8 -> act 13
]

_FIRST_ACT = WORKED_EXAMPLE[1] - WORKED_EXAMPLE[0]   # == 5


def _run(fn, line):
    try:
        return [c for c in fn(line) if isinstance(c, str) and c != line]
    except Exception:
        return []


def observe(line):
    """Every fault kind this line could plausibly exhibit.

    A kind is reported when its act actually has something to say about the
    line, which keeps the router honest and costs one cheap pass per act.
    """
    if not isinstance(line, str) or not line.strip():
        return []
    k = []
    for kind, fn in enumerate(_ACTS):
        if _run(fn, line):
            k.append(kind)
    return k


def acts(line, act):
    out = []
    if not isinstance(line, str):
        return []
    idx = None
    try:
        idx = int(act) - _FIRST_ACT
    except (TypeError, ValueError):
        idx = None
    if idx is not None and 0 <= idx < len(_ACTS):
        out = _run(_ACTS[idx], line)
    else:
        # the router handed us something outside the dictionary: offer the
        # union rather than nothing at all -- a wrong candidate is cheap.
        for fn in _ACTS:
            out.extend(_run(fn, line))
    return _uniq([c for c in out if c != line])


def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
