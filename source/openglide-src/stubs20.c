#include <windows.h>
#include <stdio.h>
static FILE* L(){ static FILE*f; if(!f){f=fopen("openglide_stubs.log","w");} return f; }
#define S(name,args,...) unsigned __stdcall name(__VA_ARGS__){ FILE*f=L(); if(f){fprintf(f,#name " called\n");fflush(f);} return 1; }
typedef unsigned U;
S(pciOpen,0,void) S(pciClose,0,void) S(pciDeviceExists,1,U) 
S(pciFindCard,3,U,U,U) S(pciFindCardMulti,4,U,U,U,U)
S(pciFindFreeMTRR,1,U) S(pciFindMTRRMatch,4,U,U,U,U)
S(pciGetConfigData,5,U,U,U,U,U) S(pciSetConfigData,5,U,U,U,U,U)
S(pciMapCard,5,U,U,U,U,U) S(pciMapCardMulti,6,U,U,U,U,U,U)
S(pciMapPhysicalToLinear,3,U,U,U) S(pciUnmapPhysical,2,U,U)
S(pciSetMTRR,4,U,U,U,U)
S(grSstConfigPipeline,3,U,U,U) S(grSstVidMode,2,U,U)
S(guMPInit,0,void) S(guMPTexCombineFunction,1,U) S(guMPTexSource,2,U,U) S(guMPDrawTriangle,3,U,U,U)
