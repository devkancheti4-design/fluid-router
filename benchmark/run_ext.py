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
import json, os, re, shutil, subprocess, sys, time
sys.path.insert(0,".")
from body2 import candidates
PY_="../../.venv/bin/python"
def pytest(root,args,t=90):
    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p=subprocess.run([PY_,"-m","pytest","-q","--no-header","-p","no:cacheprovider",
            "--ignore=tests/test_benchmarks.py","--timeout=30","-p","no:benchmark"]+args,
            cwd=root,capture_output=True,text=True,timeout=t,env=env)
        return p.returncode,p.stdout
    except subprocess.TimeoutExpired: return 1,"TIMEOUT"
def failing_node(root):
    m=re.findall(r"^FAILED (\S+)",pytest(root,["--tb=no","-q"])[1],re.M); return m[0] if m else None
bugs=json.load(open("bugs.json")); valid=json.load(open("valid.json")); out=[]
for n,b in enumerate(bugs):
    if not valid[n]: continue
    root=os.path.join("libs",b["lib"]); path=os.path.join(root,b["file"])
    pris=open(path,encoding="utf-8").read(); L=pris.splitlines(); L[b["lineno"]]=b["mutated"]
    broken="\n".join(L)+"\n"; open(path,"w",encoding="utf-8").write(broken)
    for dp,dn,_ in os.walk(root):
        for d in list(dn):
            if d=="__pycache__": shutil.rmtree(os.path.join(dp,d),ignore_errors=True)
    node=failing_node(root); t0=time.time(); tries=0; fixed=None
    lines=broken.splitlines()
    try:
        for i,line in enumerate(lines):
            for cand in candidates(line):
                tries+=1
                new=lines[:]; new[i]=cand
                open(path,"w",encoding="utf-8").write("\n".join(new)+"\n")
                if node and pytest(root,[node,"--tb=no"],60)[0]!=0: continue
                if pytest(root,["--tb=no","-q"])[0]==0: fixed=(i,line,cand); raise StopIteration
    except StopIteration: pass
    dt=time.time()-t0; open(path,"w",encoding="utf-8").write(pris)
    ex=bool(fixed and fixed[0]==b["lineno"] and fixed[2].rstrip()==b["orig"].rstrip())
    out.append(dict(n=n,lib=b["lib"],op=b["op"],iv=b["in_vocab"],repaired=bool(fixed),
                    exact=ex,tries=tries,secs=round(dt,1),got=fixed[2] if fixed else None))
    print("  %02d %-16s %-11s %-4s %-9s tries=%-5d %6.1fs" % (n,b["lib"][:16],b["op"],
          "IN" if b["in_vocab"] else "out",("EXACT" if ex else "green") if fixed else "refused",
          tries,dt),flush=True)
json.dump(out,open("ext_results.json","w"),indent=1)
