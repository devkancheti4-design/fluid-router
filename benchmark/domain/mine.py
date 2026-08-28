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
import re, subprocess, sys, json, os, collections
def sh(a,cwd): return subprocess.run(a,cwd=cwd,capture_output=True,text=True).stdout
out=[]
for repo in sys.argv[1:]:
    for line in sh(["git","log","--format=%H|%s","-i","--grep=fix","--grep=bug","--grep=incorrect",
                    "--grep=wrong","--grep=broken","-n","600"],repo).strip().splitlines():
        sha,msg=line.split("|",1)
        files=sh(["git","show","--name-only","--format=","--diff-filter=M",sha,"--"],repo).split()
        src=[f for f in files if f.endswith(".py") and "test" not in f.lower()]
        if len(src)!=1: continue
        d=sh(["git","show","--format=","--unified=0",sha,"--",src[0]],repo)
        adds=[l[1:] for l in d.splitlines() if l.startswith("+") and not l.startswith("+++")]
        dels=[l[1:] for l in d.splitlines() if l.startswith("-") and not l.startswith("---")]
        if not (1<=len(adds)<=4 and 1<=len(dels)<=4): continue
        out.append(dict(repo=os.path.basename(repo),sha=sha,msg=msg[:70],src=src[0],
                        adds=adds,dels=dels))
json.dump(out,open("candidates.json","w"),indent=1)
for k,v in sorted(collections.Counter(x["repo"] for x in out).items()): print("    %-10s %d" % (k,v))
print("    TOTAL %d candidate real bug-fixes" % len(out))
