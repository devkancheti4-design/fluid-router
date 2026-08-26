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
"""Corrected verification. A PERFECT fix leaves zero files differing from pristine."""
import json, os, subprocess, filecmp
bugs = json.load(open("bugs.json")); out = []
for n, b in enumerate(bugs):
    sb = os.path.abspath("sandboxes/bug%02d" % n); pristine = os.path.join("libs", b["lib"])
    green = subprocess.run([os.path.join(sb,"RUN_TESTS.sh"),"--tb=no","-q"],
                           capture_output=True, text=True, timeout=400).returncode == 0
    changed, touched_tests = [], False
    for root, dirs, files in os.walk(sb):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",".pytest_cache","htmlcov",".git")]
        for f in files:
            if not f.endswith(".py"): continue
            p = os.path.join(root,f); rel = os.path.relpath(p, sb); q = os.path.join(pristine, rel)
            if os.path.exists(q) and not filecmp.cmp(p,q,shallow=False):
                changed.append(rel)
                if "test" in rel.lower(): touched_tests = True
    cur = open(os.path.join(sb, b["file"]), encoding="utf-8").read().splitlines()
    restored = b["lineno"] < len(cur) and cur[b["lineno"]].rstrip() == b["orig"].rstrip()
    exact = restored and not changed          # byte-identical to the pristine library
    out.append(dict(bug=n, lib=b["lib"], op=b["op"], in_vocab=b["in_vocab"], green=green,
                    exact=exact, restored=restored, files_changed=changed, touched_tests=touched_tests))
    print("  %02d %-18s %-11s green=%-5s exact=%-5s extra_files=%d%s" % (n, b["lib"][:18], b["op"],
          green, exact, max(0,len(changed)-(0 if exact else 0)),
          "  !! TEST EDITED" if touched_tests else ""), flush=True)
json.dump(out, open("model_results.json","w"), indent=1)
print("\n  MODEL (Opus 5, fresh instance per bug, sandbox-locked)")
print("  suite green      : %d/40" % sum(x["green"] for x in out))
print("  byte-exact       : %d/40" % sum(x["exact"] for x in out))
print("  test files edited: %d"    % sum(x["touched_tests"] for x in out))
