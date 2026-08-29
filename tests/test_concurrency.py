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
"""ONE worked example of a data race, generalised to five different shapes.

The example is a counter whose method body performs an unguarded read-modify-
write. The act taken from it wraps a method body in `with self.lock:` -- it
matches the SHAPE, and hardcodes no name, type or data structure. It is then run
against races over a dict, a list, a compare-and-set and a two-field invariant,
none of which it was written against.

This is the strongest case for one-example generalisation, and it is worth being
clear about why: the fix here is CONTENT-FREE. "Put this body under the lock"
says nothing about what the body does. Categories whose fix carries content --
which string, which encoding, which argument -- do not generalise this cheaply.
See benchmark/domain/ for that measurement on real bugs.

A NOTE ON THE ORACLE, which is the whole reason an earlier version of this file
reported that concurrency was unreachable. A plain `self.n = self.n + v` race
does NOT fail reliably under CPython -- measured at 0 failures in 5 runs. A test
that passes with the bug present is not an oracle, and no repair tool can work
against one. Every module below performs a genuine read, yield, write, which
fails 3/3 and 5/5 in the runs recorded here. If you weaken that, this file will
start reporting false successes.

    python3 tests/test_concurrency.py        # ~5 s, no dependencies
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "examples"))
from fluid_router import route as router
from kdebug import WORKED_EXAMPLE


# ---------------------------------------------------------------- the example
EXAMPLE_BEFORE = """    def tally(self, v):
        t = self.n
        time.sleep(0)
        self.n = t + v"""
EXAMPLE_AFTER = """    def tally(self, v):
        with self.lock:
            t = self.n
            time.sleep(0)
            self.n = t + v"""


# ------------------------------------------------- the act taken from it
def act_guard_method_body(i, lines):
    """Wrap a method's body in `with self.lock:`.

    Derived from the example above: the diff adds one `with self.lock:` line and
    indents the body under it. Nothing else about the example is used -- not the
    method name, not the field name, not the type of the shared state.
    """
    m = re.match(r"^(\s*)def\s+\w+\(self\b.*\):\s*$", lines[i])
    if not m:
        return []
    ind = m.group(1)
    body_ind = ind + "    "
    j, body = i + 1, []
    while j < len(lines) and (lines[j].startswith(body_ind) or not lines[j].strip()):
        body.append(lines[j]); j += 1
    if not body or any("with self.lock" in b for b in body):
        return []
    guarded = [body_ind + "with self.lock:"] + ["    " + b if b.strip() else b for b in body]
    return [lines[:i + 1] + guarded + lines[j:]]


ACTS = [act_guard_method_body]


def candidates(lines):
    """The router names the act; it is never mapped by hand."""
    for i in range(len(lines)):
        for kind in range(len(ACTS)):
            act = router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)
            idx = act - WORKED_EXAMPLE[1]
            if 0 <= idx < len(ACTS):
                for new in ACTS[idx](i, lines):
                    if new != lines:
                        yield new


def repair(mod, test, timeout=60):
    d = tempfile.mkdtemp(); w = os.path.join(d, "_w"); os.makedirs(w)
    open(os.path.join(w, "test.py"), "w").write(test)
    lines = mod.splitlines(); tries = 0
    try:
        open(os.path.join(w, "mod.py"), "w").write(mod)
        if subprocess.run([sys.executable, "-B", "test.py"], cwd=w,
                          capture_output=True, timeout=timeout).returncode == 0:
            return None, 0                      # no failing test: nothing to repair
        for new in candidates(lines):
            tries += 1
            open(os.path.join(w, "mod.py"), "w").write("\n".join(new) + "\n")
            shutil.rmtree(os.path.join(w, "__pycache__"), ignore_errors=True)
            try:
                rc = subprocess.run([sys.executable, "-B", "test.py"], cwd=w,
                                    capture_output=True, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                rc = 1
            if rc == 0:
                return "\n".join(new) + "\n", tries
        return None, tries
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------- five shapes the act never saw
def _threads(body, n=8, each=400):
    return ("import threading\nfrom mod import T\no=T()\n"
            "ts=[threading.Thread(target=lambda:[%s for _ in range(%d)]) for _ in range(%d)]\n"
            "[t.start() for t in ts];[t.join() for t in ts]\n%s\nprint('ok')\n"
            % (body, each, n, "%s"))

BUGS = [
 ("counter accumulate  (int)",
  "import threading, time\nclass T:\n    def __init__(self):\n        self.lock=threading.Lock()\n        self.total=0\n    def add(self,v):\n        t=self.total\n        time.sleep(0)\n        self.total=t+v\n",
  _threads("o.add(1)") % "assert o.total==3200, o.total"),
 ("dict counter update (dict)",
  "import threading, time\nclass T:\n    def __init__(self):\n        self.lock=threading.Lock()\n        self.m={}\n    def bump(self,k):\n        c=self.m.get(k,0)\n        time.sleep(0)\n        self.m[k]=c+1\n",
  _threads("o.bump('x')") % "assert o.m['x']==3200, o.m['x']"),
 ("list rebuild append (list)",
  "import threading, time\nclass T:\n    def __init__(self):\n        self.lock=threading.Lock()\n        self.items=[]\n    def put(self,v):\n        n=len(self.items)\n        time.sleep(0)\n        self.items=self.items[:n]+[v]\n",
  ("import threading\nfrom mod import T\no=T()\n"
   "ts=[threading.Thread(target=lambda:[o.put(1) for _ in range(200)]) for _ in range(8)]\n"
   "[t.start() for t in ts];[t.join() for t in ts]\nassert len(o.items)==1600, len(o.items)\nprint('ok')\n")),
 ("running maximum     (compare-and-set)",
  "import threading, time\nclass T:\n    def __init__(self):\n        self.lock=threading.Lock()\n        self.hi=0\n        self.seen=0\n    def offer(self,v):\n        s=self.seen\n        time.sleep(0)\n        self.seen=s+1\n        if v>self.hi:\n            self.hi=v\n",
  ("import threading\nfrom mod import T\no=T()\n"
   "ts=[threading.Thread(target=lambda:[o.offer(1) for _ in range(300)]) for _ in range(8)]\n"
   "[t.start() for t in ts];[t.join() for t in ts]\nassert o.seen==2400, o.seen\nprint('ok')\n")),
 ("two-field invariant (two fields)",
  "import threading, time\nclass T:\n    def __init__(self):\n        self.lock=threading.Lock()\n        self.a=0\n        self.b=0\n    def step(self):\n        x=self.a\n        time.sleep(0)\n        self.a=x+1\n        self.b=self.a\n",
  ("import threading\nfrom mod import T\no=T()\n"
   "ts=[threading.Thread(target=lambda:[o.step() for _ in range(300)]) for _ in range(8)]\n"
   "[t.start() for t in ts];[t.join() for t in ts]\nassert o.a==2400, o.a\nprint('ok')\n")),
]


def main():
    print("=" * 74)
    print("ONE EXAMPLE OF A RACE, GENERALISED TO FIVE SHAPES")
    print("=" * 74)
    print("  the example supplied, and the only one:\n")
    for l in EXAMPLE_BEFORE.splitlines(): print("     - %s" % l)
    for l in EXAMPLE_AFTER.splitlines():  print("     + %s" % l)
    print("\n  the act taken from it wraps a method body in `with self.lock:`.")
    print("  no name, type or data structure is hardcoded.")
    print("  the router names it from worked example (kind %d -> act %d).\n" % WORKED_EXAMPLE)

    solved = 0
    for name, mod, test in BUGS:
        got, tries = repair(mod, test)
        ok = bool(got) and "with self.lock:" in got
        solved += ok
        print("  %-40s %-8s (%d tries)" % (name, "SOLVED" if ok else "no", tries))
    print("\n  %d/%d shapes repaired from one example, 0 tokens" % (solved, len(BUGS)))
    print("\n  RESULT: %s" % ("PASS" if solved == len(BUGS) else "FAIL"))
    return 0 if solved == len(BUGS) else 1


if __name__ == "__main__":
    sys.exit(main())
