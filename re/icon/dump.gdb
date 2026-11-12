set pagination off
set confirm off
set remotetimeout 10
target remote 127.0.0.1:17411
break *0x1005ecd4
commands
silent
printf "REC16 hdr=%#x size=%#x data=%#x r0=%d\n", *(unsigned*)($r6+204), *(unsigned*)($r6+208), *(unsigned*)($r6+212), $r0
printf "REC15 hdr=%#x size=%#x data=%#x\n", *(unsigned*)($r6+192), *(unsigned*)($r6+196), *(unsigned*)($r6+200)
dump binary memory re/icon/stock16.bin *(unsigned*)($r6+212) (*(unsigned*)($r6+212))+(*(unsigned*)($r6+208))
dump binary memory re/icon/stock15.bin *(unsigned*)($r6+200) (*(unsigned*)($r6+200))+(*(unsigned*)($r6+196))
disable 1
continue
end
continue
