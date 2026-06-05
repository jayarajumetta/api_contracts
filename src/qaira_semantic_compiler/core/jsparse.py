from __future__ import annotations
import re

def split_top_level_args(text: str):
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
        if ch in ("'",'"',"`"): quote=ch; i+=1; continue
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

def find_call_args(text: str, callee_regex: str):
    # callee_regex should match before the opening paren, e.g. r"service\.create"
    pat=re.compile(callee_regex+r"\s*\(")
    for m in pat.finditer(text):
        open_idx=text.find("(",m.end()-1)
        close=find_matching(text,open_idx,"(",")")
        if close>open_idx:
            yield m, split_top_level_args(text[open_idx+1:close]), text[m.start():close+1]

def find_matching(text,start,open_ch,close_ch,max_len=20000):
    depth=0; quote=None; esc=False; line=False; block=False
    for i in range(start,min(len(text),start+max_len)):
        ch=text[i]; nxt=text[i+1] if i+1<len(text) else ""
        if line:
            if ch=="\n": line=False
            continue
        if block:
            if ch=="*" and nxt=="/": block=False
            continue
        if quote:
            if esc: esc=False
            elif ch=="\\": esc=True
            elif ch==quote: quote=None
            continue
        if ch=="/" and nxt=="/": line=True; continue
        if ch=="/" and nxt=="*": block=True; continue
        if ch in ("'",'"',"`"): quote=ch; continue
        if ch==open_ch: depth+=1
        elif ch==close_ch:
            depth-=1
            if depth==0: return i
    return -1

def balanced_block(text,start):
    if start<0: return ""
    end=find_matching(text,start,"{","}",max_len=25000)
    return text[start:end+1] if end>start else text[start:start+25000]

def object_keys(obj):
    out=set()
    for m in re.finditer(r"(?:^|[,{\s])([A-Za-z_$][\w$]*)\s*:", obj):
        out.add(m.group(1))
    # shorthand keys in object literal: { title, description }
    for part in split_top_level_args(obj):
        p=part.strip()
        if re.match(r"^[A-Za-z_$][\w$]*$",p):
            out.add(p)
    return out
