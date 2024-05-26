hello:
    add_str 12,'hello world!'
mov rc,12
mov r1,hello
loop:
    jz break,rc
    inc r1
    print_char r1

    dec rc
    jmp loop
break:
    halt