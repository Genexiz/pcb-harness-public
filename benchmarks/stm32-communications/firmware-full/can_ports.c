#include "drv_canfdspi_api.h"
#include "board.h"
/* Shared upstream API scratch buffers: main loop only, never ISR/reentrant. */
static struct { uint8_t stage;uint16_t ram_offset;uint32_t deadline,next_service,next_diag; } controller[2];
volatile uint32_t can_rx_timestamp[2],can_tx_timestamp[2],can_error_state[2],can_spi_crc_error[2],can_ecc_error[2];
int8_t DRV_SPI_TransferData(uint8_t index,uint8_t *tx,uint8_t *rx,uint16_t n){return index<2&&spi_transfer(index+1,tx,rx,n)?0:-1;}
static void retry(unsigned i,uint32_t now){controller[i].stage=0;controller[i].deadline=now+100;fail_port(CAN_PORT+i);}
static bool initialize_step(unsigned i,uint32_t now){
 unsigned p=CAN_PORT+i;int8_t error=0;bool fd=i!=0;
 if(controller[i].stage==0){if((int32_t)(now-controller[i].deadline)<0)return false;error=DRV_CANFDSPI_Reset(i);controller[i].deadline=now+100;controller[i].stage=1;}
 else if(controller[i].stage==1){CAN_OSC_STATUS s={0};error=DRV_CANFDSPI_OscillatorStatusGet(i,&s);if(!error&&s.OscReady){error=DRV_CANFDSPI_EccEnable(i);controller[i].ram_offset=0;controller[i].stage=2;}else if((int32_t)(now-controller[i].deadline)>=0)error=-1;}
 else if(controller[i].stage==2){
 /* Exactly 2048 bytes initialized, 32 bounded 64-byte CRC-protected writes.
    Upstream RamInit's 96-byte buffer division leaves a remainder: do not use it. */
 uint8_t zero[64]={0};error=DRV_CANFDSPI_WriteByteArrayWithCRC(i,cRAMADDR_START+controller[i].ram_offset,zero,64,true);
 controller[i].ram_offset+=64;if(controller[i].ram_offset==2048)controller[i].stage=3;
 }
 else if(controller[i].stage==3){CAN_CONFIG c;DRV_CANFDSPI_ConfigureObjectReset(&c);c.IsoCrcEnable=1;c.StoreInTEF=1;c.RestrictReTxAttempts=1;c.BitRateSwitchDisable=!fd;c.TXQEnable=0;error=DRV_CANFDSPI_Configure(i,&c);controller[i].stage++;}
 else if(controller[i].stage==4){CAN_TEF_CONFIG c;DRV_CANFDSPI_TefConfigureObjectReset(&c);c.FifoSize=7;c.TimeStampEnable=1;error=DRV_CANFDSPI_TefConfigure(i,&c);controller[i].stage++;}
 else if(controller[i].stage==5){CAN_TX_FIFO_CONFIG c;DRV_CANFDSPI_TransmitChannelConfigureObjectReset(&c);c.FifoSize=7;c.PayLoadSize=fd?CAN_PLSIZE_64:CAN_PLSIZE_8;c.TxAttempts=1;c.TxPriority=1;error=DRV_CANFDSPI_TransmitChannelConfigure(i,CAN_FIFO_CH1,&c);controller[i].stage++;}
 else if(controller[i].stage==6){CAN_RX_FIFO_CONFIG c;DRV_CANFDSPI_ReceiveChannelConfigureObjectReset(&c);c.FifoSize=7;c.PayLoadSize=fd?CAN_PLSIZE_64:CAN_PLSIZE_8;c.RxTimeStampEnable=1;error=DRV_CANFDSPI_ReceiveChannelConfigure(i,CAN_FIFO_CH2,&c);controller[i].stage++;}
 else if(controller[i].stage==7){REG_CiFLTOBJ f={0};f.bF.SID=0x600+i;REG_CiMASK m={0};m.bF.MSID=0x7ff;m.bF.MIDE=1;error=DRV_CANFDSPI_FilterObjectConfigure(i,CAN_FILTER0,&f.bF);if(!error)error=DRV_CANFDSPI_FilterMaskConfigure(i,CAN_FILTER0,&m.bF);if(!error)error=DRV_CANFDSPI_FilterToFifoLink(i,CAN_FILTER0,CAN_FIFO_CH2,true);controller[i].stage++;}
 else if(controller[i].stage==8){error=DRV_CANFDSPI_BitTimeConfigure(i,CAN_500K_2M,CAN_SSP_MODE_AUTO,CAN_SYSCLK_20M);controller[i].stage++;}
 else if(controller[i].stage==9){error=DRV_CANFDSPI_TimeStampPrescalerSet(i,19);if(!error)error=DRV_CANFDSPI_TimeStampEnable(i);if(!error)error=DRV_CANFDSPI_GpioModeConfigure(i,GPIO_MODE_INT,GPIO_MODE_INT);controller[i].stage++;}
 else if(controller[i].stage==10){error=DRV_CANFDSPI_ReceiveChannelEventEnable(i,CAN_FIFO_CH2,CAN_RX_FIFO_NOT_EMPTY_EVENT|CAN_RX_FIFO_OVERFLOW_EVENT);if(!error)error=DRV_CANFDSPI_ModuleEventEnable(i,CAN_RX_EVENT|CAN_TEF_EVENT|CAN_TX_ATTEMPTS_EVENT|CAN_SYSTEM_ERROR_EVENT);if(!error)error=DRV_CANFDSPI_CrcEventEnable(i,CAN_CRC_ALL_EVENTS);if(!error)error=DRV_CANFDSPI_EccEventEnable(i,CAN_ECC_ALL_EVENTS);controller[i].stage++;}
 else if(controller[i].stage==11){error=DRV_CANFDSPI_OperationModeSelect(i,fd?CAN_NORMAL_MODE:CAN_CLASSIC_MODE);controller[i].stage++;controller[i].deadline=now+20;}
 else if(controller[i].stage==12){CAN_OPERATION_MODE m=DRV_CANFDSPI_OperationModeGet(i);if(m==(fd?CAN_NORMAL_MODE:CAN_CLASSIC_MODE)){controller[i].stage++;app.stats[p].service++;}else if((int32_t)(now-controller[i].deadline)>=0)error=-1;}
 if(error)retry(i,now);return controller[i].stage==13;
}
void can_service(uint32_t now){for(unsigned i=0;i<2;i++){
 unsigned p=CAN_PORT+i;if((int32_t)(now-controller[i].next_service)<0)continue;controller[i].next_service=now+1;app.stats[p].service++;
 if(controller[i].stage!=13){initialize_step(i,now);continue;}
 uint32_t faults_before=spi_faults;int8_t error=0;CAN_RX_FIFO_EVENT r;
 error=DRV_CANFDSPI_ReceiveChannelEventGet(i,CAN_FIFO_CH2,&r);
 if(!error&&(r&CAN_RX_FIFO_OVERFLOW_EVENT)){app.stats[p].overflow++;error=DRV_CANFDSPI_ReceiveChannelEventOverflowClear(i,CAN_FIFO_CH2);}
 if(!error&&(r&CAN_RX_FIFO_NOT_EMPTY_EVENT)){CAN_RX_MSGOBJ obj;uint8_t bytes[64];error=DRV_CANFDSPI_ReceiveMessageGet(i,CAN_FIFO_CH2,&obj,bytes,frame_length[p]);if(!error){can_rx_timestamp[i]=obj.bF.timeStamp;if(obj.bF.id.SID!=0x600+i||obj.bF.ctrl.FDF!=(i!=0)||obj.bF.ctrl.DLC!=(i?CAN_DLC_64:CAN_DLC_8))app.stats[p].crc_error++;else accept_frame(&app.stats[p],bytes,frame_length[p],now);}}
 CAN_TEF_FIFO_EVENT tef;if(!error)error=DRV_CANFDSPI_TefEventGet(i,&tef);
 if(!error&&(tef&CAN_TEF_FIFO_OVERFLOW_EVENT)){app.stats[p].overflow++;error=DRV_CANFDSPI_TefEventOverflowClear(i);}
 if(!error&&(tef&CAN_TEF_FIFO_NOT_EMPTY_EVENT)){CAN_TEF_MSGOBJ e;error=DRV_CANFDSPI_TefMessageGet(i,&e);if(!error){can_tx_timestamp[i]=e.bF.timeStamp;app.stats[p].tx_complete++;}}
 frame_t *f=queue_peek(&app.tx[p]);if(!error&&f){CAN_TX_FIFO_EVENT t;error=DRV_CANFDSPI_TransmitChannelEventGet(i,CAN_FIFO_CH1,&t);if(!error&&(t&CAN_TX_FIFO_ATTEMPTS_EXHAUSTED_EVENT)){fail_port(p);error=DRV_CANFDSPI_TransmitChannelEventAttemptClear(i,CAN_FIFO_CH1);if(!error)error=DRV_CANFDSPI_TransmitChannelReset(i,CAN_FIFO_CH1);}
 if(!error&&(t&CAN_TX_FIFO_NOT_FULL_EVENT)){CAN_TX_MSGOBJ obj={0};obj.bF.id.SID=0x600+i;obj.bF.ctrl.DLC=i?CAN_DLC_64:CAN_DLC_8;obj.bF.ctrl.BRS=i!=0;obj.bF.ctrl.FDF=i!=0;obj.bF.ctrl.SEQ=app.stats[p].tx;error=DRV_CANFDSPI_TransmitChannelLoad(i,CAN_FIFO_CH1,&obj,f->bytes,f->len,true);if(!error){app.stats[p].tx++;queue_pop(&app.tx[p]);}}}
 if(!error&&(int32_t)(now-controller[i].next_diag)>=0){uint8_t tx,rx;CAN_ERROR_STATE flags;error=DRV_CANFDSPI_ErrorCountStateGet(i,&tx,&rx,&flags);can_error_state[i]=((uint32_t)tx<<16)|((uint32_t)rx<<8)|flags;if(flags&CAN_TX_BUS_OFF_STATE)error=-1;
 CAN_CRC_EVENT crc;if(!error)error=DRV_CANFDSPI_CrcEventGet(i,&crc);if(!error&&crc){can_spi_crc_error[i]++;DRV_CANFDSPI_CrcEventClear(i,crc);}
 CAN_ECC_EVENT ecc;if(!error)error=DRV_CANFDSPI_EccEventGet(i,&ecc);if(!error&&ecc){can_ecc_error[i]++;DRV_CANFDSPI_EccEventClear(i,ecc);}
 controller[i].next_diag=now+100;}
 if(error||spi_faults!=faults_before)retry(i,now);
}}
