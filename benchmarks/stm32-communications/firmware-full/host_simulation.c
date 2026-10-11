/* Conditional queue/protocol model: executes real core logic over30min.
 * Service cadence2ms is an input assumption, not an observed MCU result.
 * Completion windows conservatively include wire time and a peer echo slot.
 */
#include "core.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 app_t model={0};
 const uint16_t completion_ms[PORTS]={2,4,6,4,8,2,2,2,2};
 uint32_t complete[PORTS]={0};bool active[PORTS]={0};
 for(uint32_t now=0;now<1800000;now+=2){
  app_tick(&model,now);
  for(unsigned p=0;p<PORTS;p++){
   if(active[p]&&now>=complete[p]){
    frame_t *f=queue_peek(&model.tx[p]);assert(f);
    assert(accept_frame(&model.stats[p],f->bytes,f->len,now));
    queue_pop(&model.tx[p]);model.stats[p].tx_complete++;active[p]=false;
   }
   if(!active[p]&&queue_peek(&model.tx[p])){active[p]=true;model.stats[p].tx++;complete[p]=now+completion_ms[p];}
  }
 }
 uint32_t overflow=0;
 for(unsigned p=0;p<PORTS;p++){counters_t *s=&model.stats[p];overflow+=s->overflow;assert(!s->crc_error&&!s->lost&&!s->reorder);}
 printf("{\"scope\":\"portable-model-with-assumed-service\",\"hardware_tested\":false,\"duration_ms\":1800000,\"overflow\":%lu,\"rx\":[",(unsigned long)overflow);
 for(unsigned p=0;p<PORTS;p++)printf("%s%lu",p?",":"",(unsigned long)model.stats[p].rx);
 puts("]}");return 0;
}
