#include <stdint.h>
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _stack_top;
extern int main(void);

static void default_handler(void) { for (;;) { } }
void reset_handler(void) {
    uint32_t *source = &_sidata;
    for (uint32_t *p = &_sdata; p < &_edata; ++p) *p = *source++;
    for (uint32_t *p = &_sbss; p < &_ebss; ++p) *p = 0;
    (void)main();
    default_handler();
}

/* Cortex-M3 core vectors. Probe never enables device interrupts. */
__attribute__((section(".vectors"), used))
const uintptr_t vectors[16] = {
    (uintptr_t)&_stack_top, (uintptr_t)reset_handler,
    (uintptr_t)default_handler, (uintptr_t)default_handler,
    (uintptr_t)default_handler, (uintptr_t)default_handler,
    (uintptr_t)default_handler, 0, 0, 0, 0,
    (uintptr_t)default_handler, (uintptr_t)default_handler, 0,
    (uintptr_t)default_handler, (uintptr_t)default_handler
};
