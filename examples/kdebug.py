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
"""kdebug — a zero-token single-line repair engine.

  mechanical observer  ->  AUTHORED router kernel  ->  mechanical applier  ->  test
                            (sphere, minimal in D∩I)

The router is the only decision-maker and is the authored expression verbatim:
      act = 15 & ((x >> 4) + ((x >> 8) - x))          x = F1 | (A1<<4) | (Fq<<8)
It learns the fault->act offset from ONE worked example, so the act vocabulary can be
renumbered without touching the code. No language model is involved at any stage.
"""
import os, re, shutil, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fluid_router import route as router

WORKED_EXAMPLE = (0, 5)          # fault kind 0 is repaired by act 5. That is the only
                                 # mapping supplied; every other act is inferred.

def observe(line):
    """Fault kinds this line could exhibit, most-specific first."""
    kinds = []
    if re.search(r"[<>]=?", line):                                   kinds.append(0)
    if re.search(r"\d", line):                                       kinds.append(1)
    if re.match(r"^\s*return\s+.*\s(?://|[-+*])\s", line):            kinds += [2, 3]
    elif re.search(r"\s[-+]\s", line):                               kinds.append(3)
    return kinds

def apply_act(line, act):
    if act == 5:
        for a, b in ((">=", ">"), ("<=", "<")):
            if a in line: return line.replace(a, b, 1)
        for a, b in ((">", ">="), ("<", "<=")):
            if a in line: return line.replace(a, b, 1)
        return line
    if act == 6:
        m = re.search(r"\d+", line)
        if not m: return line
        out = line[:m.start()] + str(int(m.group()) - 1) + line[m.end():]
        return re.sub(r"\s*[+-]\s*0(?![0-9])", "", out)
    if act == 7:
        m = re.match(r"^(\s*return\s+)(.*?)(\s(?://|[-+*])\s)(.*)$", line)
        return line if not m else f"{m.group(1)}{m.group(4)}{m.group(3)}{m.group(2)}"
    if act == 8:
        if " + " in line: return line.replace(" + ", " - ", 1)
        if " - " in line: return line.replace(" - ", " + ", 1)
    return line

def repair(srcdir, modname="mod.py", testname="test.py", scratch=None):
    """Return (repaired_source, attempts) or (None, attempts)."""
    src = open(os.path.join(srcdir, modname)).read()
    lines = src.splitlines()
    w = scratch or os.path.join(srcdir, "..", "_kw")
    shutil.rmtree(w, ignore_errors=True); os.makedirs(w)
    shutil.copy(os.path.join(srcdir, testname), os.path.join(w, testname))
    tries = 0
    for i, line in enumerate(lines):
        for kind in observe(line):
            act = router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)
            cand = apply_act(line, act)
            if cand == line: continue
            tries += 1
            new = lines[:]; new[i] = cand
            shutil.rmtree(os.path.join(w, "__pycache__"), ignore_errors=True)
            open(os.path.join(w, modname), "w").write("\n".join(new) + "\n")
            if subprocess.run(["python3", "-B", testname], cwd=w,
                              capture_output=True).returncode == 0:
                return "\n".join(new) + "\n", tries
    return None, tries
