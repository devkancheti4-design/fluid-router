#!/usr/bin/env python3
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
"""test_unseen.py — does the router generalise to code it has never seen?

Five single-line faults injected into idioms lifted from third-party libraries
that are NOT in the repository's measured set (cachetools, sortedcontainers,
boltons): funcy-style slicing, chunking, cachetools-style TTL arithmetic, a
sortedcontainers-style bisect bound, and a swapped-operand diff helper.

Each fault is one of the four acts the router routes to. Success is not
"the suite went green" — it is EXACT MATCH to the intended source, which is a
strictly stronger check and the one that catches a repair that greens a weak
suite with the wrong edit.

    python3 tests/test_unseen.py

NOTE ON THE TIMEOUT GUARD BELOW. examples/kdebug.py calls subprocess.run with
no timeout. A candidate that introduces a non-terminating loop therefore hangs
the pipeline forever -- measured: this exact corpus hung for 595 s and produced
nothing, because act 6 decremented a literal such that a loop counter advanced
by zero. This file installs a 5 s per-candidate bound so the suite terminates.
The bound belongs in kdebug.repair(); until it is there, this guard documents
the defect rather than hiding it.
"""
import os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))
import kdebug

# ---- the timeout guard described above -------------------------------------
_orig_run = subprocess.run
def _bounded(*a, **kw):
    kw.setdefault("timeout", 5)
    try:
        return _orig_run(*a, **kw)
    except subprocess.TimeoutExpired:
        class _R:  # a candidate that will not terminate is a failed candidate
            returncode = 1
        return _R()
kdebug.subprocess.run = _bounded

# ---- corpus: real idioms, one injected fault each --------------------------
CASES = {
    "funcy_slice_offset": (
        "def take(n, seq):\n    return list(seq[:n])\n\n"
        "def drop(n, seq):\n    return list(seq[n:])\n",
        "def take(n, seq):\n    return list(seq[:n])\n\n"
        "def drop(n, seq):\n    return list(seq[n + 1:])\n",
        "assert drop(2,[1,2,3,4])==[3,4]\nassert drop(0,[1,2])==[1,2]\n"
        "assert take(2,[1,2,3])==[1,2]\n"),
    "chunk_loop_bound": (
        "def chunked(seq, n):\n    out = []\n    i = 0\n    while i < len(seq):\n"
        "        out.append(seq[i:i+n])\n        i = i + n\n    return out\n",
        "def chunked(seq, n):\n    out = []\n    i = 0\n    while i <= len(seq):\n"
        "        out.append(seq[i:i+n])\n        i = i + n\n    return out\n",
        "assert chunked([1,2,3,4],2)==[[1,2],[3,4]]\n"
        "assert chunked([1,2,3],2)==[[1,2],[3]]\nassert chunked([],2)==[]\n"),
    "ttl_additive": (
        "def expires_at(now, ttl):\n    return now + ttl\n\n"
        "def expired(now, exp):\n    return now > exp\n",
        "def expires_at(now, ttl):\n    return now - ttl\n\n"
        "def expired(now, exp):\n    return now > exp\n",
        "assert expires_at(100,30)==130\nassert expired(140,130) is True\n"
        "assert expired(120,130) is False\n"),
    "bisect_strictness": (
        "def index_of(a, x):\n    lo, hi = 0, len(a)\n    while lo < hi:\n"
        "        mid = (lo + hi) // 2\n        if a[mid] < x:\n"
        "            lo = mid + 1\n        else:\n            hi = mid\n    return lo\n",
        "def index_of(a, x):\n    lo, hi = 0, len(a)\n    while lo < hi:\n"
        "        mid = (lo + hi) // 2\n        if a[mid] <= x:\n"
        "            lo = mid + 1\n        else:\n            hi = mid\n    return lo\n",
        "assert index_of([1,3,5,7],5)==2\nassert index_of([1,3,5,7],1)==0\n"
        "assert index_of([1,3,5,7],8)==4\n"),
    "delta_operand_swap": (
        "def delta(new, old):\n    return new - old\n",
        "def delta(new, old):\n    return old - new\n",
        "assert delta(10,4)==6\nassert delta(0,5)==-5\n"),
}


def main():
    work = tempfile.mkdtemp(prefix="fr_unseen_")
    print("UNSEEN-REPO GENERALISATION — five real idioms, none in the measured set\n")
    print("%-20s %-10s %-14s %-6s %s" % ("case", "result", "exact?", "tries", "secs"))
    print("-" * 70)
    repaired = exact = 0
    t_all = time.time()
    for name, (intended, buggy, test) in CASES.items():
        src = os.path.join(work, name, "src")
        os.makedirs(src, exist_ok=True)
        open(os.path.join(src, "mod.py"), "w").write(buggy)
        open(os.path.join(src, "test.py"), "w").write(
            "from mod import *\n" + test + "print('ok')\n")
        t0 = time.time()
        out, tries = kdebug.repair(src, scratch=os.path.join(work, name, "_w"))
        is_exact = (out == intended) if out else False
        repaired += 1 if out else 0
        exact += 1 if is_exact else 0
        print("%-20s %-10s %-14s %-6d %.2f" % (
            name, "REPAIRED" if out else "no repair",
            "YES" if is_exact else ("SUITE-GREEN ONLY" if out else "-"),
            tries, time.time() - t0))
    print("-" * 70)
    n = len(CASES)
    print("repaired %d/%d   EXACT %d/%d   %.1fs   0 tokens" % (
        repaired, n, exact, n, time.time() - t_all))
    shutil.rmtree(work, ignore_errors=True)
    ok = (exact == n)
    print("\nRESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
