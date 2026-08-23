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
