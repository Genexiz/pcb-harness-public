#include "board.h"
volatile uint32_t scheduler_passes,scheduler_tick_overruns,scheduler_us_max;
volatile uint32_t stack_high_water_bytes;
extern uint32_t _stack_bottom,_stack_top;
int main(void){uint32_t *mark=&_stack_bottom;uint32_t safe_sp=__get_MSP()-256;while((uint32_t)mark<safe_sp)*mark++=0xa5a5a5a5;board_init();uint32_t last=HAL_GetTick(),scan_due=last+1000;for(;;){uint32_t now=HAL_GetTick();if(now!=last){if(now-last>1)scheduler_tick_overruns+=now-last-1;app_tick(&app,now);last=now;}uint32_t start=DWT->CYCCNT;serial_service(now);usb_service(now);i2c_service(now);can_service(now);external_spi_service(now);ethernet_service(now);if((int32_t)(now-scan_due)>=0){stack_high_water_bytes=stack_watermark(&_stack_bottom,((uint32_t)&_stack_top-(uint32_t)&_stack_bottom)/4);scan_due=now+1000;}uint32_t us=(DWT->CYCCNT-start)/(SystemCoreClock/1000000);if(us>scheduler_us_max)scheduler_us_max=us;scheduler_passes++;}}
