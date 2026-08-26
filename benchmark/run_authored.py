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
"""Each repo's OWN Opus-5-authored dictionary, run on that repo's HELD-OUT bugs."""
import importlib.util, json, os, re, shutil, subprocess, sys, time
PY_="../../.venv/bin/python"
def load(lib):
    p=os.path.abspath(os.path.join("author",lib,"CONTRACT.py"))
    sys.path.insert(0, os.path.dirname(p))
    spec=importlib.util.spec_from_file_location("dict_"+lib.replace("-","_").replace(".","_"), p)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
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
bugs=json.load(open("bugs.json")); sp=json.load(open("split.json")); out=[]
for lib, held in sp["held"].items():
    try: M=load(lib)
    except Exception as e:
        print("  %-18s DICTIONARY FAILED TO LOAD: %s" % (lib,e), flush=True)
        for n in held: out.append(dict(n=n,lib=lib,repaired=False,exact=False,tries=0,secs=0,err=str(e)[:120]))
        continue
    for n in held:
        b=bugs[n]; root=os.path.join("libs",lib); path=os.path.join(root,b["file"])
        pris=open(path,encoding="utf-8").read(); L=pris.splitlines(); L[b["lineno"]]=b["mutated"]
        broken="\n".join(L)+"\n"; open(path,"w",encoding="utf-8").write(broken)
        for dp,dn,_ in os.walk(root):
            for d in list(dn):
                if d=="__pycache__": shutil.rmtree(os.path.join(dp,d),ignore_errors=True)
        node=failing_node(root); t0=time.time(); tries=0; fixed=None; lines=broken.splitlines()
        try:
            for i,line in enumerate(lines):
                try: cands=list(M.candidates(line))
                except Exception: cands=[]
                for cand in cands:
                    if not isinstance(cand,str) or cand==line: continue
                    tries+=1
                    if tries>4000: raise StopIteration
                    new=lines[:]; new[i]=cand
                    open(path,"w",encoding="utf-8").write("\n".join(new)+"\n")
                    if node and pytest(root,[node,"--tb=no"],60)[0]!=0: continue
                    if pytest(root,["--tb=no","-q"])[0]==0: fixed=(i,line,cand); raise StopIteration
        except StopIteration: pass
        dt=time.time()-t0; open(path,"w",encoding="utf-8").write(pris)
        ex=bool(fixed and fixed[0]==b["lineno"] and fixed[2].rstrip()==b["orig"].rstrip())
        out.append(dict(n=n,lib=lib,op=b["op"],repaired=bool(fixed),exact=ex,tries=tries,secs=round(dt,1)))
        print("  %02d %-18s %-11s %-9s tries=%-5d %6.1fs" % (n,lib[:18],b["op"],
              ("EXACT" if ex else "green") if fixed else "refused",tries,dt),flush=True)
json.dump(out,open("authored_results.json","w"),indent=1)
