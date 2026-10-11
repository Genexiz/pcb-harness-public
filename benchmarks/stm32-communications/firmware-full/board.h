#ifndef FULL_BOARD_H
#define FULL_BOARD_H
#include "stm32f1xx_hal.h"
#include "core.h"
extern app_t app;
extern UART_HandleTypeDef uart[3];
extern SPI_HandleTypeDef spi1, spi2;
extern I2C_HandleTypeDef i2c;
extern volatile uint32_t spi_faults;
extern volatile uint32_t usb_driver_faults,scheduler_us_max,scheduler_tick_overruns,i2c_irq_us_max;
extern volatile uint32_t stack_high_water_bytes;
void board_init(void);
void serial_service(uint32_t);
void i2c_service(uint32_t);
void external_spi_service(uint32_t);
void usb_service(uint32_t);
void can_service(uint32_t);
void ethernet_service(uint32_t);
void receive_bytes(unsigned, const uint8_t *, unsigned, uint32_t);
bool spi_transfer(unsigned owner, const uint8_t *, uint8_t *, uint16_t);
void fail_port(unsigned);
#endif
