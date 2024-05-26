mov r1,10
call factorial
halt

factorial:      ; res in r3, arg in r1
    mov r2,r1
    mov r3,1    ;res

    loop:
        jz break,r2
        mul r3,r3,r2
        dec r2
        jmp loop
    break:
        ret