#include "board.h"
#include <string.h>
app_t app;
UART_HandleTypeDef uart[3];
SPI_HandleTypeDef spi1,spi2;
I2C_HandleTypeDef i2c;
static DMA_HandleTypeDef rx_dma[3],tx_dma[3];
static uint8_t rx_ring[3][256],rx_partial[PORTS][FRAME_MAX];
static uint16_t partial_len[PORTS];
static volatile uint32_t rx_wrap[3],rx_fault[3];
static uint32_t consumed[3],tx_deadline[3];
static volatile uint8_t tx_done[3],tx_active[3],i2c_done,i2c_failed;
static uint8_t i2c_phase, i2c_rx[32];
static uint32_t i2c_deadline, i2c_retry;
static bus_t shared_bus;
volatile uint32_t spi_faults;
volatile uint32_t i2c_irq_us_max;
static void gpio(GPIO_TypeDef *p,uint16_t pins,uint32_t mode){GPIO_InitTypeDef c={0};c.Pin=pins;c.Mode=mode;c.Speed=GPIO_SPEED_FREQ_HIGH;c.Pull=GPIO_NOPULL;HAL_GPIO_Init(p,&c);}
void fail_port(unsigned p){app.stats[p].timeout++;}
static void clock_init(void){
 RCC_OscInitTypeDef o={0}; RCC_ClkInitTypeDef c={0};
 o.OscillatorType=RCC_OSCILLATORTYPE_HSE;o.HSEState=RCC_HSE_BYPASS;o.PLL.PLLState=RCC_PLL_ON;o.PLL.PLLSource=RCC_PLLSOURCE_HSE;o.PLL.PLLMUL=RCC_PLL_MUL6;
 if(HAL_RCC_OscConfig(&o)!=HAL_OK)for(;;){} /* fatal clock fault: no false running status */
 c.ClockType=RCC_CLOCKTYPE_SYSCLK|RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;c.SYSCLKSource=RCC_SYSCLKSOURCE_PLLCLK;c.AHBCLKDivider=RCC_SYSCLK_DIV1;c.APB1CLKDivider=RCC_HCLK_DIV2;c.APB2CLKDivider=RCC_HCLK_DIV1;
 if(HAL_RCC_ClockConfig(&c,FLASH_LATENCY_1)!=HAL_OK)for(;;){}
 __HAL_RCC_USB_CONFIG(RCC_USBCLKSOURCE_PLL);
}
static void dma_init(unsigned i,DMA_Channel_TypeDef *rx,DMA_Channel_TypeDef *tx){
 rx_dma[i].Instance=rx;rx_dma[i].Init.Direction=DMA_PERIPH_TO_MEMORY;rx_dma[i].Init.PeriphInc=DMA_PINC_DISABLE;rx_dma[i].Init.MemInc=DMA_MINC_ENABLE;rx_dma[i].Init.PeriphDataAlignment=DMA_PDATAALIGN_BYTE;rx_dma[i].Init.MemDataAlignment=DMA_MDATAALIGN_BYTE;rx_dma[i].Init.Mode=DMA_CIRCULAR;rx_dma[i].Init.Priority=DMA_PRIORITY_HIGH;
 tx_dma[i].Instance=tx;tx_dma[i].Init=rx_dma[i].Init;tx_dma[i].Init.Direction=DMA_MEMORY_TO_PERIPH;tx_dma[i].Init.Mode=DMA_NORMAL;
 HAL_DMA_Init(&rx_dma[i]);HAL_DMA_Init(&tx_dma[i]);__HAL_LINKDMA(&uart[i],hdmarx,rx_dma[i]);__HAL_LINKDMA(&uart[i],hdmatx,tx_dma[i]);
}
/* ES096 analog-filter BUSY workaround. No driving a low SDA when SCL is stuck. */
#define SETTLE() do {uint32_t mark=DWT->CYCCNT;while((uint32_t)(DWT->CYCCNT-mark)<5*(SystemCoreClock/1000000)){} } while(0)
static bool i2c_bus_recover(void){
 __HAL_I2C_DISABLE(&i2c);gpio(GPIOB,GPIO_PIN_6|GPIO_PIN_7,GPIO_MODE_OUTPUT_OD);
 HAL_GPIO_WritePin(GPIOB,GPIO_PIN_6|GPIO_PIN_7,GPIO_PIN_SET);
 SETTLE();
 if((GPIOB->IDR&(GPIO_PIN_6|GPIO_PIN_7))!=(GPIO_PIN_6|GPIO_PIN_7))goto bad;
 HAL_GPIO_WritePin(GPIOB,GPIO_PIN_7,GPIO_PIN_RESET);SETTLE();if(GPIOB->IDR&GPIO_PIN_7)goto bad;
 HAL_GPIO_WritePin(GPIOB,GPIO_PIN_6,GPIO_PIN_RESET);SETTLE();if(GPIOB->IDR&GPIO_PIN_6)goto bad;
 HAL_GPIO_WritePin(GPIOB,GPIO_PIN_6,GPIO_PIN_SET);SETTLE();if(!(GPIOB->IDR&GPIO_PIN_6))goto bad;
 HAL_GPIO_WritePin(GPIOB,GPIO_PIN_7,GPIO_PIN_SET);SETTLE();if(!(GPIOB->IDR&GPIO_PIN_7))goto bad;
 gpio(GPIOB,GPIO_PIN_6|GPIO_PIN_7,GPIO_MODE_AF_OD);SET_BIT(i2c.Instance->CR1,I2C_CR1_SWRST);CLEAR_BIT(i2c.Instance->CR1,I2C_CR1_SWRST);return HAL_I2C_Init(&i2c)==HAL_OK;
bad:
 HAL_GPIO_WritePin(GPIOB,GPIO_PIN_6|GPIO_PIN_7,GPIO_PIN_SET);gpio(GPIOB,GPIO_PIN_6|GPIO_PIN_7,GPIO_MODE_AF_OD);return false;
}
void board_init(void){
 /* ES0962.2.9: newGNU development supported only onY/1 or later
    equivalent0x2003 silicon. Ordering/package marking still needs M5 review. */
 if((DBGMCU->IDCODE>>16)!=0x2003)for(;;){}
 HAL_Init();clock_init();__HAL_RCC_AFIO_CLK_ENABLE();__HAL_AFIO_REMAP_SWJ_NOJTAG();__HAL_RCC_GPIOA_CLK_ENABLE();__HAL_RCC_GPIOB_CLK_ENABLE();__HAL_RCC_GPIOC_CLK_ENABLE();__HAL_RCC_DMA1_CLK_ENABLE();__HAL_RCC_USART1_CLK_ENABLE();__HAL_RCC_USART2_CLK_ENABLE();__HAL_RCC_USART3_CLK_ENABLE();__HAL_RCC_SPI1_CLK_ENABLE();__HAL_RCC_SPI2_CLK_ENABLE();__HAL_RCC_I2C1_CLK_ENABLE();
 HAL_GPIO_WritePin(GPIOA,GPIO_PIN_4|GPIO_PIN_8,GPIO_PIN_SET);HAL_GPIO_WritePin(GPIOB,GPIO_PIN_9|GPIO_PIN_12,GPIO_PIN_SET);HAL_GPIO_WritePin(GPIOA,GPIO_PIN_1,GPIO_PIN_RESET);HAL_GPIO_WritePin(GPIOB,GPIO_PIN_5,GPIO_PIN_RESET);
 gpio(GPIOA,GPIO_PIN_4|GPIO_PIN_8|GPIO_PIN_1,GPIO_MODE_OUTPUT_PP);gpio(GPIOB,GPIO_PIN_9|GPIO_PIN_12|GPIO_PIN_5,GPIO_MODE_OUTPUT_PP);
 gpio(GPIOA,GPIO_PIN_0|GPIO_PIN_3|GPIO_PIN_10|GPIO_PIN_6,GPIO_MODE_INPUT);gpio(GPIOB,GPIO_PIN_11|GPIO_PIN_14,GPIO_MODE_INPUT);gpio(GPIOC,GPIO_PIN_13,GPIO_MODE_INPUT);
 gpio(GPIOB,GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_8,GPIO_MODE_IT_FALLING);HAL_NVIC_SetPriority(EXTI0_IRQn,3,0);HAL_NVIC_EnableIRQ(EXTI0_IRQn);HAL_NVIC_SetPriority(EXTI1_IRQn,3,0);HAL_NVIC_EnableIRQ(EXTI1_IRQn);HAL_NVIC_SetPriority(EXTI9_5_IRQn,3,0);HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
 gpio(GPIOA,GPIO_PIN_2|GPIO_PIN_9|GPIO_PIN_5|GPIO_PIN_7,GPIO_MODE_AF_PP);gpio(GPIOB,GPIO_PIN_10|GPIO_PIN_13|GPIO_PIN_15,GPIO_MODE_AF_PP);gpio(GPIOB,GPIO_PIN_6|GPIO_PIN_7,GPIO_MODE_AF_OD);
 USART_TypeDef *instances[3]={USART1,USART2,USART3};
 for(unsigned i=0;i<3;i++){uart[i].Instance=instances[i];uart[i].Init.BaudRate=115200;uart[i].Init.WordLength=UART_WORDLENGTH_8B;uart[i].Init.StopBits=UART_STOPBITS_1;uart[i].Init.Parity=UART_PARITY_NONE;uart[i].Init.Mode=UART_MODE_TX_RX;uart[i].Init.HwFlowCtl=UART_HWCONTROL_NONE;uart[i].Init.OverSampling=UART_OVERSAMPLING_16;HAL_UART_Init(&uart[i]);}
 dma_init(0,DMA1_Channel5,DMA1_Channel4);dma_init(1,DMA1_Channel6,DMA1_Channel7);dma_init(2,DMA1_Channel3,DMA1_Channel2);
 for(unsigned i=0;i<3;i++)HAL_UART_Receive_DMA(&uart[i],rx_ring[i],256);
 for(int irq=DMA1_Channel2_IRQn;irq<=DMA1_Channel7_IRQn;irq++){HAL_NVIC_SetPriority((IRQn_Type)irq,2,0);HAL_NVIC_EnableIRQ((IRQn_Type)irq);}
 for(int irq=USART1_IRQn;irq<=USART3_IRQn;irq++){HAL_NVIC_SetPriority((IRQn_Type)irq,2,0);HAL_NVIC_EnableIRQ((IRQn_Type)irq);}
 spi1.Instance=SPI1;spi1.Init.Mode=SPI_MODE_MASTER;spi1.Init.Direction=SPI_DIRECTION_2LINES;spi1.Init.DataSize=SPI_DATASIZE_8BIT;spi1.Init.CLKPolarity=SPI_POLARITY_LOW;spi1.Init.CLKPhase=SPI_PHASE_1EDGE;spi1.Init.NSS=SPI_NSS_SOFT;spi1.Init.BaudRatePrescaler=SPI_BAUDRATEPRESCALER_8;spi1.Init.FirstBit=SPI_FIRSTBIT_MSB;spi1.Init.TIMode=SPI_TIMODE_DISABLE;spi1.Init.CRCCalculation=SPI_CRCCALCULATION_DISABLE;HAL_SPI_Init(&spi1);
 spi2.Instance=SPI2;spi2.Init=spi1.Init;spi2.Init.BaudRatePrescaler=SPI_BAUDRATEPRESCALER_4;HAL_SPI_Init(&spi2);
 /* DWT deadlines keep SPI waits bounded even if tick interrupt is delayed. */
 CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;DWT->CYCCNT=0;DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
 i2c.Instance=I2C1;i2c.Init.ClockSpeed=100000;i2c.Init.DutyCycle=I2C_DUTYCYCLE_2;i2c.Init.AddressingMode=I2C_ADDRESSINGMODE_7BIT;i2c.Init.DualAddressMode=I2C_DUALADDRESS_DISABLE;i2c.Init.GeneralCallMode=I2C_GENERALCALL_DISABLE;i2c.Init.NoStretchMode=I2C_NOSTRETCH_DISABLE;HAL_I2C_Init(&i2c);i2c_bus_recover();
 /* ES0962.8.1: I2C event/error handlers share highest preemption priority.
    No active IRQ may interrupt byte-sensitive sequences; no DMA channel clash. */
 HAL_NVIC_SetPriority(I2C1_EV_IRQn,0,0);HAL_NVIC_EnableIRQ(I2C1_EV_IRQn);HAL_NVIC_SetPriority(I2C1_ER_IRQn,0,0);HAL_NVIC_EnableIRQ(I2C1_ER_IRQn);
}
void receive_bytes(unsigned p,const uint8_t *data,unsigned n,uint32_t now){if(p<PORTS)feed_frames(&app.stats[p],rx_partial[p],&partial_len[p],data,n,frame_length[p],now);}
void serial_service(uint32_t now){for(unsigned i=0;i<3;i++){
 unsigned p=i+1;uint32_t key=__get_PRIMASK();__disable_irq();uint32_t wraps=rx_wrap[i];uint32_t before=__HAL_DMA_GET_FLAG(&rx_dma[i],__HAL_DMA_GET_TC_FLAG_INDEX(&rx_dma[i]));uint32_t remain=__HAL_DMA_GET_COUNTER(&rx_dma[i]);uint32_t tc=__HAL_DMA_GET_FLAG(&rx_dma[i],__HAL_DMA_GET_TC_FLAG_INDEX(&rx_dma[i]));if(tc!=before)remain=__HAL_DMA_GET_COUNTER(&rx_dma[i]);__set_PRIMASK(key);
 uint32_t head=dma_produced(wraps,remain,tc!=0),available=head-consumed[i];
 if(available>256){app.stats[p].overflow+=available-256;consumed[i]=head-256;partial_len[p]=0;available=256;}
 unsigned quota=available<64?available:64;while(quota){unsigned offset=consumed[i]%256,run=256-offset;if(run>quota)run=quota;if(i!=1||!tx_active[i]||tx_done[i])receive_bytes(p,rx_ring[i]+offset,run,now);consumed[i]+=run;quota-=run;}
 if(rx_fault[i]){app.stats[p].overflow+=rx_fault[i];rx_fault[i]=0;HAL_UART_AbortReceive(&uart[i]);rx_wrap[i]=0;consumed[i]=0;partial_len[p]=0;HAL_UART_Receive_DMA(&uart[i],rx_ring[i],256);}
 if(tx_active[i]){if(tx_done[i]){tx_done[i]=0;tx_active[i]=0;queue_pop(&app.tx[p]);app.stats[p].tx_complete++;}else if((int32_t)(now-tx_deadline[i])>=0){HAL_UART_AbortTransmit(&uart[i]);if(i==1)HAL_GPIO_WritePin(GPIOA,GPIO_PIN_1,GPIO_PIN_RESET);tx_active[i]=0;queue_pop(&app.tx[p]);fail_port(p);}}
 frame_t *f=queue_peek(&app.tx[p]);if(!tx_active[i]&&f){if(i==1)HAL_GPIO_WritePin(GPIOA,GPIO_PIN_1,GPIO_PIN_SET);if(HAL_UART_Transmit_DMA(&uart[i],f->bytes,f->len)==HAL_OK){tx_active[i]=1;tx_deadline[i]=now+10;app.stats[p].tx++;}else{if(i==1)HAL_GPIO_WritePin(GPIOA,GPIO_PIN_1,GPIO_PIN_RESET);fail_port(p);}}
 app.stats[p].service++;
}}
void i2c_service(uint32_t now){
 app.stats[I2C_PORT].service++;
 if(i2c_phase&&(i2c_failed||(int32_t)(now-i2c_deadline)>=0)){
 /* Reset immediately instead of HAL blocking abort waits on a stuck bus. */
 __HAL_I2C_DISABLE_IT(&i2c,I2C_IT_EVT|I2C_IT_BUF|I2C_IT_ERR);i2c_bus_recover();i2c_phase=0;i2c_failed=0;queue_pop(&app.tx[I2C_PORT]);fail_port(I2C_PORT);i2c_retry=now+100;
 }
 if(i2c_phase==1&&i2c_done){i2c_done=0;i2c_phase=2;if(HAL_I2C_Master_Receive_IT(&i2c,0x42<<1,i2c_rx,32)!=HAL_OK)i2c_failed=1;}
 if(i2c_phase==2&&i2c_done){i2c_done=0;i2c_phase=0;accept_frame(&app.stats[I2C_PORT],i2c_rx,32,now);queue_pop(&app.tx[I2C_PORT]);app.stats[I2C_PORT].tx_complete++;}
 frame_t *f=queue_peek(&app.tx[I2C_PORT]);if(!i2c_phase&&f&&(int32_t)(now-i2c_retry)>=0){
 if(HAL_I2C_Master_Transmit_IT(&i2c,0x42<<1,f->bytes,32)==HAL_OK){i2c_phase=1;i2c_done=0;i2c_deadline=now+8;app.stats[I2C_PORT].tx++;}else{fail_port(I2C_PORT);i2c_bus_recover();i2c_retry=now+100;}}
}
/* Byte/register waits bounded by a whole transaction DWT deadline, not N*timeout. */
bool spi_transfer(unsigned owner,const uint8_t *tx,uint8_t *rx,uint16_t n){
 uint32_t hz=owner==3?750000:6000000;
 if(!bus_begin(&shared_bus,owner,hz,n))return false;
 HAL_GPIO_WritePin(GPIOA,GPIO_PIN_4|GPIO_PIN_8,GPIO_PIN_SET);HAL_GPIO_WritePin(GPIOB,GPIO_PIN_9,GPIO_PIN_SET);
 __HAL_SPI_DISABLE(&spi1);MODIFY_REG(SPI1->CR1,SPI_CR1_BR,owner==3?SPI_BAUDRATEPRESCALER_64:SPI_BAUDRATEPRESCALER_8);__HAL_SPI_ENABLE(&spi1);
 GPIO_TypeDef *port=owner==3?GPIOB:GPIOA;uint16_t pin=owner==1?GPIO_PIN_4:owner==2?GPIO_PIN_8:GPIO_PIN_9;
 HAL_GPIO_WritePin(port,pin,GPIO_PIN_RESET);uint32_t start=DWT->CYCCNT;uint32_t limit=(wire_us(n,hz)+750)*(SystemCoreClock/1000000);bool ok=true;
 for(unsigned i=0;i<n;i++){
 while(!(SPI1->SR&SPI_SR_TXE)){if((uint32_t)(DWT->CYCCNT-start)>limit){ok=false;goto out;}}
 *(__IO uint8_t *)&SPI1->DR=tx?tx[i]:0xff;
 while(!(SPI1->SR&SPI_SR_RXNE)){if((uint32_t)(DWT->CYCCNT-start)>limit){ok=false;goto out;}}
 uint8_t b=*(__IO uint8_t *)&SPI1->DR;if(rx)rx[i]=b;
 }
 while(SPI1->SR&SPI_SR_BSY){if((uint32_t)(DWT->CYCCNT-start)>limit){ok=false;break;}}
out:
 HAL_GPIO_WritePin(port,pin,GPIO_PIN_SET);bus_end(&shared_bus);if(!ok){spi_faults++;__HAL_SPI_DISABLE(&spi1);__HAL_RCC_SPI1_FORCE_RESET();__HAL_RCC_SPI1_RELEASE_RESET();HAL_SPI_Init(&spi1);}return ok;
}
void external_spi_service(uint32_t now){(void)now;app.stats[SPI_PORT].service++;frame_t *f=queue_peek(&app.tx[SPI_PORT]);if(!f)return;uint8_t r[64];if(spi_transfer(3,f->bytes,r,64)){accept_frame(&app.stats[SPI_PORT],r,64,now);app.stats[SPI_PORT].tx++;app.stats[SPI_PORT].tx_complete++;}else fail_port(SPI_PORT);queue_pop(&app.tx[SPI_PORT]);}
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *h){for(unsigned i=0;i<3;i++)if(h==&uart[i]){if(i==1)HAL_GPIO_WritePin(GPIOA,GPIO_PIN_1,GPIO_PIN_RESET);tx_done[i]=1;}}
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *h){for(unsigned i=0;i<3;i++)if(h==&uart[i])rx_wrap[i]++;}
void HAL_UART_ErrorCallback(UART_HandleTypeDef *h){for(unsigned i=0;i<3;i++)if(h==&uart[i])rx_fault[i]++;}
void HAL_I2C_MasterTxCpltCallback(I2C_HandleTypeDef *h){(void)h;i2c_done=1;}
void HAL_I2C_MasterRxCpltCallback(I2C_HandleTypeDef *h){(void)h;i2c_done=1;}
void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *h){(void)h;i2c_failed=1;}
void SysTick_Handler(void){HAL_IncTick();HAL_SYSTICK_IRQHandler();}
void DMA1_Channel2_IRQHandler(void){HAL_DMA_IRQHandler(&tx_dma[2]);}
void DMA1_Channel3_IRQHandler(void){HAL_DMA_IRQHandler(&rx_dma[2]);}
void DMA1_Channel4_IRQHandler(void){HAL_DMA_IRQHandler(&tx_dma[0]);}
void DMA1_Channel5_IRQHandler(void){HAL_DMA_IRQHandler(&rx_dma[0]);}
void DMA1_Channel6_IRQHandler(void){HAL_DMA_IRQHandler(&rx_dma[1]);}
void DMA1_Channel7_IRQHandler(void){HAL_DMA_IRQHandler(&tx_dma[1]);}
void USART1_IRQHandler(void){HAL_UART_IRQHandler(&uart[0]);}
void USART2_IRQHandler(void){HAL_UART_IRQHandler(&uart[1]);}
void USART3_IRQHandler(void){HAL_UART_IRQHandler(&uart[2]);}
void I2C1_EV_IRQHandler(void){uint32_t mark=DWT->CYCCNT;HAL_I2C_EV_IRQHandler(&i2c);uint32_t us=(DWT->CYCCNT-mark)/(SystemCoreClock/1000000);if(us>i2c_irq_us_max)i2c_irq_us_max=us;}
void I2C1_ER_IRQHandler(void){uint32_t mark=DWT->CYCCNT;HAL_I2C_ER_IRQHandler(&i2c);uint32_t us=(DWT->CYCCNT-mark)/(SystemCoreClock/1000000);if(us>i2c_irq_us_max)i2c_irq_us_max=us;}
void EXTI0_IRQHandler(void){HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_0);}
void EXTI1_IRQHandler(void){HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_1);}
void EXTI9_5_IRQHandler(void){HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_8);}
