# recursive-descent disassembler for main image: addr = file_offset - 0x100
import sys, capstone, collections
data=open(sys.argv[1],'rb').read()
img=data[0x100:]; N=len(img)
md=capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16); md.detail=True
import json,os
code={}; todo=[0,0x100,0x3d2d,0x3d6f]
for f in sys.argv[2:]:
    todo+= [a for a,_ in json.load(open(f))] if f.endswith('.json') else [int(f,16)]
calls=collections.Counter(); indirect=[]; jt=set()
while todo:
    a=todo.pop()
    while 0<=a<N and a not in code:
        ins=next(md.disasm(img[a:a+16],a),None)
        if ins is None: break
        code[a]=ins
        m=ins.mnemonic; nxt=a+ins.size
        if m.startswith('j') or m in('call','loop','loope','loopne','jcxz'):
            op=ins.operands[0] if ins.operands else None
            if op is not None and op.type==capstone.x86.X86_OP_IMM:
                t=op.imm&0xffff; todo.append(t)
                if m=='call': calls[t]+=1
            else: indirect.append((a,m,ins.op_str))
            if m in('jmp','ljmp'): break
        if m in('ret','retf','iret','hlt'): break
        a=nxt
print(f"image {N:#x} bytes; code bytes {sum(i.size for i in code.values()):#x}; insns {len(code)}",file=sys.stderr)
out=open('/dev/stdout','w')
targets=set(calls)|{(i.operands[0].imm&0xffff) for i in code.values() if i.mnemonic.startswith('j') and i.operands and i.operands[0].type==capstone.x86.X86_OP_IMM}
for a in sorted(code):
    i=code[a]
    if a in calls: out.write(f"\nsub_{a:04x}:   ; called {calls[a]}x\n")
    elif a in targets: out.write(f"loc_{a:04x}:\n")
    out.write(f"  {a:04x}: {i.bytes.hex():<12} {i.mnemonic} {i.op_str}\n")
print("INDIRECT:",*[f"{a:04x} {m} {o}" for a,m,o in indirect],sep="\n",file=sys.stderr)
# code ranges
rs=[];s=None;p=None
for a in sorted(code):
    if s is None: s=a
    elif a!=p: rs.append((s,p)); s=a
    p=a+code[a].size
rs.append((s,p))
big=[(x,y) for x,y in rs]
print("RANGES:",len(big),file=sys.stderr)
for x,y in big:
    if y-x>64: print(f"  {x:04x}-{y:04x}",file=sys.stderr)
