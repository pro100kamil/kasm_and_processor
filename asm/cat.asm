ei
loop:
    jmp loop

int1:
    di
    input
    jz break,ir
    print
    ei
    iret

break:
    halt