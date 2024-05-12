question:
    add_str 19,'what is your name? '
hello_start:
    add_str 6,'hello '
hello_end:
    add_str 1,'!'

print_str question

break:
    print_str hello_start
    ;
    print_str hello_end
    halt
