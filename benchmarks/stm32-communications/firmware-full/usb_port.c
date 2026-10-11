/* Board adapter for original STM32 USB Device middleware (ST SLA0044).
 * Original vendor code and license notice remain under vendor/usb. */
#include "board.h"
#include "usbd_core.h"
#include "usbd_cdc.h"
#include "usbd_ctlreq.h"
static USBD_HandleTypeDef usb;
static PCD_HandleTypeDef pcd;
static USBD_CDC_HandleTypeDef class_storage;
static uint8_t class_used, connected, tx_pending;
static uint8_t ep_rx[64],ring[256];
static volatile uint32_t write_pos,usb_overflow;
static volatile uint32_t read_pos;
static uint32_t tx_limit,report_due,faults_seen,restart_due;
static volatile uint32_t usb_reset_events,usb_suspend_events,usb_irq_us_max;
static uint8_t report_port;
void *usb_class_alloc(uint32_t n){if(class_used||n>sizeof(class_storage))return 0;class_used=1;return &class_storage;}
void usb_class_free(void *p){if(p==&class_storage)class_used=0;}
/* Experimental VID/PID only; replace before shipping with legitimately assigned IDs. */
static uint8_t device_desc[18]={18,USB_DESC_TYPE_DEVICE,0,2,2,0,0,64,0x83,0x04,0x40,0x57,0,1,1,2,3,1};
static uint8_t lang_desc[4]={4,USB_DESC_TYPE_STRING,9,4},string_desc[128];
static uint8_t *dev(USBD_SpeedTypeDef s,uint16_t *n){(void)s;*n=18;return device_desc;}
static uint8_t *lang(USBD_SpeedTypeDef s,uint16_t *n){(void)s;*n=4;return lang_desc;}
static uint8_t *str(const char *s,uint16_t *n){USBD_GetString((uint8_t *)s,string_desc,n);return string_desc;}
static uint8_t *manufacturer(USBD_SpeedTypeDef s,uint16_t *n){(void)s;return str("PCB Harness experimental",n);}
static uint8_t *product(USBD_SpeedTypeDef s,uint16_t *n){(void)s;return str("Nine interface test",n);}
static uint8_t *serial(USBD_SpeedTypeDef s,uint16_t *n){(void)s;return str("M4-TEST-0001",n);}
static uint8_t *configuration(USBD_SpeedTypeDef s,uint16_t *n){(void)s;return str("Self powered CDC",n);}
static uint8_t *interface(USBD_SpeedTypeDef s,uint16_t *n){(void)s;return str("CRC sequence stream",n);}
static USBD_DescriptorsTypeDef descriptors={dev,lang,manufacturer,product,serial,configuration,interface};
static int8_t cdc_init(void){USBD_CDC_SetRxBuffer(&usb,ep_rx);USBD_CDC_SetTxBuffer(&usb,0,0);return USBD_OK;}
static int8_t cdc_deinit(void){return USBD_OK;}
static int8_t control(uint8_t cmd,uint8_t *p,uint16_t n){if(cmd==CDC_GET_LINE_CODING&&n>=7){const uint8_t v[7]={0,0xc2,1,0,0,0,8};memcpy(p,v,7);}return USBD_OK;}
static int8_t received(uint8_t *p,uint32_t *n){for(unsigned i=0;i<*n&&i<64;i++){if(write_pos-read_pos>=256)usb_overflow++;else ring[write_pos++%256]=p[i];}USBD_CDC_SetRxBuffer(&usb,ep_rx);USBD_CDC_ReceivePacket(&usb);return USBD_OK;}
static USBD_CDC_ItfTypeDef functions={cdc_init,cdc_deinit,control,received};
void HAL_PCD_MspInit(PCD_HandleTypeDef *h){if(h->Instance==USB){__HAL_RCC_USB_CLK_ENABLE();HAL_NVIC_SetPriority(USB_LP_CAN1_RX0_IRQn,1,0);HAL_NVIC_EnableIRQ(USB_LP_CAN1_RX0_IRQn);}}
void HAL_PCD_MspDeInit(PCD_HandleTypeDef *h){(void)h;HAL_NVIC_DisableIRQ(USB_LP_CAN1_RX0_IRQn);__HAL_RCC_USB_CLK_DISABLE();}
void USB_LP_CAN1_RX0_IRQHandler(void){uint32_t mark=DWT->CYCCNT;HAL_PCD_IRQHandler(&pcd);uint32_t us=(DWT->CYCCNT-mark)/(SystemCoreClock/1000000);if(us>usb_irq_us_max)usb_irq_us_max=us;}
void HAL_PCD_SetupStageCallback(PCD_HandleTypeDef *h){USBD_LL_SetupStage(h->pData,(uint8_t *)h->Setup);}
void HAL_PCD_DataOutStageCallback(PCD_HandleTypeDef *h,uint8_t ep){USBD_LL_DataOutStage(h->pData,ep,h->OUT_ep[ep].xfer_buff);}
void HAL_PCD_DataInStageCallback(PCD_HandleTypeDef *h,uint8_t ep){USBD_LL_DataInStage(h->pData,ep,h->IN_ep[ep].xfer_buff);}
void HAL_PCD_SOFCallback(PCD_HandleTypeDef *h){USBD_LL_SOF(h->pData);}
void HAL_PCD_ResetCallback(PCD_HandleTypeDef *h){usb_reset_events++;USBD_LL_SetSpeed(h->pData,USBD_SPEED_FULL);USBD_LL_Reset(h->pData);}
void HAL_PCD_SuspendCallback(PCD_HandleTypeDef *h){usb_suspend_events++;USBD_LL_Suspend(h->pData);}
void HAL_PCD_ResumeCallback(PCD_HandleTypeDef *h){USBD_LL_Resume(h->pData);}
void HAL_PCD_ISOOUTIncompleteCallback(PCD_HandleTypeDef *h,uint8_t ep){USBD_LL_IsoOUTIncomplete(h->pData,ep);}
void HAL_PCD_ISOINIncompleteCallback(PCD_HandleTypeDef *h,uint8_t ep){USBD_LL_IsoINIncomplete(h->pData,ep);}
void HAL_PCD_ConnectCallback(PCD_HandleTypeDef *h){USBD_LL_DevConnected(h->pData);}
void HAL_PCD_DisconnectCallback(PCD_HandleTypeDef *h){USBD_LL_DevDisconnected(h->pData);}
void HAL_PCDEx_SetConnectionState(PCD_HandleTypeDef *h,uint8_t on){(void)h;GPIO_InitTypeDef g={0};g.Pin=GPIO_PIN_12;g.Speed=GPIO_SPEED_FREQ_LOW;g.Mode=on?GPIO_MODE_INPUT:GPIO_MODE_OUTPUT_OD;HAL_GPIO_WritePin(GPIOA,GPIO_PIN_12,GPIO_PIN_RESET);HAL_GPIO_Init(GPIOA,&g);}
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *p){pcd.Instance=USB;pcd.Init.dev_endpoints=8;pcd.Init.speed=PCD_SPEED_FULL;pcd.Init.ep0_mps=EP_MPS_64;pcd.Init.phy_itface=PCD_PHY_EMBEDDED;pcd.Init.low_power_enable=0;pcd.pData=p;p->pData=&pcd;if(HAL_PCD_Init(&pcd)!=HAL_OK)return USBD_FAIL;
 /* 512 byte PMA; BTABLE 0..63, EP0 OUT/IN64..191, CDC IN192..255,
    command IN256..271, CDC OUT272..335. No native bxCAN use. */
 HAL_PCDEx_PMAConfig(&pcd,0x00,PCD_SNG_BUF,0x40);HAL_PCDEx_PMAConfig(&pcd,0x80,PCD_SNG_BUF,0x80);HAL_PCDEx_PMAConfig(&pcd,CDC_IN_EP,PCD_SNG_BUF,0xc0);HAL_PCDEx_PMAConfig(&pcd,CDC_CMD_EP,PCD_SNG_BUF,0x100);HAL_PCDEx_PMAConfig(&pcd,CDC_OUT_EP,PCD_SNG_BUF,0x110);return USBD_OK;}
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef *p){return HAL_PCD_DeInit(p->pData)==HAL_OK?USBD_OK:USBD_FAIL;}
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *p){return HAL_PCD_Start(p->pData)==HAL_OK?USBD_OK:USBD_FAIL;}
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef *p){return HAL_PCD_Stop(p->pData)==HAL_OK?USBD_OK:USBD_FAIL;}
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *p,uint8_t ep,uint8_t type,uint16_t mps){return HAL_PCD_EP_Open(p->pData,ep,mps,type)==HAL_OK?USBD_OK:USBD_FAIL;}
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *p,uint8_t ep){HAL_PCD_EP_Close(p->pData,ep);return USBD_OK;}
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef *p,uint8_t ep){HAL_PCD_EP_Flush(p->pData,ep);return USBD_OK;}
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef *p,uint8_t ep){HAL_PCD_EP_SetStall(p->pData,ep);return USBD_OK;}
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef *p,uint8_t ep){HAL_PCD_EP_ClrStall(p->pData,ep);return USBD_OK;}
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef *p,uint8_t ep){PCD_HandleTypeDef *h=p->pData;return ep&0x80?h->IN_ep[ep&0x7f].is_stall:h->OUT_ep[ep].is_stall;}
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef *p,uint8_t addr){HAL_PCD_SetAddress(p->pData,addr);return USBD_OK;}
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *buf,uint16_t n){HAL_PCD_EP_Transmit(p->pData,ep,buf,n);return USBD_OK;}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *buf,uint16_t n){HAL_PCD_EP_Receive(p->pData,ep,buf,n);return USBD_OK;}
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *p,uint8_t ep){return HAL_PCD_EP_GetRxCount(p->pData,ep);}
void USBD_LL_Delay(uint32_t n){HAL_Delay(n);}
void usb_service(uint32_t now){
 bool vbus=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0)==GPIO_PIN_RESET; /* transistor detector is active LOW */
 app.stats[USB_PORT].service++;
 if(usb_driver_faults!=faults_seen){app.stats[USB_PORT].timeout+=usb_driver_faults-faults_seen;faults_seen=usb_driver_faults;USBD_Stop(&usb);USBD_DeInit(&usb);connected=0;if(tx_pending)queue_pop(&app.tx[0]);tx_pending=0;restart_due=now+100;}
 if(vbus&&!connected&&(int32_t)(now-restart_due)>=0){if(USBD_Init(&usb,&descriptors,0)==USBD_OK&&USBD_RegisterClass(&usb,&USBD_CDC)==USBD_OK&&USBD_CDC_RegisterInterface(&usb,&functions)==USBD_OK&&USBD_Start(&usb)==USBD_OK)connected=1;else{fail_port(USB_PORT);USBD_DeInit(&usb);restart_due=now+100;}}
 if(!vbus&&connected){USBD_Stop(&usb);USBD_DeInit(&usb);connected=0;tx_pending=0;read_pos=write_pos;}
 if(usb_overflow){uint32_t key=__get_PRIMASK();__disable_irq();app.stats[USB_PORT].overflow+=usb_overflow;usb_overflow=0;__set_PRIMASK(key);}
 uint32_t available=write_pos-read_pos;unsigned quota=available<64?available:64;while(quota){unsigned offset=read_pos%256,run=256-offset;if(run>quota)run=quota;receive_bytes(USB_PORT,ring+offset,run,now);read_pos+=run;quota-=run;}
 if(tx_pending){if(usb.dev_state==USBD_STATE_SUSPENDED)tx_limit=now+50;else if(usb.pClassData&&class_storage.TxState==0){queue_pop(&app.tx[USB_PORT]);app.stats[USB_PORT].tx_complete++;tx_pending=0;}else if((int32_t)(now-tx_limit)>=0){USBD_Stop(&usb);USBD_DeInit(&usb);connected=0;queue_pop(&app.tx[USB_PORT]);tx_pending=0;fail_port(USB_PORT);restart_due=now+100;}}
 if((int32_t)(now-report_due)>=0){frame_t f;make_telemetry(&f,app.stats[0].next++,now,report_port,&app.stats[report_port]);uint32_t diagnostics[10]={usb_driver_faults,scheduler_tick_overruns,scheduler_us_max,spi_faults,usb_reset_events,usb_suspend_events,usb_irq_us_max,i2c_irq_us_max,now,stack_high_water_bytes};memcpy(f.bytes+48,diagnostics,40);uint16_t c=crc16(f.bytes,126);f.bytes[126]=c;f.bytes[127]=c>>8;queue_push(&app.tx[0],&f,&app.stats[0]);report_port=(report_port+1)%PORTS;report_due=now+100;}
 frame_t *f=queue_peek(&app.tx[0]);if(connected&&usb.dev_state==USBD_STATE_CONFIGURED&&!tx_pending&&f){USBD_CDC_SetTxBuffer(&usb,f->bytes,f->len);if(USBD_CDC_TransmitPacket(&usb)==USBD_OK){tx_pending=1;tx_limit=now+50;app.stats[0].tx++;}}
}
