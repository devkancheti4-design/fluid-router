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
# Kind vocabulary (contiguous from 0; act number for kind k is k + 5)
#
#   0  relational strictness        <  <-> <=      >  <-> >=
#   1  relational direction/other   <  <-> >, and relational <-> equality
#   2  equality / identity / membership   == <-> !=, is <-> is not, in <-> not in
#   3  integer literal off-by-one    N -> N-1, N+1   (decimal AND hex, every site)
#   4  integer literal substitution  N -> 0/1/2/3/-1/-2, sign flip
#   5  additive operator confusion   + <-> -, += <-> -=, aug -> plain
#   6  multiplicative confusion      * / // % ** cross-substitution
#   7  boolean literal / negation    True <-> False, insert/remove `not`
#   8  logical connective            and <-> or
#   9  swapped operands              a OP b -> b OP a, f(a, b) -> f(b, a), [a:b] -> [b:a]
#  10  slice / index bound off-by-one   add, drop or retune a trailing +/- N
#  11  paired-token swap             start/end, lbound/ubound, min/max, break/continue, ...
#
# Every act walks EVERY applicable site on the line and emits a candidate for
# each; nothing takes "just the first match".
# ===========================================================================

_N_KINDS = 12


# --------------------------------------------------------------------------
# line dissection: keep transforms out of string literals and comments
# --------------------------------------------------------------------------

def _split_segments(line):
    """Split *line* into [(text, is_code), ...]; strings and comments are not code."""
    out = []
    buf = []
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c == '#':
            if buf:
                out.append((''.join(buf), True))
                buf = []
            out.append((line[i:], False))
            return out
        if c == '"' or c == "'":
            if buf:
                out.append((''.join(buf), True))
                buf = []
            q = line[i:i + 3] if line[i:i + 3] in ('"""', "'''") else c
            j = i + len(q)
            while j < n:
                if line[j] == '\\':
                    j += 2
                    continue
                if line.startswith(q, j):
                    j += len(q)
                    break
                j += 1
            if j > n:
                j = n
            out.append((line[i:j], False))
            i = j
            continue
        buf.append(c)
        i += 1
    if buf:
        out.append((''.join(buf), True))
    return out


def _code_spans(line):
    """[(absolute_offset, text), ...] for the code-bearing parts of *line*."""
    spans = []
    off = 0
    for text, is_code in _split_segments(line):
        if is_code and text:
            spans.append((off, text))
        off += len(text)
    return spans


def _sites(line, pattern):
    """Every (abs_start, abs_end, match) for *pattern* inside code spans."""
    res = []
    for off, text in _code_spans(line):
        for m in pattern.finditer(text):
            res.append((off + m.start(), off + m.end(), m))
    return res


def _sites_wide(line, pattern):
    """Like _sites but string literals count too (constants live in regexes here)."""
    res = []
    off = 0
    for text, is_code in _split_segments(line):
        if is_code or not text.startswith('#'):
            for m in pattern.finditer(text):
                res.append((off + m.start(), off + m.end(), m))
        off += len(text)
    return res


def _depth_at(line, pos):
    """Bracket nesting depth of *pos*, counting only code characters."""
    depth = 0
    for off, text in _code_spans(line):
        for i, ch in enumerate(text):
            if off + i >= pos:
                return depth
            if ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
    return depth


_PY_KEYWORDS = frozenset(
    'False None True and as assert async await break class continue def del elif '
    'else except finally for from global if import in is lambda nonlocal not or '
    'pass raise return try while with yield self int str bool float len'.split())


def _names(line):
    """Identifiers appearing in the code part of *line*, in order, de-duplicated."""
    out = []
    for _off, text in _code_spans(line):
        for m in re.finditer(r'[A-Za-z_]\w*', text):
            nm = m.group(0)
            if nm not in _PY_KEYWORDS and nm not in out:
                out.append(nm)
    return out


def _put(line, a, b, rep):
    return line[:a] + rep + line[b:]


def _tokenwise(line, pattern, table):
    """Emit one candidate per site per alternative given by table[matched_text]."""
    out = []
    for a, b, m in _sites(line, pattern):
        for rep in table.get(m.group(0), ()):
            out.append(_put(line, a, b, rep))
    return out


# --------------------------------------------------------------------------
# shared patterns
# --------------------------------------------------------------------------

