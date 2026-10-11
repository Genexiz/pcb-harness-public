/* Register-level transport double; executes the untouched official CAN API. */
#include "drv_canfdspi_api.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static uint8_t registers[4096];
static int8_t transport_error;
void Nop(void){}
int8_t DRV_SPI_TransferData(uint8_t index,uint8_t *tx,uint8_t *rx,uint16_t n){
 assert(index<2&&n>=2&&n<=96);
 if(transport_error)return transport_error;
 unsigned address=((tx[0]&15)<<8)|tx[1];assert(address+n-2<=4096);
 if(tx[0]>>4==2)memcpy(registers+address,tx+2,n-2);
 else if(tx[0]>>4==3)memcpy(rx+2,registers+address,n-2);
 else assert(0);
 return 0;
}
int main(void){
 assert(DRV_CANFDSPI_BitTimeConfigure(0,CAN_500K_2M,CAN_SSP_MODE_AUTO,CAN_SYSCLK_20M)==0);
 REG_CiNBTCFG n;REG_CiDBTCFG d;REG_CiTDC t;
 memcpy(&n,registers+4,4);memcpy(&d,registers+8,4);memcpy(&t,registers+12,4);
 assert(n.bF.BRP==0&&n.bF.TSEG1==30&&n.bF.TSEG2==7&&n.bF.SJW==7);
 assert(d.bF.BRP==0&&d.bF.TSEG1==6&&d.bF.TSEG2==1&&d.bF.SJW==1);
 assert(t.bF.TDCMode==2&&t.bF.TDCOffset==7);
 assert(20000000u/((n.bF.BRP+1)*(n.bF.TSEG1+n.bF.TSEG2+3))==500000);
 assert(20000000u/((d.bF.BRP+1)*(d.bF.TSEG1+d.bF.TSEG2+3))==2000000);
 transport_error=-1;
 assert(DRV_CANFDSPI_BitTimeConfigure(0,CAN_500K_2M,CAN_SSP_MODE_AUTO,CAN_SYSCLK_20M)!=0);
 puts("official CAN registers transport error: passed");
}
