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
"""Each repo's OWN dictionary, scored on that repo's held-out real bugs."""
import importlib.util, json, sys, os
import os as _o; _H=_o.path.dirname(_o.path.abspath(__file__))
S=json.load(open(_o.path.join(_H,"split.json"))); tot=hit=0; rows=[]
for repo in S:
    p=os.path.abspath(os.path.join(_H,"dictionaries",repo+".py"))
    sys.path.insert(0,os.path.dirname(p))
    try:
        sp=importlib.util.spec_from_file_location("d_"+repo,p)
        M=importlib.util.module_from_spec(sp); sp.loader.exec_module(M)
    except Exception as e:
        print("  %-10s DICTIONARY FAILED: %s" % (repo,str(e)[:50])); continue
    h=0; n=0; ns=[]
    for x in S[repo]["held"]:
        n+=1
        try: c=list(M.candidates(x["broken"]))
        except Exception: c=[]
        ns.append(len(c))
        ok=any(s.rstrip()==x["fixed"].rstrip() for s in c)
        h+=ok; rows.append((repo,ok,x["msg"],x["broken"],x["fixed"]))
    tot+=n; hit+=h
    print("  %-10s %d/%d = %3.0f%%   median %d candidates/line" %
          (repo,h,n,100*h/n, sorted(ns)[len(ns)//2] if ns else 0))
print("\n  SAME-CODEBASE TOTAL: %d/%d = %.0f%%" % (hit,tot,100*hit/tot))
print("  (cross-codebase, one mixed dictionary, was 16/39 = 41%)")
print("\n  what it recovered:")
for r,ok,m,b,f in rows:
    if ok:
        print("    [%-8s] %s" % (r,m[:52])); print("        - %s" % b.strip()[:70]); print("        + %s" % f.strip()[:70])
print("\n  what it still missed:")
k=0
for r,ok,m,b,f in rows:
    if not ok and k<8:
        k+=1; print("    [%-8s] %s" % (r,m[:52])); print("        - %s" % b.strip()[:70]); print("        + %s" % f.strip()[:70])
