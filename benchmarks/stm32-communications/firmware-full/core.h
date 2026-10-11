#ifndef FULL_CORE_H
#define FULL_CORE_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#define PORTS 9
#define FRAME_MAX 128
#define QUEUE_DEPTH 2
enum { USB_PORT, UART_PORT, RS485_PORT, RS232_PORT, I2C_PORT, SPI_PORT, CAN_PORT, FD_PORT, ETH_PORT };
typedef struct { uint32_t rx, tx, crc_error, lost, reorder, overflow, timeout, service, latency_ms_max, tx_complete; uint16_t expected, next; bool seen; } counters_t;
typedef struct { uint8_t bytes[FRAME_MAX]; uint16_t len; } frame_t;
typedef struct { frame_t frame[QUEUE_DEPTH]; uint8_t head, count; } queue_t;
typedef struct { counters_t stats[PORTS]; queue_t tx[PORTS]; uint32_t deadline[PORTS]; uint8_t cursor; } app_t;
typedef struct { uint8_t owner; uint32_t clock; uint16_t count; } bus_t;
extern const uint16_t frame_length[PORTS], period_ms[PORTS];
uint16_t crc16(const uint8_t *, size_t);
bool make_frame(frame_t *, uint16_t len, uint16_t seq, uint16_t tick, uint8_t port);
bool make_telemetry(frame_t *,uint16_t seq,uint16_t tick,uint8_t port,const counters_t *);
bool accept_frame(counters_t *, const uint8_t *, uint16_t len, uint32_t now);
void feed_frames(counters_t *,uint8_t *partial,uint16_t *used,const uint8_t *,uint16_t n,uint16_t frame_len,uint32_t now);
bool queue_push(queue_t *, const frame_t *, counters_t *);
frame_t *queue_peek(queue_t *);
void queue_pop(queue_t *);
void app_tick(app_t *, uint32_t now);
bool bus_begin(bus_t *, uint8_t owner, uint32_t clock, uint16_t count);
void bus_end(bus_t *);
uint32_t wire_us(uint16_t bytes, uint32_t hz);
uint32_t dma_produced(uint32_t wraps, uint16_t remaining, bool pending_tc);
bool irq_budget_take(uint8_t *);
bool bounded_reset_wait(bool ready,uint32_t start,uint32_t now,uint32_t limit);
uint32_t stack_watermark(const uint32_t *,size_t words);
#endif
