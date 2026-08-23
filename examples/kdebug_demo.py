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
"""Demo: repair a single-line bug with the router as the only decision-maker."""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kdebug import repair

MOD = '''\
def count_above(xs, t):
    n = 0
    for x in xs:
        if x >= t:
            n += 1
    return n
'''
FIXED = MOD.replace("x >= t", "x > t")
TEST = 'from mod import *\nassert count_above([1, 5, 5, 9], 5) == 1\nprint("ALL PASS")\n'

d = tempfile.mkdtemp()
open(os.path.join(d, "mod.py"), "w").write(MOD)
open(os.path.join(d, "test.py"), "w").write(TEST)
print("buggy:  ", MOD.splitlines()[3].strip())
got, tries = repair(d, scratch=os.path.join(d, "_w"))
print("repaired:", got.splitlines()[3].strip() if got else "FAILED")
print(f"attempts: {tries}   exact match to intended source: {got == FIXED}")
shutil.rmtree(d, ignore_errors=True)
