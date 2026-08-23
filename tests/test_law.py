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
"""Stress test for the routing law.

    LAW   act = 15 & ((x >> 4) + ((x >> 8) - x))        x = F1 | (A1<<4) | (Fq<<8)

Claim: from ONE worked example (fault F1 was repaired by act A1), the law returns the
act for any new fault Fq, for every possible renumbering of the act vocabulary. No
constant in the expression encodes the offset — there is nothing to memorise.

Reference: act = (Fq + A1 - F1) mod 16
"""
import itertools, os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fluid_router import route_packed as law, _w32 as w32

def pack(F1, A1, Fq, pollution=0):
    return w32((F1 & 15) | ((A1 & 15) << 4) | ((Fq & 15) << 8) | (pollution << 12))

def ref(F1, A1, Fq):
    return (Fq + A1 - F1) % 16

FAIL = 0
def check(name, ok, detail=""):
    global FAIL
    if not ok: FAIL += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  ' + detail if detail else ''}")

# ---------------------------------------------------------------- 1. complete domain
print("\n1. COMPLETE DOMAIN — all 4096 (F1, A1, Fq) triples")
wrong = [(a,b,c) for a,b,c in itertools.product(range(16), repeat=3)
         if law(pack(a,b,c)) != ref(a,b,c)]
check("law == (Fq + A1 - F1) mod 16 on all 4096", not wrong,
      f"{len(wrong)} wrong" if wrong else "0 wrong")

# ------------------------------------------------------- 2. every offset, every example
print("\n2. OFFSET GENERALISATION — all 16 renumberings, from every worked example")
bad = []
for off in range(16):
    for F1 in range(16):                    # the worked example may be ANY fault
        A1 = (F1 + off) % 16
        for Fq in range(16):
            if law(pack(F1, A1, Fq)) != (Fq + off) % 16:
                bad.append((off, F1, Fq))
check("all 16 offsets recovered from all 16 example faults", not bad,
      f"{len(bad)} wrong of 4096")

# --------------------------------------------------------------- 3. held-out offsets
print("\n3. FLUID INFERENCE — offsets never used to build the law")
TRAIN = {0, 5}                              # the only offsets ever supplied to the engine
HELD  = [o for o in range(16) if o not in TRAIN]
bad = [(o,F1,Fq) for o in HELD for F1 in range(16) for Fq in range(16)
       if law(pack(F1,(F1+o)%16,Fq)) != (Fq+o)%16]
check(f"{len(HELD)} unseen offsets x 256 cases", not bad, f"{len(bad)} wrong of {len(HELD)*256}")

# ------------------------------------------------------------ 4. algebraic properties
print("\n4. ALGEBRAIC PROPERTIES")
check("identity: route(F1,A1,F1) == A1",
      all(law(pack(a,b,a)) == b for a in range(16) for b in range(16)))
check("offset invariance: act - Fq == A1 - F1 (mod 16)",
      all((law(pack(a,b,c)) - c) % 16 == (b - a) % 16
          for a,b,c in itertools.product(range(16), repeat=3)))
check("zero offset is the identity map on Fq",
      all(law(pack(a,a,c)) == c for a in range(16) for c in range(16)))
check("translation: shifting F1 and A1 together changes nothing",
      all(law(pack(a,b,c)) == law(pack((a+d)%16,(b+d)%16,c))
          for a,b,c,d in itertools.product(range(16), repeat=4)))
check("involution at offset 8: applying twice returns Fq",
      all(law(pack(0,8,law(pack(0,8,c)))) == c for c in range(16)))
check("surjective: every act 0..15 is reachable",
      {law(pack(0,o,q)) for o in range(16) for q in range(16)} == set(range(16)))

# ------------------------------------------------------ 5. it is NOT a lookup table
print("\n5. NOT A LOOKUP TABLE")
# a table keyed only on Fq must fail: same Fq maps to different acts under different offsets
collisions = 0
for Fq in range(16):
    acts = {law(pack(0, off, Fq)) for off in range(16)}
    if len(acts) > 1: collisions += 1
check("each Fq yields 16 distinct acts across the 16 offsets", collisions == 16,
      f"{collisions}/16 faults are offset-dependent")
# a table keyed on (F1,Fq) ignoring A1 must also fail
tbl_bad = any(law(pack(a,b1,c)) != law(pack(a,b2,c))
              for a in range(16) for c in range(16)
              for b1,b2 in [(0,1)])
check("output genuinely depends on A1 (not derivable from F1,Fq)", tbl_bad)

# ------------------------------------------------------------- 6. pollution immunity
print("\n6. POLLUTION IMMUNITY — bits 12..31 must not influence the result")
rnd = random.Random(20260822)
pats = [0, 0xFFFFF, 0x80000, 0xA5A5A, 0x5A5A5, 1, 0xFFFFE] + \
       [rnd.randrange(0, 1 << 20) for _ in range(40)]
bad = [(a,b,c,p) for a,b,c in itertools.product(range(16), repeat=3) for p in pats
       if law(pack(a,b,c,p)) != ref(a,b,c)]
check(f"all 4096 triples x {len(pats)} pollution patterns", not bad, f"{len(bad)} wrong")

# ------------------------------------------------------------------ 7. sign extremes
print("\n7. SIGN AND WRAP EXTREMES")
edge = [0, 1, -1, 1 << 31, (1 << 31) - 1, -(1 << 31), 0x7FFFFFFF, 0xFFFFFFF0]
bad = []
for a,b,c in itertools.product(range(16), repeat=3):
    base = pack(a,b,c)
    for hi in edge:
        x = w32(base | w32(hi & ~0xFFF))
        if law(x) != ref(a,b,c): bad.append((a,b,c,hi))
check("high-bit patterns incl. sign bit set", not bad, f"{len(bad)} wrong")

# --------------------------------------------------------------------- 8. composition
print("\n8. COMPOSITION — chaining two routers composes their offsets")
bad = [(o1,o2,q) for o1 in range(16) for o2 in range(16) for q in range(16)
       if law(pack(0,o2,law(pack(0,o1,q)))) != (q+o1+o2) % 16]
check("route(o2, route(o1, q)) == q + o1 + o2 (mod 16)", not bad, f"{len(bad)} wrong of 4096")

print(f"\n{'='*66}\nPYTHON SUITE: {'ALL PASS' if FAIL == 0 else str(FAIL) + ' FAILURES'}")
sys.exit(1 if FAIL else 0)