_NUM_RE = re.compile(r'(?<![\w.])(0[xX][0-9a-fA-F]+|[0-9]+)(?![\w.])')

_CMP_RE = re.compile(r'(?<![-+*/%<>=!&|^~:])(<=|>=|==|!=|<|>)(?![=<>])')

_ADD_AUG_RE = re.compile(r'(?<![-+*/%<>=!&|^~])([-+])=(?!=)')
_ADD_BIN_RE = re.compile(r'(?<![-+*/%<>=!&|^~])([-+])(?![-+=>])')

_MUL_AUG_RE = re.compile(r'(?<![*/%])(//|\*\*|[*/%])=(?!=)')
_MUL_BIN_RE = re.compile(r'(?<![*/%])(\*\*|//|[*/%])(?![*/=])')

_BOOL_RE = re.compile(r'\b(True|False)\b')
_ANDOR_RE = re.compile(r'\b(and|or)\b')
_NOT_RE = re.compile(r'\bnot\s+')
_NOT_HOST_RE = re.compile(r'\b(if|elif|while|and|or|return|assert)\s+')
_IS_RE = re.compile(r'\bis\s+not\b|\bis\b')
_IN_RE = re.compile(r'\bnot\s+in\b|\bin\b')

_ATOM = (r'(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\([^()]*\))?(?:\[[^\[\]]*\])*'
         r'|0[xX][0-9a-fA-F]+|\d+)')
_ATOM_SIMPLE = r'(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|0[xX][0-9a-fA-F]+|\d+)'
_SWAPOP = r'(?:<=|>=|==|!=|//|[-+*/%<>])'


def _swap_pattern(atom):
    # right operand stays un-consumed (lookahead) so `a + b + c` yields both pairs,
    # and so a nested pair is not swallowed by a wider one.
    return re.compile(r'(?<![\w.\])])(' + atom + r')(\s*)(' + _SWAPOP +
                      r')(\s*)(?=(' + atom + r')(?![\w.(\[]))')


_SWAP_RE = _swap_pattern(_ATOM)
_SWAP_SIMPLE_RE = _swap_pattern(_ATOM_SIMPLE)

_ASSIGN_RE = re.compile(r'(?<![-+*/%<>=!&|^~:])=(?!=)')

_ARG = r'(?:[^(),]|\([^()]*\))+'
_CALL2_RE = re.compile(r'\b([A-Za-z_]\w*)\((' + _ARG + r'),(\s*)(' + _ARG + r')\)')

_BRACKET_RE = re.compile(r'\[([^\[\]]*)\]')

_KW_BEFORE = ('return', 'and', 'or', 'not', 'in', 'is', 'if', 'elif', 'while',
              'else', 'yield', 'assert', 'lambda', 'while')


# --------------------------------------------------------------------------
# numeric helpers
# --------------------------------------------------------------------------

def _fmt_hex(orig, val):
    """Reformat *val* as a 0x token; both letter cases, orig's case first."""
    if val < 0:
        return []
    body = orig[2:]
    upper_first = any(ch in 'ABCDEF' for ch in body)
    out = []
    for spec in (('X', 'x') if upper_first else ('x', 'X')):
        bare = format(val, spec)
        padded = ('0' * (len(body) - len(bare)) + bare) if len(bare) < len(body) else bare
        for s in (bare, padded):
            tok = orig[:2] + s
            if tok not in out:
                out.append(tok)
    return out


def _minus_pos(line, start):
    """Index of the '-' immediately preceding position *start*, else -1."""
    j = start - 1
    while j >= 0 and line[j] == ' ':
        j -= 1
    if j >= 0 and line[j] == '-':
        return j
    return -1


def _is_unary_minus(line, start):
    """True when the '-' just before *start* is a sign, not a subtraction."""
    j = _minus_pos(line, start)
    if j < 0:
        return False
    k = j - 1
    while k >= 0 and line[k] == ' ':
        k -= 1
    if k < 0:
        return True
    if line[k] in '=([{,:+-*/%<>!~&|^;':
        return True
    m = re.search(r'([A-Za-z_]\w*)$', line[:k + 1])
    return bool(m and m.group(1) in _KW_BEFORE)


# ===========================================================================
# the acts
# ===========================================================================

_STRICT = {'<': ('<=',), '<=': ('<',), '>': ('>=',), '>=': ('>',)}

