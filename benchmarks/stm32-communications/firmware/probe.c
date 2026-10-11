/* Resource/CRC/queue probe only. No USB, CAN, W5500, UART or I2C drivers. */
#include <stdint.h>
#include <stddef.h>

#define CLIENTS 9u
#define QUEUE_SIZE 256u
static volatile uint8_t queues[CLIENTS][QUEUE_SIZE];
static volatile uint16_t heads[CLIENTS], tails[CLIENTS];
static volatile uint32_t accepted[CLIENTS], rejected[CLIENTS], full[CLIENTS];
/* Chosen reserves, retained by volatile accesses; these are not actual stacks. */
#ifndef PROBE_HOST_TEST
static volatile uint8_t usb_reserve[2048], ethernet_reserve[2048];
static volatile uint8_t can_reserve[2048], scratch_reserve[512];
#endif

uint32_t probe_crc(const uint8_t *data, size_t length) {
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((0u - (crc & 1u)) & 0xedb88320u);
    }
    return ~crc;
}

int probe_accept(unsigned client, const uint8_t *data, size_t length, uint32_t crc) {
    if (client >= CLIENTS || !data || length == 0 || length >= QUEUE_SIZE) return -1;
    if (probe_crc(data, length) != crc) { ++rejected[client]; return -2; }
    unsigned used = (heads[client] - tails[client]) & (QUEUE_SIZE - 1u);
    if (length > QUEUE_SIZE - 1u - used) { ++full[client]; return -3; }
    for (size_t i = 0; i < length; ++i) {
        queues[client][heads[client]] = data[i];
        heads[client] = (heads[client] + 1u) & (QUEUE_SIZE - 1u);
    }
    ++accepted[client];
    return 0;
}

int probe_read(unsigned client) {
    if (client >= CLIENTS || tails[client] == heads[client]) return -1;
    int value = queues[client][tails[client]];
    tails[client] = (tails[client] + 1u) & (QUEUE_SIZE - 1u);
    return value;
}

#ifndef PROBE_HOST_TEST
int main(void) {
    const uint8_t frame[] = {1, 2, 3, 4, 5, 6, 7, 8};
    for (;;) {
        for (unsigned client = 0; client < CLIENTS; ++client) {
            (void)probe_accept(client, frame, sizeof(frame), probe_crc(frame, sizeof(frame)));
            while (probe_read(client) >= 0) { }
        }
        /* Touch every reserve byte: optimizer cannot remove the reservations. */
        for (unsigned i = 0; i < 2048; ++i) {
            usb_reserve[i] = (uint8_t)i;
            ethernet_reserve[i] = usb_reserve[i];
            can_reserve[i] = ethernet_reserve[i];
        }
        for (unsigned i = 0; i < 512; ++i) scratch_reserve[i] = can_reserve[i];
    }
}
#endif
