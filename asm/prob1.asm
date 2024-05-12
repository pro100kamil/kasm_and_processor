;If we list all the natural numbers below 10 that are multiples of 3 or 5, we get 3, 5, 6 and 9. The sum of these multiples is 23.
;Find the sum of all the multiples of 3 or 5 below 1000.

mov rc,999     ; counter
mov rs,0       ; total sum
loop:
    jz break,rc    ; if rc == 0 >= break

    mod r1,rc,3   ; r1 = rc % 3
    mod r2,rc,5   ; r2 = rc % 5
    mul r3,r1,r2  ; r3 = r1 * r2

    jnz end_of_loop,r3    ; if r3 != 0 => end_of_loop

    add rs,rs,rc  ; rs = rs + rc

    end_of_loop:
        dec rc      ; rc = rc - 1
        jmp loop
break:
    halt