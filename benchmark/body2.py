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
"""EXTENDED ACT DICTIONARY -- the 'company custom file' hypothesis.

Router untouched and imported verbatim. Only the mechanical body grows:
  * four new acts covering the fault classes the shipped four cannot express
  * the crude-transform fix the README already names: try EVERY literal on a
    line, not just re.search(r"\d+") which takes the first.

The kind -> act mapping is still never written down. It is inferred by the
router from the single shipped worked example (fault kind 0 -> act 5).
"""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fluid_router import route as router
WORKED_EXAMPLE = (0, 5)

def observe(line):
    k = []
    if re.search(r"[<>]=?", line):                              k.append(0)
    if re.search(r"\d", line):                                  k.append(1)
    if re.match(r"^\s*return\s+.*\s(?://|[-+*])\s", line):      k += [2, 3]
    elif re.search(r"\s[-+]\s", line):                          k.append(3)
    if re.search(r"\s[*/]\s", line):                            k.append(4)
    if re.search(r"\b(True|False)\b", line):                    k.append(5)
    if re.search(r"\s(and|or)\s", line):                        k.append(6)
    if re.search(r"[=!]=", line):                               k.append(7)
    return k

def _sub_at(line, m, rep):  return line[:m.start()] + rep + line[m.end():]

def acts(line, act):
    """Return EVERY candidate this act offers on this line (was: one)."""
    out = []
    if act == 5:                                    # comparison strictness
        for m in re.finditer(r"[<>]=|[<>](?!=)", line):
            t = m.group(); out.append(_sub_at(line, m, {"<":"<=", ">":">=", "<=":"<", ">=":">"}[t]))
    elif act == 6:                                  # EVERY literal, both directions
        for m in re.finditer(r"\b\d+\b", line):
            v = int(m.group())
            for d in (-1, +1):
                if 0 <= v + d <= 10**6: out.append(line[:m.start()] + str(v+d) + line[m.end():])
    elif act == 7:                                  # swap operands of a return
        m = re.match(r"^(\s*return\s+)(.*?)(\s(?://|[-+*])\s)(.*)$", line)
        if m: out.append("%s%s%s%s" % (m.group(1), m.group(4), m.group(3), m.group(2)))
    elif act == 8:                                  # additive flip, each site
        for m in re.finditer(r" [-+] ", line):
            out.append(_sub_at(line, m, " - " if m.group() == " + " else " + "))
    elif act == 9:                                  # NEW multiplicative flip
        for m in re.finditer(r" [*/] ", line):
            out.append(_sub_at(line, m, " / " if m.group() == " * " else " * "))
    elif act == 10:                                 # NEW boolean literal flip
        for m in re.finditer(r"\b(True|False)\b", line):
            out.append(_sub_at(line, m, "False" if m.group() == "True" else "True"))
    elif act == 11:                                 # NEW and/or flip
        for m in re.finditer(r"\s(and|or)\s", line):
            out.append(line[:m.start()] + (" or " if m.group().strip()=="and" else " and ") + line[m.end():])
    elif act == 12:                                 # NEW equality flip
        for m in re.finditer(r"[=!]=", line):
            out.append(_sub_at(line, m, "!=" if m.group()=="==" else "=="))
    return [c for c in out if c != line]

def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
