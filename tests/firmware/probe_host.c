#include <stdint.h>
#include <stddef.h>
extern uint32_t probe_crc(const uint8_t *, size_t);
extern int probe_accept(unsigned, const uint8_t *, size_t, uint32_t);
extern int probe_read(unsigned);
int main(void) {
    const uint8_t known[] = "123456789";
    if (probe_crc(known, 9) != 0xcbf43926u) return 1;
    if (probe_accept(0, known, 9, 0) != -2 || probe_read(0) != -1) return 2;
    if (probe_accept(9, known, 9, 0xcbf43926u) != -1) return 3;
    for (unsigned i = 0; i < 28; ++i)
        if (probe_accept(0, known, 9, 0xcbf43926u) != 0) return 4;
    if (probe_accept(0, known, 9, 0xcbf43926u) != -3) return 5;
    for (unsigned i = 0; i < 252; ++i)
        if (probe_read(0) != known[i % 9]) return 6;
    if (probe_read(0) != -1) return 7;
    if (probe_accept(0, known, 9, 0xcbf43926u) != 0) return 8;
    return 0;
}
