# Minimal PC harness for LSTONE.COM (Opera Soft): CGA mode 4, INT 9 keyboard, INT 1Ch timer.
import sys, json, struct
from unicorn import *
from unicorn.x86_const import *
from PIL import Image
COM=sys.argv[1]; OUT=sys.argv[2]; script=json.loads(sys.argv[3])  # list of [tick, action, arg]
TICKS=int(sys.argv[4]) if len(sys.argv)>4 else 3000
PSP=0x1000; GS=PSP+0x20   # game segment: addr = fileoffset-0x100
mu=Uc(UC_ARCH_X86, UC_MODE_16); mu.mem_map(0,0x110000)
_com=open(COM,'rb').read()
WRAPPED=_com[:3]==b'\xe9\xac\x00'   # 1991 Kiev port: loader wrapper in front, game at PSP+0x20
if WRAPPED:
    mu.mem_write(PSP*16+0x100,_com)
else:                                # plain COM: run it in the game segment (its own PSP)
    mu.mem_write(GS*16+0x100,_com)
    mu.mem_write(GS*16+0x64d,b'\x75'); mu.mem_write(GS*16+0x3f96,b'\xe6\x61')  # undo LSTONE's trainer
# IVT: point every vector at an IRET stub at F000:FF00
mu.mem_write(0xFFF00,b'\xcf')
for v in range(256): mu.mem_write(v*4,struct.pack('<HH',0xFF00,0xF000))
mu.mem_write(0xFFFF0,b'\xf4')  # reboot target -> hlt
for r in (UC_X86_REG_CS,UC_X86_REG_DS,UC_X86_REG_ES,UC_X86_REG_SS): mu.reg_write(r,PSP if WRAPPED else GS)
mu.reg_write(UC_X86_REG_SP,0xfffe)
pal=[0x10,1]; scancode=[0]; cov=set()
def intr(uc,n,_):
    ax=uc.reg_read(UC_X86_REG_AX)
    if n==0x10:
        if ax>>8==0x0b: pal[(uc.reg_read(UC_X86_REG_BX)>>8)&1]=uc.reg_read(UC_X86_REG_BX)&0xff
    # emulate IRET of the software int: unicorn pushed nothing; just continue
mu.hook_add(UC_HOOK_INTR,intr)
mu.hook_add(UC_HOOK_INSN,lambda uc,p,s,_: (scancode[0] if p==0x60 else 0xff if p==0x202 else 0),None,1,0,UC_X86_INS_IN)
mu.hook_add(UC_HOOK_INSN,lambda uc,p,s,v,_: None,None,1,0,UC_X86_INS_OUT)
def blk(uc,addr,size,_):
    if (addr>>4)>=GS and addr<GS*16+0x10000: cov.add((addr-GS*16,size))
mu.hook_add(UC_HOOK_BLOCK,blk)
def irq(vec):
    sp=mu.reg_read(UC_X86_REG_SP); ss=mu.reg_read(UC_X86_REG_SS)
    fl=mu.reg_read(UC_X86_REG_EFLAGS)
    if not fl&0x200: return False
    cs=mu.reg_read(UC_X86_REG_CS); ip=mu.reg_read(UC_X86_REG_IP)
    sp-=6; mu.mem_write(ss*16+sp,struct.pack('<HHH',ip,cs,fl&0xffff)); mu.reg_write(UC_X86_REG_SP,sp)
    off,seg=struct.unpack('<HH',mu.mem_read(vec*4,4))
    mu.reg_write(UC_X86_REG_EFLAGS,fl&~0x200); mu.reg_write(UC_X86_REG_CS,seg); mu.reg_write(UC_X86_REG_IP,off)
    return True
PALS={0:[(0,0,0),(0,170,0),(170,0,0),(170,85,0)],1:[(0,0,0),(0,170,170),(170,0,170),(170,170,170)]}
EGA=[(0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),(170,85,0),(170,170,170),(85,85,85),(85,85,255),(85,255,85),(85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255)]
def shot(name):
    vm=bytes(mu.mem_read(0xB8000,0x4000)); im=Image.new('RGB',(320,200))
    p=[EGA[pal[0]&15]]+PALS[pal[1]&1][1:]
    if pal[0]&0x10: p=[p[0]]+[tuple(min(255,c+85) for c in x) for x in p[1:]]
    px=im.load()
    for y in range(200):
        base=(y&1)*0x2000+(y>>1)*80
        for xb in range(80):
            b=vm[base+xb]
            for k in range(4): px[xb*4+k,y]=p[(b>>(6-2*k))&3]
    im.resize((640,400),Image.NEAREST).save(f"{OUT}/{name}.png")
import importlib.util, os as _os
_spec=importlib.util.spec_from_file_location('gfx',_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'extract_gfx.py'))
_argv=sys.argv; sys.argv=[COM]; gfx=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gfx); sys.argv=_argv
static_maps={r:bytes(gfx.room_map(r)[0]) for r in range(gfx.NUM_ROOMS)}
TRACK={int(x,16) for x in _os.environ.get('TRACK','').split()}
track_out=open(f'{OUT}/track.txt','w')
pending=list(script); last_room=[None]; seen={}; tilediff={}; seen={}
mu.reg_write(UC_X86_REG_CS,PSP if WRAPPED else GS); mu.reg_write(UC_X86_REG_IP,0x100)
def run(n):
    addr=mu.reg_read(UC_X86_REG_CS)*16+mu.reg_read(UC_X86_REG_IP)
    mu.emu_start(addr,0,count=n)
