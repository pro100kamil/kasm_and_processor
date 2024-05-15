input
loop:
    jz break,acc
    print
    input
    jmp loop
break:
    halt