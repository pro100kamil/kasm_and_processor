ei
loop:
    jmp loop

int1:
    di
    input
    jz break,acc
    print
    ei
    iret

break:
    halt