import sys, capstone
data=open(sys.argv[1],'rb').read()
start=int(sys.argv[2],16); end=int(sys.argv[3],16); base=int(sys.argv[4],16) if len(sys.argv)>4 else 0x100
md=capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
for i in md.disasm(data[start:end], base+start):
    print(f"{i.address:04x}: {i.bytes.hex():<14} {i.mnemonic} {i.op_str}")
