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
"""Acts derived from example pairs -- nothing about repair is hand-written.

You hand it a bug you already fixed, as a (broken, fixed) pair. `derive()` reads
the diff and returns a general transform. The router names the act. From then on
that class of bug is repaired for free, in code the example never touched.

The last section is the point: a bug that is REFUSED with N examples becomes a
one-try byte-exact fix with N+1, because the new example mints a new act and the
router names it immediately. A hand-written kind->act table cannot do that -- the
kind did not exist when the table was written.

    python3 tests/test_from_examples.py       # ~2 s, no dependencies
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "examples"))
from fluid_router import route as router
from kdebug import WORKED_EXAMPLE


def _toks(s):
    return re.findall(r"[A-Za-z_]\w*|\d+|\S", s)


def derive(broken, fixed):
    """A general transform, inferred from ONE (broken, fixed) pair."""
    tb, tf = _toks(broken), _toks(fixed)

    if len(tb) == len(tf):                      # one token differs
        d = [i for i, (a, b) in enumerate(zip(tb, tf)) if a != b]
        if len(d) == 1:
            a, b = tb[d[0]], tf[d[0]]
            if a.isdigit() and b.isdigit():     # generalise the DELTA, not the value
                delta = int(b) - int(a)

                def act(line, delta=delta):
                    out = []
                    for m in re.finditer(r"\b\d+\b", line):
                        v = int(m.group()) + delta
                        if v >= 0:
                            out.append(line[:m.start()] + str(v) + line[m.end():])
                    return out
                return "numeric shift %+d" % delta, act

            def act(line, a=a, b=b):            # generalise the token PAIR
                return [line[:m.start()] + b + line[m.end():]
                        for m in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(a), line)]
            return "token %s -> %s" % (a, b), act

    if sorted(tb) == sorted(tf):                # same tokens, reordered
        for op in ("@", "*", "+", "-", "/"):
            pat = r"^(\s*return\s+)(\S+)\s%s\s(\S+)\s*$" % re.escape(op)
            m1, m2 = re.match(pat, broken), re.match(pat, fixed)
            if m1 and m2 and m1.group(2) == m2.group(3) and m1.group(3) == m2.group(2):
                def act(line, op=op, pat=pat):
                    m = re.match(pat, line)
                    return [] if not m else ["%s%s %s %s" % (m.group(1), m.group(3), op, m.group(2))]
                return "swap operands around '%s'" % op, act

    return "no act derivable", lambda line: []


def build(examples):
    """acts[i] is derived from examples[i]. Fault kind i -> act named by the router."""
    return [derive(b, f) for b, f in examples]


def candidates(line, acts):
    for kind in range(len(acts)):
        act = router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)
        i = act - WORKED_EXAMPLE[1]
        if 0 <= i < len(acts):
            for c in acts[i][1](line):
                if c != line:
                    yield c, acts[i][0]


def repair(mod, test, acts):
    d = tempfile.mkdtemp(); w = os.path.join(d, "_w"); os.makedirs(w)
    open(os.path.join(w, "test.py"), "w").write(test)
    lines = mod.splitlines(); tries = 0
    try:
        open(os.path.join(w, "mod.py"), "w").write(mod)
        if subprocess.run([sys.executable, "-B", "test.py"], cwd=w,
                          capture_output=True, timeout=10).returncode == 0:
            return None, 0, None, None          # nothing to repair
        for i, line in enumerate(lines):
            for cand, why in candidates(line, acts):
                tries += 1
                new = lines[:]; new[i] = cand
                open(os.path.join(w, "mod.py"), "w").write("\n".join(new) + "\n")
                shutil.rmtree(os.path.join(w, "__pycache__"), ignore_errors=True)
                try:
                    rc = subprocess.run([sys.executable, "-B", "test.py"], cwd=w,
                                        capture_output=True, timeout=10).returncode
                except subprocess.TimeoutExpired:
                    rc = 1
                if rc == 0:
                    return "\n".join(new) + "\n", tries, cand, why
        return None, tries, None, None
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- bugs you already fixed, handed over as pairs ------------------------
EXAMPLES = [
    ("    return xs[1]",        "    return xs[0]"),        # an index one out
    ("    return a * b",        "    return b * a"),        # operands reversed
    ("    n = count(3)",        "    n = count(2)"),        # a literal one high
]
SIGN_EXAMPLE = ("    loss = a + b", "    loss = a - b")     # added later

# ---- bugs it has never seen, in code the examples never touched ---------
NOVEL = [
    ("index one out, different shape",
     "def first(rows):\n    hdr = rows[1]\n    return hdr\n",
     "    hdr = rows[1]",
     "    hdr = rows[0]",
     "from mod import first\nassert first(['a','b','c'])=='a'\nprint('ok')\n"),
    ("operands reversed in a helper",
     "def scale(v, k):\n    return k * v\n",
     "    return k * v",
     "    return v * k",
     "from mod import scale\nclass M:\n    def __mul__(s,o): return 'right'\n    def __rmul__(s,o): return 'wrong'\nassert scale(M(),2)=='right'\nprint('ok')\n"),
    ("literal one high, nested call",
     "def window(xs):\n    return xs[: len(xs) - 1]\n",
     "    return xs[: len(xs) - 1]",
     "    return xs[: len(xs) - 0]",
     "from mod import window\nassert window([1,2,3])==[1,2,3]\nprint('ok')\n"),
    ("gradient sign -- NO example covers this yet",
     "def step(w, g, lr):\n    return w + lr * g\n",
     "    return w + lr * g",
     "    return w - lr * g",
     "from mod import step\nassert step(1.0,2.0,0.5)==0.0\nprint('ok')\n"),
]


def main():
    print("=" * 74)
    print("ACTS DERIVED FROM EXAMPLES -- no repair logic is hand-written")
    print("=" * 74)
    acts = build(EXAMPLES)
    print("  you hand over %d bugs you already fixed; each yields one act:\n" % len(EXAMPLES))
    for i, ((b, f), (why, _)) in enumerate(zip(EXAMPLES, acts)):
        print("    kind %d -> act %d   %-26s  %s"
              % (i, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], i), b.strip(), why))
    print("\n  the router is told only three integers -- never any code.\n")

    solved = exact = 0
    for name, mod, broken, want, test in NOVEL[:3]:
        got, tries, cand, why = repair(mod, test, acts)
        ok = bool(got) and cand.rstrip() == want.rstrip()
        solved += bool(got); exact += ok
        print("  %-34s %-7s (%d tries)" % (name, "EXACT" if ok else ("green" if got else "refused"), tries))
        if got:
            print("       - %s\n       + %s   via '%s'" % (broken.strip(), cand.strip(), why))
    print("\n  %d/3 novel bugs repaired, %d byte-exact, 0 acts hand-written\n" % (solved, exact))

    print("=" * 74)
    print("ONE MORE EXAMPLE MINTS A NEW ACT -- a table cannot do this")
    print("=" * 74)
    name, mod, broken, want, test = NOVEL[3]
    for label, ex in (("with %d examples" % len(EXAMPLES), EXAMPLES),
                      ("with %d examples" % (len(EXAMPLES) + 1), EXAMPLES + [SIGN_EXAMPLE])):
        a = build(ex)
        got, tries, cand, why = repair(mod, test, a)
        print("  %-22s %-42s %s"
              % (label, broken.strip(),
                 ("SOLVED -> %s  (%d try, '%s')" % (cand.strip(), tries, why)) if got
                 else "REFUSED (%d candidates generated)" % tries))
    ok = bool(got) and cand.rstrip() == want.rstrip()
    print("\n  byte-exact: %s" % ok)
    print("  The new example created fault kind %d. The router named its act with no"
          % len(EXAMPLES))
    print("  edit anywhere; a hand-written table would need a new row first.")
    print("\n  RESULT: %s" % ("PASS" if exact == 3 and ok else "FAIL"))
    return 0 if (exact == 3 and ok) else 1


if __name__ == "__main__":
    sys.exit(main())
