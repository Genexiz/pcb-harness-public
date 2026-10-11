ENTRY(Reset_Handler)
MEMORY {
 FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K
 RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}
SECTIONS {
 .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
 .text : { *(.text*) *(.rodata*) . = ALIGN(4); } > FLASH
 .ARM.extab : { *(.ARM.extab*) } > FLASH
 .ARM.exidx : { *(.ARM.exidx*) } > FLASH
 _sidata = LOADADDR(.data);
 .data : { _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT> FLASH
 .bss (NOLOAD) : { _sbss = .; *(.bss*) *(COMMON) . = ALIGN(8); _ebss = .; } > RAM
 .stack (NOLOAD) : { _stack_bottom = .; . += 8192; _stack_top = .; } > RAM
 _estack = _stack_top;
 /DISCARD/ : { *(.comment*) *(.note*) }
 ASSERT(_stack_top <= ORIGIN(RAM)+LENGTH(RAM), "RAM plus stack overflow")
 ASSERT(LOADADDR(.data)+SIZEOF(.data) <= ORIGIN(FLASH)+LENGTH(FLASH), "flash overflow")
}