_DIRECTION = {
    '<': ('>', '>=', '==', '!='),
    '<=': ('>', '>=', '==', '!='),
    '>': ('<', '<=', '==', '!='),
    '>=': ('<', '<=', '==', '!='),
    '==': ('<', '<=', '>', '>='),
    '!=': ('<', '<=', '>', '>='),
}


def _act_cmp_strict(line):
    """kind 0 -- boundary strictness at every relational site."""
    return _tokenwise(line, _CMP_RE, _STRICT)


def _act_cmp_direction(line):
    """kind 1 -- reversed / re-classed comparison at every relational site."""
    return _tokenwise(line, _CMP_RE, _DIRECTION)


def _act_equality(line):
    """kind 2 -- == <-> !=, is <-> is not, in <-> not in, at every site."""
    out = _tokenwise(line, _CMP_RE, {'==': ('!=',), '!=': ('==',)})
    for a, b, m in _sites(line, _IS_RE):
        tok = ' '.join(m.group(0).split())
        out.append(_put(line, a, b, 'is' if tok.startswith('is not') else 'is not'))
    for a, b, m in _sites(line, _IN_RE):
        tok = ' '.join(m.group(0).split())
        if tok == 'in':
            if re.search(r'\bfor\b', line[:a]) or re.search(r'\blambda\b', line[:a]):
                continue
            out.append(_put(line, a, b, 'not in'))
        else:
            out.append(_put(line, a, b, 'in'))
    return out


def _act_int_offbyone(line):
    """kind 3 -- every integer literal (decimal or hex) nudged by one."""
    out = []
    for a, b, m in _sites_wide(line, _NUM_RE):
        tok = m.group(0)
        if tok[:2] in ('0x', '0X'):
            val = int(tok, 16)
            for nv in (val - 1, val + 1):
                for s in _fmt_hex(tok, nv):
                    out.append(_put(line, a, b, s))
        else:
            val = int(tok)
            for nv in (val - 1, val + 1):
                out.append(_put(line, a, b, str(nv)))
    return out


# stock constants this library actually leans on: sentinels -1/-2, widths 0/1/2,
# tabsize 8, lru_cache sizes, buffer/scan limits.
_SPECIALS = ('0', '1', '2', '3', '-1', '-2', '4', '8', '10', '16', '32', '-3')


def _act_int_special(line):
    """kind 4 -- every integer literal replaced by a stock constant / sign flip."""
    out = []
    sites = _sites_wide(line, _NUM_RE)
    others = []
    for _a, _b, m in sites:
        tok = m.group(0)
        if tok not in others:
            others.append(tok)
    for a, b, m in sites:
        tok = m.group(0)
        if tok[:2] in ('0x', '0X'):
            # letter-case restyling of the same value (exact-text repairs)
            for s in _fmt_hex(tok, int(tok, 16)):
                out.append(_put(line, a, b, s))
            continue
        val = int(tok)
        pool = list(_SPECIALS) + [t for t in others if t != tok and t[:2] not in ('0x', '0X')]
        if _is_unary_minus(line, a):
            mp = _minus_pos(line, a)
            for s in pool:
                if int(s) != -val:
                    out.append(_put(line, mp, b, s))
            out.append(_put(line, mp, b, tok))          # drop the sign
        else:
            for s in pool:
                if int(s) != val:
                    out.append(_put(line, a, b, s))
            out.append(_put(line, a, b, '-' + tok))     # add a sign
    return out


def _act_additive(line):
    """kind 5 -- + <-> -, += <-> -=, and plain <-> augmented assignment."""
    out = _tokenwise(line, _ADD_AUG_RE, {'+=': ('-=', '='), '-=': ('+=', '=')})
    out += _tokenwise(line, _ADD_BIN_RE, {'+': ('-',), '-': ('+',)})
    # `col = grapheme_w` where `col += grapheme_w` shipped, and the reverse
    if not re.match(r'\s*(def|class|import|from|global|nonlocal)\b', line) \
            and 'lambda' not in line:
        for a, b, _m in _sites(line, _ASSIGN_RE):
            if _depth_at(line, a) != 0:
                continue
            for rep in ('+=', '-=', '*=', '//='):
                out.append(_put(line, a, b, rep))
    return out