for t in range(TICKS):
    try:
        run(12000)
        # IRQs are delivered after the slice (IF is normally set there); the timer
        # handler clears IF, so the keyboard IRQ must go first and run to completion.
        for ev in [e for e in pending if e[0]==t]:
            pending.remove(ev)
            if ev[1]=='shot': shot(ev[2])
            elif ev[1]=='dump':
                open(f"{OUT}/{ev[2]}.bin",'wb').write(bytes(mu.mem_read(GS*16,0x10000)))
                open(f"{OUT}/{ev[2]}.vram",'wb').write(bytes(mu.mem_read(0xB8000,0x4000)))
            elif ev[1] in('down','up'):
                scancode[0]=ev[2]|(0x80 if ev[1]=='up' else 0)
                if irq(9): run(2000)
                else: pending.append([t+1]+ev[1:])
    except UcError as e:
        print("ERR",t,e,hex(mu.reg_read(UC_X86_REG_CS)),hex(mu.reg_read(UC_X86_REG_IP))); break
    if mu.reg_read(UC_X86_REG_CS)==0xF000 and mu.reg_read(UC_X86_REG_IP)>=0xFFF0: print("halt/reboot",t); break
    irq(0x1c)
    r=mu.mem_read(GS*16+0xe04a,1)[0]
    if r!=last_room[0]: print('tick',t,'room',hex(r)); last_room[0]=r
    if TRACK and r in TRACK:  # per-tick positions of logs (tile map) and objects
        m=mu.mem_read(GS*16,0x10000); tm=m[0xe04c:0xe04c+800]
        logs=[(i//40,i%40) for i in range(800) if tm[i]==222]
        objs=[]; a=0xde46
        while a<0xe04c and m[a]!=0xff:
            if m[a]&0x80: objs.append(((a-0xde46)//0x28,m[a+0x1a],m[a+0x1b],m[a+0x26]|m[a+0x27]<<8))
            a+=0x28
        track_out.write(f"{t},{r},{logs},{objs}\n")
    if t%3==0:  # tilemap cells that differ from the static room layout (moving tiles)
        tm=bytes(mu.mem_read(GS*16+0xe04c,800))
        if r in static_maps:
            for i,(a,b) in enumerate(zip(tm,static_maps[r])):
                if a!=b: tilediff.setdefault(r,{}).setdefault(i,set()).add(a)
    if t%5==0:  # which sprites appear in which room
        m=mu.mem_read(GS*16,0x10000); a=0xde46
        while a<0xe04c and m[a]!=0xff:
            if m[a]&0x80: seen.setdefault(r,set()).add(m[a+0x26]|m[a+0x27]<<8)
            a+=0x28
    if TRACK and r in TRACK:  # per-tick positions of logs (tile map) and objects
        m=mu.mem_read(GS*16,0x10000); tm=m[0xe04c:0xe04c+800]
        logs=[(i//40,i%40) for i in range(800) if tm[i]==222]
        objs=[]; a=0xde46
        while a<0xe04c and m[a]!=0xff:
            if m[a]&0x80: objs.append(((a-0xde46)//0x28,m[a+0x1a],m[a+0x1b],m[a+0x26]|m[a+0x27]<<8))
            a+=0x28
        track_out.write(f"{t},{r},{logs},{objs}\n")
    if t%3==0:  # tilemap cells that differ from the static room layout (moving tiles)
        tm=bytes(mu.mem_read(GS*16+0xe04c,800))
        if r in static_maps:
            for i,(a,b) in enumerate(zip(tm,static_maps[r])):
                if a!=b: tilediff.setdefault(r,{}).setdefault(i,set()).add(a)
    if t%5==0:  # which sprites appear in which room
        m=mu.mem_read(GS*16,0x10000); a=0xde46
        while a<0xe04c and m[a]!=0xff:
            if m[a]&0x80: seen.setdefault(r,set()).add((a-0xde46)//0x28*0x10000+(m[a+0x26]|m[a+0x27]<<8))
            a+=0x28
json.dump({f'{k:02x}':{str(i):sorted(v) for i,v in d.items()} for k,d in tilediff.items()},open(f'{OUT}/tilediff.json','w'))
json.dump(sorted(cov),open(f"{OUT}/cov.json","w"))
json.dump({f"{k:02x}":sorted(f"{v:04x}" for v in vs) for k,vs in seen.items()},open(f"{OUT}/room_sprites.json","w"),indent=1)
json.dump({hex(k):sorted(f"{v>>16}:{v&0xffff:04x}" for v in vs) for k,vs in seen.items()},open(f"{OUT}/room_sprites.json","w"),indent=1)
print("blocks",len(cov),"bytes",len({a+i for a,s in cov for i in range(s)}))
