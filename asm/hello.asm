hello:
    add_str 12,'hello world!'
mov r1,12       ; length
mov r2,hello    ; beginning
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