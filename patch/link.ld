INCLUDE stock.ld
MEMORY { CAVE (rx) : ORIGIN = 0x1025A100, LENGTH = 0xF0F00 }
SECTIONS {
  .text : {
    KEEP(*(.text.entry*))
    *(.text*)
    *(.rodata*)
  } > CAVE
  /DISCARD/ : { *(.data*) *(.bss*) *(COMMON) *(.ARM.*) *(.comment) }
}
