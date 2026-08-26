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
"""Select N live mutants per library: mutations the library's own suite catches."""
import json, os, random, shutil, sys
from inject import sites, mutate, suite

LIBS = {"humanize-4.16.0":"humanize", "inflection-0.5.1":"inflection",
        "natsort-8.4.0":"natsort", "parse-1.22.1":"parse", "wcwidth-0.8.2":"wcwidth"}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
rng = random.Random(20260825)
picked, tried = [], 0
for lib, pkg in LIBS.items():
    root = os.path.join("libs", lib)
    S = sites(root, pkg); rng.shuffle(S)
    got = 0
    for (f, i, line, name, pat, rep, invoc, at) in S:
        if got >= N: break
        cand = mutate(line, pat, rep, at)
        if cand is None or cand == line: continue
        orig = open(f, encoding="utf-8").read(); L = orig.splitlines()
        L[i] = cand; open(f, "w", encoding="utf-8").write("\n".join(L) + "\n")
        tried += 1
        rc, out = suite(root)
        if rc != 0 and out != "TIMEOUT":          # a LIVE mutant: the suite catches it
            picked.append(dict(lib=lib, pkg=pkg, file=os.path.relpath(f, root), lineno=i,
                               orig=line, mutated=cand, op=name, in_vocab=invoc,
                               failing=out[-1500:]))
            got += 1
        open(f, "w", encoding="utf-8").write(orig)      # always restore
    print("  %-18s %d live mutants" % (lib, got), flush=True)
json.dump(picked, open("bugs.json", "w"), indent=1)
print("\n  %d bugs from %d mutations tried" % (len(picked), tried))
iv = sum(1 for b in picked if b["in_vocab"])
print("  inside fluid-router's four acts : %d      outside : %d" % (iv, len(picked)-iv))