_MUL = {
    '*': ('/', '//', '%', '**'),
    '/': ('*', '//', '%'),
    '//': ('/', '*', '%'),
    '%': ('//', '/', '*'),
    '**': ('*',),
}
_MUL_AUG = dict(('%s=' % k, tuple('%s=' % v for v in vs) + ('=',))
                for k, vs in _MUL.items())


def _act_multiplicative(line):
    """kind 6 -- * / // % ** cross-substitution at every site."""
    out = _tokenwise(line, _MUL_AUG_RE, _MUL_AUG)
    out += _tokenwise(line, _MUL_BIN_RE, _MUL)
    return out


def _act_boolean(line):
    """kind 7 -- True <-> False, and insertion / removal of `not`."""
    out = _tokenwise(line, _BOOL_RE, {'True': ('False',), 'False': ('True',)})
    for a, b, _m in _sites(line, _NOT_RE):
        out.append(_put(line, a, b, ''))
    for a, b, _m in _sites(line, _NOT_HOST_RE):
        out.append(_put(line, b, b, 'not '))
    return out


def _act_andor(line):
    """kind 8 -- and <-> or at every site."""
    return _tokenwise(line, _ANDOR_RE, {'and': ('or',), 'or': ('and',)})


def _act_operand_swap(line):
    """kind 9 -- swap the two operands of a binary op, a 2-arg call, or a slice."""
    out = []
    for pat in (_SWAP_RE, _SWAP_SIMPLE_RE):
        for a, b, m in _sites(line, pat):
            rhs = m.group(5)
            end = b + len(rhs)          # rhs was matched by lookahead, not consumed
            out.append(_put(line, a, end,
                            rhs + m.group(2) + m.group(3) + m.group(4) + m.group(1)))
    for a, b, m in _sites(line, _CALL2_RE):
        left, right = m.group(2).strip(), m.group(4).strip()
        if left and right:
            out.append(_put(line, a, b,
                            '%s(%s,%s%s)' % (m.group(1), right, m.group(3), left)))
    for a, b, m in _sites(line, _BRACKET_RE):
        inner = m.group(1)
        if inner.count(':') != 1 or ',' in inner:
            continue
        lhs, rhs = inner.split(':')
        if lhs.strip() and rhs.strip():
            out.append(_put(line, a, b, '[' + rhs + ':' + lhs + ']'))
    return out


def _bump_variants(expr):
    """Textual off-by-one retunings of an index / slice endpoint expression."""
    e = expr.strip()
    if not e:
        return []
    out = []
    m = re.match(r'^(.*\S)\s*([-+])\s*(\d+)$', e)
    if m and m.group(1):
        base, op, num = m.group(1), m.group(2), int(m.group(3))
        val = num if op == '+' else -num
        for nv in (val - 1, val + 1):
            if nv == 0:
                out.append(base)
            elif nv > 0:
                out.append('%s + %d' % (base, nv))
            else:
                out.append('%s - %d' % (base, -nv))
        out.append(base)
        out.append('%s %s %d' % (base, '-' if op == '+' else '+', num))
    else:
        out.append('%s + 1' % e)
        out.append('%s - 1' % e)
    return [o for o in out if o.strip() != e]


_TRAILING_TERM_RE = re.compile(r'(\s*[-+]\s*\d+)(?=[\])},:]|\s*$)')


def _act_bound_offbyone(line):
    """kind 10 -- add / drop / retune a +N or -N on any index or slice bound."""
    out = []
    # a stray trailing `+ N` / `- N` closing an expression anywhere on the line
    for a, b, _m in _sites(line, _TRAILING_TERM_RE):
        out.append(_put(line, a, b, ''))
    for a, b, m in _sites(line, _BRACKET_RE):
        inner = m.group(1)
        if not inner.strip() or ',' in inner:
            continue
        colons = inner.count(':')
        if colons == 0:
            for v in _bump_variants(inner):
                out.append(_put(line, a, b, '[' + v + ']'))
        elif colons == 1:
            lhs, rhs = inner.split(':')
            for v in _bump_variants(lhs):
                out.append(_put(line, a, b, '[' + v + ':' + rhs + ']'))
            for v in _bump_variants(rhs):
                out.append(_put(line, a, b, '[' + lhs + ':' + v + ']'))
            if lhs.strip():
                out.append(_put(line, a, b, '[:' + rhs + ']'))
            if rhs.strip():
                out.append(_put(line, a, b, '[' + lhs + ':]'))
            # a dropped bound: try re-seating it with a name already on the line
            if not lhs.strip() or not rhs.strip():
                fill = ['0', '1', '-1'] + _names(line)
                for nm in fill[:14]:
                    if nm == inner.strip():
                        continue
                    if not lhs.strip():
                        out.append(_put(line, a, b, '[' + nm + ':' + rhs + ']'))
                    if not rhs.strip():
                        out.append(_put(line, a, b, '[' + lhs + ':' + nm + ']'))
    return out


