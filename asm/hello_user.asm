question:
    add_str 19,'what is your name? '
hello_start:
    add_str 6,'hello '
hello_end:
    add_str 1,'!'

mov r1,19           ; length
mov r2,question     ; beginning
call print_str

mov r3,0            ; length of name
mov r4,addr         ; beginning of name
ei
loop:
    jmp loop

int1:
    di
    right
    input
    jz break,ir
    inc r3
    ei
    iret

break:
    store r4,r3

    mov r1,6               ; length
    mov r2,hello_start     ; beginning
    call print_str

    mov r1,r3
    mov r2,r4
    call print_str

    mov r1,1
    mov r2,hello_end
    call print_str
    halt


print_str:
    loop_print_str:
        jz break_print_str,r1
        inc r2
        print_char r2

        dec r1
        jmp loop_print_str
    break_print_str:
        ret