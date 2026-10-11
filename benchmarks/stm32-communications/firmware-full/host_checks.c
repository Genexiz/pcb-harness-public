#include "core.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
 assert(crc16((const uint8_t *)"123456789",9)==0x29b1);
 frame_t f={0}, g={0}; counters_t s={0};
 assert(!make_frame(&f,5,0,0,0)); assert(!make_frame(&f,129,0,0,0));
 assert(make_frame(&f,8,65535,65530,6)); assert(accept_frame(&s,f.bytes,8,65536));
 assert(s.rx==1 && s.latency_ms_max==6 && s.expected==0);
 assert(make_frame(&g,8,1,2,6)); assert(accept_frame(&s,g.bytes,8,3)); assert(s.lost==1);
 assert(accept_frame(&s,g.bytes,8,4)); assert(s.reorder==1);
 f.bytes[4]^=1; assert(!accept_frame(&s,f.bytes,8,65536)); assert(s.crc_error==1);
 queue_t q={0}; assert(queue_push(&q,&g,&s)); assert(queue_push(&q,&g,&s));
 assert(!queue_push(&q,&g,&s)); assert(s.overflow==1 && q.count==2);
 assert(queue_peek(&q)->bytes[0]==1); queue_pop(&q); queue_pop(&q); assert(!queue_peek(&q));
 bus_t b={0}; assert(!bus_begin(&b,3,1000001,64)); assert(!bus_begin(&b,3,500000,65));
 assert(bus_begin(&b,3,562500,64)); assert(!bus_begin(&b,1,9000000,8)); bus_end(&b);
 assert(bus_begin(&b,1,9000000,74)); bus_end(&b); assert(b.owner==0);
 assert(wire_us(64,500000)==1024); assert(wire_us(92,9000000)==82);
 /* Payload envelope and half-duplex receive turn must fit real wire time. */
 assert((uint32_t)frame_length[USB_PORT]*8000/period_ms[USB_PORT]>=128000);
 assert((uint32_t)frame_length[ETH_PORT]*8000/period_ms[ETH_PORT]>=128000);
 assert((uint32_t)frame_length[RS485_PORT]*20*1000<115200u*period_ms[RS485_PORT]);
 assert(dma_produced(0,255,true)==257);
 assert(dma_produced(4,0,true)==1280);
 assert(dma_produced(4,256,false)==1024);
 assert(dma_produced(0xffffff,255,true)==1); /* uint32 byte cursor rollover */
 counters_t telemetry={0};telemetry.rx=0x12345678;telemetry.tx_complete=9;
 assert(make_telemetry(&f,5,7,FD_PORT,&telemetry));
 assert(f.len==128&&f.bytes[4]==0xa5&&f.bytes[5]==0x5a&&f.bytes[6]==FD_PORT&&f.bytes[7]==1);
 assert(f.bytes[8]==0x78&&f.bytes[9]==0x56&&f.bytes[10]==0x34&&f.bytes[11]==0x12);
 assert(f.bytes[44]==9); /* tenth counter is tx_complete */
 assert(!make_telemetry(&f,0,0,PORTS,&telemetry));
 uint8_t quota=4;for(unsigned j=0;j<4;j++)assert(irq_budget_take(&quota));assert(!irq_budget_take(&quota));
 assert(bounded_reset_wait(false,0xfffffff0,0xfffffff5,20));
 assert(!bounded_reset_wait(false,0xfffffff0,4,20));
 assert(!bounded_reset_wait(true,0,0,20));
 uint32_t watermark[4]={0xa5a5a5a5,0xa5a5a5a5,0,0};
 assert(stack_watermark(watermark,4)==8);watermark[0]=0;assert(stack_watermark(watermark,4)==16);
 uint8_t partial[128]={0};uint16_t used=0;counters_t streamed={0};
 make_frame(&f,8,0,0,CAN_PORT);feed_frames(&streamed,partial,&used,f.bytes,3,8,2);
 assert(used==3&&streamed.rx==0);feed_frames(&streamed,partial,&used,f.bytes+3,5,8,2);
 assert(used==0&&streamed.rx==1);
 app_t a={0}; app_tick(&a,0); for(int i=0;i<PORTS;i++) assert(a.tx[i].count==1);
 app_tick(&a,0); for(int i=0;i<PORTS;i++) assert(a.tx[i].count==1);
 app_tick(&a,8); assert(a.tx[ETH_PORT].count==2);
 a.deadline[ETH_PORT]=0xfffffff0; app_tick(&a,3); assert(a.stats[ETH_PORT].overflow==1);
 assert(a.deadline[ETH_PORT]==8); /* retain phase without replaying missed ticks */
 app_t drift={0};app_tick(&drift,0);app_tick(&drift,10);assert(drift.deadline[ETH_PORT]==16);
 puts("protocol queue scheduler cs: passed");
}
