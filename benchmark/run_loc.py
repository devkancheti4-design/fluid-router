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
"""Same blind dictionaries, but the buggy LINE is given. Isolates dictionary
accuracy from the line search, which is what is actually failing above."""
import importlib.util, json, os, re, shutil, subprocess, sys, time
PY_="../../.venv/bin/python"
def load(lib):
    p=os.path.abspath(os.path.join("author",lib,"CONTRACT.py")); sys.path.insert(0,os.path.dirname(p))
    s=importlib.util.spec_from_file_location("L_"+lib.replace("-","_").replace(".","_"),p)
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def pytest(root,args,t=120):
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
    try:
        p=subprocess.run([PY_,"-m","pytest","-q","--no-header","-p","no:cacheprovider",
            "--ignore=tests/test_benchmarks.py","--timeout=30","-p","no:benchmark"]+args,
            cwd=root,capture_output=True,text=True,timeout=t,env=env)
        return p.returncode,p.stdout
    except subprocess.TimeoutExpired: return 1,"TIMEOUT"
bugs=json.load(open("bugs.json")); sp=json.load(open("split.json")); out=[]
for lib,held in sp["held"].items():
    M=load(lib)
    for n in held:
        b=bugs[n]; root=os.path.join("libs",lib); path=os.path.join(root,b["file"])
        pris=open(path,encoding="utf-8").read(); L=pris.splitlines(); L[b["lineno"]]=b["mutated"]
        open(path,"w",encoding="utf-8").write("\n".join(L)+"\n")
        for dp,dn,_ in os.walk(root):
            for d in list(dn):
                if d=="__pycache__": shutil.rmtree(os.path.join(dp,d),ignore_errors=True)
        node=re.findall(r"^FAILED (\S+)",pytest(root,["--tb=no","-q"])[1],re.M)
        node=node[0] if node else None
        t0=time.time(); fixed=None; tries=0
        for cand in M.candidates(b["mutated"]):
            if not isinstance(cand,str) or cand==b["mutated"]: continue
            tries+=1
            new=L[:]; new[b["lineno"]]=cand
            open(path,"w",encoding="utf-8").write("\n".join(new)+"\n")
            if node and pytest(root,[node,"--tb=no"],60)[0]!=0: continue
            if pytest(root,["--tb=no","-q"])[0]==0: fixed=cand; break
        dt=time.time()-t0; open(path,"w",encoding="utf-8").write(pris)
        ex=bool(fixed and fixed.rstrip()==b["orig"].rstrip())
        out.append(dict(n=n,lib=lib,op=b["op"],repaired=bool(fixed),exact=ex,tries=tries,secs=round(dt,1)))
        print("  %02d %-18s %-11s %-9s tries=%-4d %6.1fs" % (n,lib[:18],b["op"],
              ("EXACT" if ex else "GREEN-ONLY") if fixed else "no-fix",tries,dt),flush=True)
json.dump(out,open("loc_results.json","w"),indent=1)
