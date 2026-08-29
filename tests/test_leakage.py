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
"""ONE example of train/test leakage, generalised to seven variants.

Leakage is the bug that costs an afternoon precisely because it never raises: a
preprocessing statistic is computed over the whole dataset, the model trains, it
scores well, and the score is a lie. Nothing crashes. Nothing is red.

The example fixes one instance -- a mean and a standard deviation taken over all
rows, restricted to the training slice. The act taken from it learns the SHAPE:
*a statistic whose source should be the train slice, not the whole array*. It
hardcodes no statistic name, no array name, and no split-variable name -- the
split variable is recovered from the function's own signature by finding which
parameter is used as a slice bound in its body.

It then repairs seven variants it has never seen: median, quantile, norm,
variance, max, mean and standard deviation, across three call forms -- method
`xs.stat(...)`, function `stat(xs)`, and qualified `mod.stat(xs)`. The example
demonstrated only the method form, on only two statistics.

Written in plain Python so the repo keeps its no-dependency promise; the shape
is identical to the numpy original (`X.mean(axis=0)` -> `X[:n].mean(axis=0)`).

    python3 tests/test_leakage.py        # ~2 s, no dependencies
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "examples"))
from fluid_router import route as router
from kdebug import WORKED_EXAMPLE


# ---------------------------------------------------------------- the example
EXAMPLE_BEFORE = """def standardize(xs, n_train):
    mu = mean(xs)
    sd = stdev(xs)
    z = [(v - mu) / sd for v in xs]
    return z[:n_train], z[n_train:], mu
"""
EXAMPLE_AFTER = """def standardize(xs, n_train):
    mu = mean(xs[:n_train])
    sd = stdev(xs[:n_train])
    z = [(v - mu) / sd for v in xs]
    return z[:n_train], z[n_train:], mu