# paired tokens that read as each other's mirror image; swapped as whole
# name components, so cluster_start <-> cluster_end, lbound <-> ubound, ...
_WORD_PAIRS = (
    ('start', 'end'), ('lbound', 'ubound'), ('first', 'last'),
    ('left', 'right'), ('before', 'after'), ('prev', 'curr'),
    ('prev', 'next'), ('narrower', 'wider'), ('narrow', 'wide'),
    ('forward', 'backward'), ('begin', 'end'), ('open', 'close'),
    ('head', 'tail'), ('lower', 'upper'), ('min', 'max'),
    ('row', 'col'), ('src', 'dst'), ('break', 'continue'),
)

# paired callables; only swapped when actually invoked
_CALL_PAIRS = (
    ('max', 'min'), ('ljust', 'rjust'), ('lstrip', 'rstrip'),
    ('startswith', 'endswith'), ('find', 'rfind'), ('rindex', 'index'),
    ('split', 'rsplit'), ('match', 'search'), ('islower', 'isupper'),
    ('lower', 'upper'), ('append', 'extend'), ('keys', 'values'),
)

_WORD_TABLE = {}
for _x, _y in _WORD_PAIRS:
    _WORD_TABLE.setdefault(_x, []).append(_y)
    _WORD_TABLE.setdefault(_y, []).append(_x)
_WORD_RE = re.compile(r'(?<![A-Za-z0-9])(' +
                      '|'.join(sorted(_WORD_TABLE, key=len, reverse=True)) +
                      r')(?![A-Za-z0-9])')

_CALL_TABLE = {}
for _x, _y in _CALL_PAIRS:
    _CALL_TABLE.setdefault(_x, []).append(_y)
    _CALL_TABLE.setdefault(_y, []).append(_x)
_CALL_RE = re.compile(r'(?<![A-Za-z0-9_])(' +
                      '|'.join(sorted(_CALL_TABLE, key=len, reverse=True)) +
                      r')(?=\s*\()')


def _act_paired_token(line):
    """kind 11 -- swap a token for its mirror twin, at every site."""
    out = []
    for a, b, m in _sites(line, _WORD_RE):
        for rep in _WORD_TABLE.get(m.group(1), ()):
            out.append(_put(line, a, b, rep))
    for a, b, m in _sites(line, _CALL_RE):
        for rep in _CALL_TABLE.get(m.group(1), ()):
            out.append(_put(line, a, b, rep))
    return out


_ACTS = {
    0: _act_cmp_strict,
    1: _act_cmp_direction,
    2: _act_equality,
    3: _act_int_offbyone,
    4: _act_int_special,
    5: _act_additive,
    6: _act_multiplicative,
    7: _act_boolean,
    8: _act_andor,
    9: _act_operand_swap,
    10: _act_bound_offbyone,
    11: _act_paired_token,
}

_MEMO = {}


def _run(kind, line):
    """Deduplicated, self-excluding candidate list for one kind."""
    key = (kind, line)
    hit = _MEMO.get(key)
    if hit is not None:
        return hit
    fn = _ACTS.get(kind)
    res = []
    if fn is not None:
        seen = set()
        for cand in fn(line):
            if cand != line and cand not in seen:
                seen.add(cand)
                res.append(cand)
    if len(_MEMO) > 8192:
        _MEMO.clear()
    _MEMO[key] = res
    return res


def observe(line):
    k = []
    if not line or not line.strip():
        return k
    if line.lstrip().startswith('#'):
        return k
    highest = -1
    for kind in range(_N_KINDS):
        if _run(kind, line):
            highest = kind
    if highest < 0:
        return k
    # contiguous from 0 -- inapplicable acts simply yield nothing
    k = list(range(highest + 1))
    return k


def acts(line, act):
    out = _run((act - 5) % 16, line)
    return [c for c in out if c != line]


def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
