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
"""Mechanical, seeded bug injection. I do not choose the bugs.

Standard mutation operators (mutmut/cosmic-ray set). Three of the seven fall
inside fluid-router's four-act vocabulary and four fall outside it; the split
is a property of the operator set, not a choice made per-bug.
"""
import os, random, re, subprocess, sys, glob

OPS = [   # (name, pattern, replacement, in fluid-router's vocabulary?)
 ("cmp_strict", r"(?<![<>=!])<(?!=)", "<=", True),
 ("cmp_strict", r"(?<![<>=!])>(?!=)", ">=", True),
 ("const_off",  r"\b(\d+)\b",         None, True),      # n -> n+1
 ("arith_add",  r" \+ ",              " - ", True),
 ("cmp_eq",     r" == ",              " != ", False),
 ("arith_mul",  r" \* ",              " / ", False),
 ("bool_flip",  r"\bTrue\b",          "False", False),
 ("logic_flip", r" and ",             " or ", False),
]

def srcfiles(root, pkg):
    out = []
    for f in glob.glob(os.path.join(root, "**", "*.py"), recursive=True):
        rel = os.path.relpath(f, root)
        if rel.startswith(("test", "tests", "setup", "docs", "bench", "conftest")): continue
        if os.sep + "test" in os.sep + rel: continue
        out.append(f)
    return sorted(out)

def sites(root, pkg):
    s = []
    for f in srcfiles(root, pkg):
        for i, line in enumerate(open(f, encoding="utf-8").read().splitlines()):
            st = line.strip()
            if not st or st.startswith("#") or st.startswith(('"', "'")): continue
            for name, pat, rep, invoc in OPS:
                for m in re.finditer(pat, line):
                    s.append((f, i, line, name, pat, rep, invoc, m.start()))
    return s

def mutate(line, pat, rep, at):
    m = re.compile(pat).match(line, at) or re.compile(pat).search(line, at)
    if not m: return None
    if rep is None:                      # const_off: n -> n+1
        try: v = int(m.group(1))
        except Exception: return None
        if v > 10**6: return None
        return line[:m.start(1)] + str(v + 1) + line[m.end(1):]
    return line[:m.start()] + rep + line[m.end():]

def suite(root, extra=()):
    cmd = ["../../.venv/bin/python", "-m", "pytest", "-q", "--no-header",
           "-p", "no:cacheprovider", "--ignore=tests/test_benchmarks.py",
           "-x", "--timeout=60"] + list(extra)
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=180)
        return p.returncode, p.stdout[-4000:]
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"
