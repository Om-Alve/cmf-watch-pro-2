    .syntax unified
    .thumb
    .section .text.entry, "ax"
    .global hook_boot
    .type hook_boot, %function
hook_boot:
    push {r0-r4, lr}
    bl remote_on_boot
    pop {r0-r4, lr}
    b.w stock_system_app_launch
