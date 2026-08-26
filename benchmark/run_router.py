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
"""fluid-router (SHIPPED kdebug.py acts + SHIPPED worked example) on 40 unseen bugs.

The router is the only decision point. It is given the file containing the bug --
the same information the model side is given -- and must localise within it.
"""
import json, os, re, shutil, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fluid"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fluid", "examples"))
from fluid_router import route as router
from kdebug import observe, apply_act, WORKED_EXAMPLE

PY_ = "../../.venv/bin/python"
def pytest(root, args, timeout=90):
    try:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([PY_, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
                            "--ignore=tests/test_benchmarks.py", "--timeout=30", "-p", "no:benchmark"] + args,
                           cwd=root, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"

def failing_node(root):
    rc, out = pytest(root, ["--tb=no", "-q"])
    m = re.findall(r"^FAILED (\S+)", out, re.M)
    return m[0] if m else None

bugs = json.load(open("bugs.json")); results = []
for n, b in enumerate(bugs, 1):
    root = os.path.join("libs", b["lib"]); path = os.path.join(root, b["file"])
    pristine = open(path, encoding="utf-8").read()
    L = pristine.splitlines(); L[b["lineno"]] = b["mutated"]
    broken = "\n".join(L) + "\n"
    open(path, "w", encoding="utf-8").write(broken)
    for dp, dn, _ in os.walk(root):
        for d in list(dn):
            if d == "__pycache__": shutil.rmtree(os.path.join(dp, d), ignore_errors=True)
    node = failing_node(root)
    t0 = time.time(); tries = 0; fixed = None
    lines = broken.splitlines()
    try:
        for i, line in enumerate(lines):
            for kind in observe(line):
                act = router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)   # THE decision
                cand = apply_act(line, act)
                if cand == line: continue
                tries += 1
                new = lines[:]; new[i] = cand
                open(path, "w", encoding="utf-8").write("\n".join(new) + "\n")
                if node and pytest(root, [node, "--tb=no"], 60)[0] != 0: continue
                if pytest(root, ["--tb=no", "-q"])[0] == 0:                # no regression
                    fixed = (i, line, cand); raise StopIteration
    except StopIteration:
        pass
    dt = time.time() - t0
    open(path, "w", encoding="utf-8").write(pristine)              # always restore
    exact = bool(fixed and fixed[0] == b["lineno"] and fixed[2].rstrip() == b["orig"].rstrip())
    results.append(dict(**{k: b[k] for k in ("lib","file","op","in_vocab","orig","mutated")},
                        repaired=bool(fixed), exact=exact, tries=tries, secs=round(dt,1),
                        got=fixed[2] if fixed else None))
    print("  %2d/%d %-18s %-11s %-4s %-9s tries=%-4d %5.1fs" %
          (n, len(bugs), b["lib"][:18], b["op"], "IN" if b["in_vocab"] else "out",
           ("EXACT" if exact else "green") if fixed else "refused", tries, dt), flush=True)
json.dump(results, open("router_results_v2.json","w"), indent=1)
