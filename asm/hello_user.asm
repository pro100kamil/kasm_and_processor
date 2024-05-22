question:
    add_str 19,'what is your name? '
hello_start:
    add_str 6,'hello '
hello_end:
    add_str 1,'!'

print_str question

mov r1,0  ;length
mov r2,addr ;start
ei
loop:
    jmp loop

int1:
    di
    right
    input
    jz break,acc
    inc r1
    ei
    iret

break:
    store r2,r1

    print_str hello_start
    print_str r2
    print_str hello_end
    halt
