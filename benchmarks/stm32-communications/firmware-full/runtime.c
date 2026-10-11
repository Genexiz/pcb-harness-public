/* Explicit freestanding runtime: no libc heap or hidden startup allocation. */
#include <stddef.h>
void Nop(void){__asm volatile("nop");}
void __libc_init_array(void){}
void *memcpy(void *dst,const void *src,size_t n){unsigned char *d=dst;const unsigned char *s=src;for(size_t i=0;i<n;i++)d[i]=s[i];return dst;}
void *memset(void *dst,int c,size_t n){unsigned char *d=dst;for(size_t i=0;i<n;i++)d[i]=(unsigned char)c;return dst;}
int memcmp(const void *a,const void *b,size_t n){const unsigned char *p=a,*q=b;for(size_t i=0;i<n;i++)if(p[i]!=q[i])return (int)p[i]-q[i];return 0;}
