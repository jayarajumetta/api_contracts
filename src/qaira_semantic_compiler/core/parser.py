from __future__ import annotations
import re
from pathlib import Path

def line_no(text, idx):
    return text.count("\n", 0, idx) + 1

def norm_path(p):
    if not p: return "/"
    return "/" + p.strip("/")

def find_matching_paren(text, open_idx, max_chars=30000):
    depth=0; quote=None; esc=False; line=False; block=False
    end=min(len(text), open_idx+max_chars)
    i=open_idx
    while i<end:
        ch=text[i]; nxt=text[i+1] if i+1<end else ""
        if line:
            if ch=="\n": line=False
            i+=1; continue
        if block:
            if ch=="*" and nxt=="/": block=False; i+=2; continue
            i+=1; continue
        if quote:
            if esc: esc=False
            elif ch=="\\": esc=True
            elif ch==quote: quote=None
            i+=1; continue
        if ch=="/" and nxt=="/": line=True; i+=2; continue
        if ch=="/" and nxt=="*": block=True; i+=2; continue
        if ch in ("'", '"', "`"): quote=ch; i+=1; continue
        if ch=="(": depth+=1
        elif ch==")":
            depth-=1
            if depth==0: return i
        i+=1
    return -1

def split_top_level_args(text):
    args=[]; start=0; pr=pc=ps=0; quote=None; esc=False; line=False; block=False; i=0
    while i<len(text):
        ch=text[i]; nxt=text[i+1] if i+1<len(text) else ""
        if line:
            if ch=="\n": line=False
            i+=1; continue
        if block:
            if ch=="*" and nxt=="/": block=False; i+=2; continue
            i+=1; continue
        if quote:
            if esc: esc=False
            elif ch=="\\": esc=True
            elif ch==quote: quote=None
            i+=1; continue
        if ch=="/" and nxt=="/": line=True; i+=2; continue
        if ch=="/" and nxt=="*": block=True; i+=2; continue
        if ch in ("'", '"', "`"): quote=ch; i+=1; continue
        if ch=="(": pr+=1
        elif ch==")": pr-=1
        elif ch=="{": pc+=1
        elif ch=="}": pc-=1
        elif ch=="[": ps+=1
        elif ch=="]": ps-=1
        elif ch=="," and pr==pc==ps==0:
            args.append(text[start:i].strip()); start=i+1
        i+=1
    tail=text[start:].strip()
    if tail: args.append(tail)
    return args

def extract_route_calls(text):
    pat=re.compile(r"\b(app|router|server|fastify)\.(get|post|put|patch|delete)\s*\(", re.I)
    for m in pat.finditer(text):
        open_idx=text.find("(", m.end()-1)
        close_idx=find_matching_paren(text, open_idx)
        if close_idx<0: continue
        args=split_top_level_args(text[open_idx+1:close_idx])
        if not args: continue
        pm=re.match(r"^[`'\"]([^`'\"]+)[`'\"]", args[0].strip())
        if not pm: continue
        handler=""
        for arg in reversed(args[1:]):
            if "=>" in arg or arg.strip().startswith(("async ", "function")):
                handler=arg.strip(); break
        if not handler and len(args)>1:
            for arg in args[1:]:
                hm=re.search(r"\bhandler\s*:\s*([\s\S]+)$", arg)
                if hm: handler=hm.group(1).strip()
        if not handler and len(args)>1:
            handler=args[-1].strip()
        yield {"method": m.group(2).upper(), "path": norm_path(pm.group(1)), "handler": handler, "line": line_no(text, m.start()), "call": text[m.start():close_idx+1]}
