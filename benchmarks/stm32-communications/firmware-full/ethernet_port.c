/* WIZnet ioLibrary W5500 register/buffer driver with an application-owned
 * nonblocking UDP protocol. Upstream socket.c's polling loops are not used. */
#include "board.h"
#include "wizchip_conf.h"
#include "w5500.h"
static uint8_t state;
static uint32_t deadline,next_service,next_rx,spi_start;
static uint8_t spi_failed;
static uint16_t discard_remaining;
volatile uint32_t ethernet_spi_errors,ethernet_irq_samples;
static void no_critical(void){}
static void select_chip(void){HAL_GPIO_WritePin(GPIOB,GPIO_PIN_12,GPIO_PIN_RESET);spi_start=DWT->CYCCNT;spi_failed=0;}
static void deselect_chip(void){while(SPI2->SR&SPI_SR_BSY){if(DWT->CYCCNT-spi_start>SystemCoreClock/1000){spi_failed=1;break;}}HAL_GPIO_WritePin(GPIOB,GPIO_PIN_12,GPIO_PIN_SET);if(spi_failed){ethernet_spi_errors++;__HAL_SPI_DISABLE(&spi2);__HAL_RCC_SPI2_FORCE_RESET();__HAL_RCC_SPI2_RELEASE_RESET();HAL_SPI_Init(&spi2);}}
static uint8_t transfer(uint8_t b){if(spi_failed)return 0;while(!(SPI2->SR&SPI_SR_TXE)){if(DWT->CYCCNT-spi_start>SystemCoreClock/1000){spi_failed=1;return 0;}}*(__IO uint8_t *)&SPI2->DR=b;while(!(SPI2->SR&SPI_SR_RXNE)){if(DWT->CYCCNT-spi_start>SystemCoreClock/1000){spi_failed=1;return 0;}}return *(__IO uint8_t *)&SPI2->DR;}
static uint8_t read_spi(void){return transfer(0xff);}
static void write_spi(uint8_t b){(void)transfer(b);}
static void restart(uint32_t now){fail_port(ETH_PORT);state=0;deadline=now+100;HAL_GPIO_WritePin(GPIOB,GPIO_PIN_5,GPIO_PIN_RESET);}
/* Upstream getSn_RX_RSR/getSn_TX_FSR retry until stable without a bound.
 * Read exactly twice and defer a changing value to the next scheduler pass. */
static bool stable_size(uint32_t address,uint16_t *out){uint16_t a=(uint16_t)(WIZCHIP_READ(address)<<8)|WIZCHIP_READ(address+(1<<8));uint16_t b=(uint16_t)(WIZCHIP_READ(address)<<8)|WIZCHIP_READ(address+(1<<8));if(a!=b)return false;*out=a;return true;}
void ethernet_service(uint32_t now){
 if((int32_t)(now-next_service)<0)return;next_service=now+1;app.stats[ETH_PORT].service++;
 uint32_t before=ethernet_spi_errors;
 if(state==0){if((int32_t)(now-deadline)<0)return;HAL_GPIO_WritePin(GPIOB,GPIO_PIN_5,GPIO_PIN_RESET);deadline=now+2;state=1;return;}
 if(state==1){if((int32_t)(now-deadline)<0)return;HAL_GPIO_WritePin(GPIOB,GPIO_PIN_5,GPIO_PIN_SET);deadline=now+500;state=2;return;}
 if(state==2){if(!HAL_GPIO_ReadPin(GPIOC,GPIO_PIN_13)){if((int32_t)(now-deadline)>=0)restart(now);return;}
 reg_wizchip_cris_cbfunc(no_critical,no_critical);reg_wizchip_cs_cbfunc(select_chip,deselect_chip);reg_wizchip_spi_cbfunc(read_spi,write_spi);
 if(getVERSIONR()!=4){restart(now);return;}
 uint8_t size[8]={2,0,0,0,0,0,0,0};if(wizchip_init(size,size)!=0){restart(now);return;}
 /* WIZ550io's boot MAC is retained; avoid replacing it with a fabricated OUI. */
 uint8_t ip[4]={192,168,50,100},mask[4]={255,255,255,0},gw[4]={192,168,50,1};setSIPR(ip);setSUBR(mask);setGAR(gw);setRTR(2000);setRCR(1);setSn_MR(0,Sn_MR_UDP);setSn_PORT(0,5000);setSn_IMR(0,(Sn_IR_RECV|Sn_IR_SENDOK|Sn_IR_TIMEOUT));setSIMR(1);setSn_CR(0,Sn_CR_OPEN);deadline=now+10;state=3;
 }
 else if(state==3){if(getSn_CR(0)==0&&getSn_SR(0)==SOCK_UDP)state=4;else if((int32_t)(now-deadline)>=0)restart(now);}
 else if(state==5){if(getSn_CR(0)==0)state=4;else if((int32_t)(now-deadline)>=0)restart(now);}
 else if(state==6){uint8_t ir=getSn_IR(0);if(ir&Sn_IR_TIMEOUT){setSn_IR(0,Sn_IR_TIMEOUT);queue_pop(&app.tx[ETH_PORT]);restart(now);}else if(ir&Sn_IR_SENDOK){setSn_IR(0,Sn_IR_SENDOK);queue_pop(&app.tx[ETH_PORT]);app.stats[ETH_PORT].tx_complete++;state=4;}else if((int32_t)(now-deadline)>=0){queue_pop(&app.tx[ETH_PORT]);restart(now);}}
 else if(state==4){
 if(!HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_8))ethernet_irq_samples++;
 if((int32_t)(now-next_rx)>=0){next_rx=now+8;uint16_t bytes;
 if(stable_size(Sn_RX_RSR(0),&bytes)&&bytes){uint8_t payload[128];
 if(discard_remaining){uint16_t n=discard_remaining<128?discard_remaining:128;if(bytes>=n){wiz_recv_data(0,payload,n);discard_remaining-=n;setSn_CR(0,Sn_CR_RECV);state=5;deadline=now+10;}}
 else if(bytes>=8){uint8_t h[8];wiz_recv_data(0,h,8);uint16_t len=(uint16_t)(h[6]<<8)|h[7];if(len==128&&bytes>=136){wiz_recv_data(0,payload,128);accept_frame(&app.stats[ETH_PORT],payload,128,now);}else{discard_remaining=len;app.stats[ETH_PORT].overflow++;}setSn_IR(0,Sn_IR_RECV);setSn_CR(0,Sn_CR_RECV);state=5;deadline=now+10;}}
 }
 if(state==4){frame_t *f=queue_peek(&app.tx[ETH_PORT]);uint16_t available;if(f&&stable_size(Sn_TX_FSR(0),&available)&&available>=128){uint8_t peer[4]={192,168,50,1};setSn_DIPR(0,peer);setSn_DPORT(0,5001);wiz_send_data(0,f->bytes,128);setSn_IR(0,(Sn_IR_SENDOK|Sn_IR_TIMEOUT));setSn_CR(0,Sn_CR_SEND);app.stats[ETH_PORT].tx++;state=6;deadline=now+50;}}
 }
 if(ethernet_spi_errors!=before)restart(now);
}