"""


# ------------------------------------------------- the act taken from it
def _split_var(lines, i):
    """Which parameter marks the split? Read it from the function itself --
    the one that appears as a slice bound somewhere in the body."""
    for j in range(i, -1, -1):
        m = re.match(r"^\s*def\s+\w+\(([^)]*)\)", lines[j])
        if not m:
            continue
        params = [p.strip().split(":")[0].split("=")[0].strip()
                  for p in m.group(1).split(",") if p.strip()]
        for p in params:
            pat = r"\[\s*:\s*%s\s*\]|\[\s*%s\s*:\s*\]" % (re.escape(p), re.escape(p))
            if any(re.search(pat, l) for l in lines):
                return p
        return params[-1] if params else None
    return None


def act_restrict_statistic(i, lines):
    """Restrict the source of a statistic to the training slice.

    Three call forms, because real code uses all three and the example only
    showed one:  xs.stat(...)  |  stat(xs)  |  mod.stat(xs)
    """
    n = _split_var(lines, i)
    if not n:
        return []
    line = lines[i]
    if "[:%s]" % n in line:
        return []                                   # already restricted
    out, seen = [], set()

    def emit(start, end, arr):
        if arr in ("self",) or (start, end) in seen:
            return
        seen.add((start, end))
        new = line[:start] + "%s[:%s]" % (arr, n) + line[end:]
        out.append(lines[:i] + [new] + lines[i + 1:])

    for m in re.finditer(r"(?<![\w.])([A-Za-z_]\w*)\.[a-z_]+\(", line):   # xs.stat(
        emit(m.start(1), m.end(1), m.group(1))
    for m in re.finditer(r"(?<![\w.])[a-z_]\w*\(\s*([A-Za-z_]\w*)", line):  # stat(xs)
        emit(m.start(1), m.end(1), m.group(1))
    for m in re.finditer(r"(?<![\w.])\w+(?:\.\w+)+\(\s*([A-Za-z_]\w*)", line):  # mod.stat(xs)
        emit(m.start(1), m.end(1), m.group(1))
    return out


ACTS = [act_restrict_statistic]


def candidates(lines):
    """The router names the act. It is never mapped by hand."""
    for i in range(len(lines)):
        for kind in range(len(ACTS)):
            act = router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)
            idx = act - WORKED_EXAMPLE[1]
            if 0 <= idx < len(ACTS):
                for new in ACTS[idx](i, lines):
                    if new != lines:
                        yield new


def repair(mod, test, timeout=30):
    d = tempfile.mkdtemp(); w = os.path.join(d, "_w"); os.makedirs(w)
    open(os.path.join(w, "test.py"), "w").write(test)
    lines = mod.splitlines(); tries = 0
    try:
        open(os.path.join(w, "mod.py"), "w").write(mod)
        if subprocess.run([sys.executable, "-B", "test.py"], cwd=w,
                          capture_output=True, timeout=timeout).returncode == 0:
            return None, 0, None                    # no failing test
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
                changed = [l for l in new if l not in lines]
                return "\n".join(new) + "\n", tries, (changed[0].strip() if changed else "")
        return None, tries, None
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------ seven variants it never saw
HEAD = ("import statistics\n"
        "def _norm(v):\n    return sum(x * x for x in v) ** 0.5\n")

def _test(fn, stat_expr, note):
    """The train slice must differ from the whole array under EVERY statistic --
    min, max, mean, median, variance, stdev and norm alike, or a variant has no
    failing test and the run reports a pass it did not earn. Two earlier datasets
    failed this: [1.0]*40+[100.0]*40 made min(train)==min(all), and
    [5.0]*40+[1.0]*20+[100.0]*20 made median(train)==median(all). The values
    below were checked against all seven statistics before being used."""
    return ("import statistics\nfrom mod import %s\n"
            "xs = [5.0]*40 + [1.0] + [100.0]*59\n"
            "got = %s(xs, 40)[2]\n"
            "want = %s\n"
            "assert abs(got - want) < 1e-9, %r\nprint('ok')\n"
            % (fn, fn, stat_expr, note))

BUGS = [
 ("median imputation",
  HEAD + "def impute(xs, n_train):\n    med = statistics.median(xs)\n"
         "    z = [med if v is None else v for v in xs]\n    return z[:n_train], z[n_train:], med\n",
  _test("impute", "statistics.median([5.0]*40)", "median came from ALL data")),
 ("variance-threshold selection",
  HEAD + "def select(xs, n_train):\n    var = statistics.pvariance(xs)\n"
         "    z = [v for v in xs]\n    return z[:n_train], z[n_train:], var\n",
  _test("select", "statistics.pvariance([5.0]*40)", "variance came from ALL data")),
 ("whitening factor from stdev",
  HEAD + "def whiten(xs, n_train):\n    s = statistics.pstdev(xs) + 1e-9\n"
         "    z = [v / s for v in xs]\n    return z[:n_train], z[n_train:], s\n",
  _test("whiten", "statistics.pstdev([5.0]*40) + 1e-9", "stdev came from ALL data")),
 ("mean centring only",
  HEAD + "def centre(xs, n_train):\n    mu = statistics.fmean(xs)\n"
         "    z = [v - mu for v in xs]\n    return z[:n_train], z[n_train:], mu\n",
  _test("centre", "statistics.fmean([5.0]*40)", "mean came from ALL data")),
 ("per-column max used for clipping",
  HEAD + "def clipall(xs, n_train):\n    cap = max(xs) * 0.9\n"
         "    z = [min(v, cap) for v in xs]\n    return z[:n_train], z[n_train:], cap\n",
  _test("clipall", "max([5.0]*40) * 0.9", "cap came from ALL data")),
 ("min used for shifting",
  HEAD + "def shift(xs, n_train):\n    lo = min(xs)\n"
         "    z = [v - lo for v in xs]\n    return z[:n_train], z[n_train:], lo\n",
  _test("shift", "min([5.0]*40)", "min came from ALL data")),
 ("L2 normalisation constant",
  HEAD + "def l2norm(xs, n_train):\n    nrm = _norm(xs) + 1e-9\n"
         "    z = [v / nrm for v in xs]\n    return z[:n_train], z[n_train:], nrm\n",
  _test("l2norm", "(sum(x*x for x in [5.0]*40)) ** 0.5 + 1e-9", "norm came from ALL data")),
]


def main():
    print("=" * 74)
    print("ONE LEAKAGE EXAMPLE, GENERALISED TO SEVEN VARIANTS")
    print("=" * 74)
    print("  the example supplied, and the only one:\n")
    for l in EXAMPLE_BEFORE.rstrip().splitlines(): print("     - %s" % l)
    print()
    for l in EXAMPLE_AFTER.rstrip().splitlines():  print("     + %s" % l)
    print("\n  a statistic taken over the WHOLE array, restricted to the train slice.")
    print("  no statistic, array or split-variable name is hardcoded.")
    print("  the router names the act from worked example (kind %d -> act %d).\n" % WORKED_EXAMPLE)

    print("  %-34s %-9s %6s  %s" % ("variant it has never seen", "result", "tries", "the line it wrote"))
    solved = 0
    for name, mod, test in BUGS:
        got, tries, line = repair(mod, test)
        ok = bool(got)
        solved += ok
        print("  %-34s %-9s %6d  %s" % (name, "SOLVED" if ok else "no", tries, (line or "")[:34]))
    print("\n  %d/%d variants repaired from one example, 0 tokens" % (solved, len(BUGS)))
    print("\n  RESULT: %s" % ("PASS" if solved == len(BUGS) else "FAIL"))
    return 0 if solved == len(BUGS) else 1


if __name__ == "__main__":
    sys.exit(main())
