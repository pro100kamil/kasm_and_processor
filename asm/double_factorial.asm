mov r1,13
call f
halt

f:      ; arg in r1, res in r3,
    mov r2,r1
    mov r3,1

    loop:
        jz break,r2
        mul r3,r3,r2
        dec r2
        jz break,r2
        dec r2
        jmp loop
    break:
        ret
