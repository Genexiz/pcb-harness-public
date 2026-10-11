/* STM32 transport replacement for Microchip's platform-specific SPI interface.
 * CAN API originals, copyright and license are preserved in ../canfdspi. */
#ifndef _DRV_SPI_H
#define _DRV_SPI_H
#include <stdint.h>
#define SPI_DEFAULT_BUFFER_LENGTH 96
int8_t DRV_SPI_TransferData(uint8_t,uint8_t *,uint8_t *,uint16_t);
void Nop(void);
#endif
