;If we list all the natural numbers below 10 that are multiples of 3 or 5, we get 3, 5, 6 and 9. The sum of these multiples is 23.
;Find the sum of all the multiples of 3 or 5 below 1000.

mov rs,0       ; total sum
mov rc,999     ; counter
loop3:
    jz break3,rc    ; if rc == 0 >= break

    add rs,rs,rc  ; rs = rs + rc

    end_of_loop3:
        sub rc,rc,3      ; rc = rc - 3
        jmp loop3
break3:
    mov rc,995

loop5:
    jz break5,rc    ; if rc == 0 >= break

    add rs,rs,rc  ; rs = rs + rc

    end_of_loop5:
        sub rc,rc,5      ; rc = rc - 5
        jmp loop5
break5:
    mov rc,990

loop15:
    jz break15,rc    ; if rc == 0 >= break

    sub rs,rs,rc  ; rs = rs - rc

    end_of_loop15:
        sub rc,rc,15      ; rc = rc - 15
        jmp loop15
break15:
    halt