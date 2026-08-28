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
"""Edit shapes a one-line substitution cannot reach: a spurious line that must be
DELETED, and a missing guard that must be INSERTED.

Both work with the router untouched. An act returns DELETE_LINE to remove the
line, or a string containing newlines to expand one line into several. The
kind->act mapping is still never written down: the kernel names acts 9 and 10
for fault kinds 4 and 5 from the same single worked example it always had.

The second half of this file is the finding that matters. The worked example
sets the OFFSET and nothing else, so it cannot decide which of two fault kinds
on the same line is tried first. That is fixed by ordering observe(), not by
choosing a better example -- and with the wrong order, all 16 worked examples
produce a repair that greens the suite and is wrong.

    python3 tests/test_multiline.py        # ~20 s, no dependencies
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples"))
sys.path.insert(0, os.path.join(HERE, ".."))
import kdebug
from kdebug import DELETE_LINE
from fluid_router import route as router

SHIPPED_ACT = kdebug.apply_act
WORKED_EXAMPLE = kdebug.WORKED_EXAMPLE


# ---------------------------------------------------------------- body only
# Six fault kinds, six acts numbered in kind order. The mapping kind -> act is
# NEVER written here; the router derives it from the worked example.

def observe(line, specific_first=True):
    k = []
    if re.search(r"[<>]=?", line):                   k.append(0)   # comparison
    if re.search(r"\d", line):                       k.append(1)   # integer literal
    if re.match(r"^\s*return\s+.*\s[-+*]\s", line):  k.append(2)   # return with binop
    if re.search(r"\s[-+]\s", line):                 k.append(3)   # additive
    if re.match(r"^\s*\w+\s*\+=", line):                          # lone accumulate
        k.insert(0, 4) if specific_first else k.append(4)
    if re.match(r"^\s*return\s+\w+\s*$", line):      k.append(5)   # bare return
    return k


def act_of(line, act, base):
    """base is whatever offset the worked example implies; i is the kind."""
    i = act - base
    ind = re.match(r"^(\s*)", line).group(1)
    if i == 0: return SHIPPED_ACT(line, 5)
    if i == 1: return SHIPPED_ACT(line, 6)
    if i == 2: return SHIPPED_ACT(line, 7)
    if i == 3: return SHIPPED_ACT(line, 8)
    if i == 4: return DELETE_LINE                       # NEW: remove the line
    if i == 5:                                          # NEW: insert a guard above
        m = re.match(r"^\s*return\s+(\w+)", line)
        if not m: return line
        return "%sif %s is None:\n%s    return None\n%s" % (ind, m.group(1), ind, line)
    return line


def repair(mod, test, F1, A1, specific_first=True):
    d = tempfile.mkdtemp(); w = os.path.join(d, "_w"); os.makedirs(w)
    open(os.path.join(w, "test.py"), "w").write(test)
    lines = mod.splitlines(); base = A1 - F1
    try:
        for i, line in enumerate(lines):
            for kind in observe(line, specific_first):
                cand = act_of(line, router(F1, A1, kind), base)
                if cand is not DELETE_LINE and cand == line: continue
                new = lines[:]
                if cand is DELETE_LINE: del new[i]
                else:                   new[i] = cand
                open(os.path.join(w, "mod.py"), "w").write("\n".join(new) + "\n")
                shutil.rmtree(os.path.join(w, "__pycache__"), ignore_errors=True)
                try:
                    rc = subprocess.run(["python3", "-B", "test.py"], cwd=w,
                                        capture_output=True, timeout=5).returncode
                except subprocess.TimeoutExpired:
                    rc = 1
                if rc == 0: return "\n".join(new) + "\n"
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------- cases
CASES = [
    ("comparison",
     'def c(xs, t):\n    n = 0\n    for x in xs:\n        if x >= t:\n            n += 1\n    return n\n',
     'from mod import *\nassert c([1,5,5,9], 5) == 1\nprint("ok")\n',
     lambda s: "if x > t:" in s),
    ("off-by-one",
     'def h(xs):\n    return xs[1]\n',
     'from mod import *\nassert h([7,8,9]) == 7\nprint("ok")\n',
     lambda s: "return xs[0]" in s),
    ("spurious line (DELETE)",
     'def n(xs):\n    k = 0\n    for x in xs:\n        k += 1\n        k += 1\n    return k\n',
     'from mod import *\nassert n([1,2,3]) == 3\nprint("ok")\n',
     # correct ONLY if the line is gone -- "k += 0" also greens the suite
     lambda s: "+= 0" not in s and len([l for l in s.splitlines() if l.strip()]) == 5),
    ("missing guard (INSERT)",
     'def s(v):\n    return v\n',
     'from mod import *\nassert s(None) is None and s(4) == 4\nprint("ok")\n',
     lambda s: "if v is None:" in s),
]


def sweep(specific_first):
    rows = []
    for A1 in range(16):
        res = []
        for _, mod, test, ok in CASES:
            got = repair(mod, test, 0, A1, specific_first)
            res.append("OK" if (got and ok(got)) else ("WRONG" if got else "refuse"))
        rows.append((A1, res, all(r == "OK" for r in res)))
    return rows


def main():
    print("=" * 74)
    print("EDIT SHAPES BEYOND ONE-LINE SUBSTITUTION")
    print("=" * 74)
    print("  worked example supplied: fault kind %d is repaired by act %d." % WORKED_EXAMPLE)
    print("  Acts 9 (delete) and 10 (insert) are named by the kernel, never declared.\n")

    for name, mod, test, ok in CASES:
        got = repair(mod, test, *WORKED_EXAMPLE)
        print("  %-24s %s" % (name, "REPAIRED" if got and ok(got) else
                              ("WRONG" if got else "refused")))
        if got and name.startswith(("spurious", "missing")):
            for l in got.rstrip().splitlines(): print("        %s" % l)
    print()

    print("=" * 74)
    print("THE ORDER IN observe() IS LOAD-BEARING; THE WORKED EXAMPLE CANNOT FIX IT")
    print("=" * 74)
    print("  'k += 1' exhibits kind 1 (has a digit) and kind 4 (a lone accumulate).")
    print("  act = kind + offset is a TRANSLATION: it shifts every kind equally, so")
    print("  whichever kind observe() lists first wins for EVERY worked example.\n")
    for label, sf in (("generic kind first (wrong)", False), ("specific kind first", True)):
        rows = sweep(sf)
        good = sum(1 for _, _, a in rows if a)
        print("  %-28s all four correct for %2d of 16 worked examples" % (label, good))
        bad = [a1 for a1, r, _ in rows if r[2] == "WRONG"]
        print("      offsets giving a green-but-wrong delete: %s" % (bad if bad else "none"))
    print()
    rows = sweep(True)
    good = sum(1 for _, _, a in rows if a)
    print("  RESULT: %s" % ("PASS" if good >= 10 else "FAIL"))
    return 0 if good >= 10 else 1


if __name__ == "__main__":
    sys.exit(main())
