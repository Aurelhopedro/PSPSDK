# ============================================================
# Makefile — RPG Axel Digital
# Criado por Axev Digital
# Compatível com PSPSDK (pspdev toolchain)
# ============================================================

TARGET          = rpg_axel_digital
OBJS            = src/main.o

# Identidade do jogo
PSP_EBOOT_TITLE = RPG Axel Digital

# Flags do compilador
CFLAGS          = -O2 -G0 -Wall -DPSP
CXXFLAGS        = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS         = $(CFLAGS)

# Bibliotecas PSP necessárias:
# - pspdisplay  : sceDisplaySetMode, sceDisplaySetFrameBuf, sceDisplayWaitVblankStart
# - pspge       : Graphics Engine (necessário para display)
# - pspctrl     : sceCtrlReadBufferPositive, sceCtrlSetSamplingMode
# - pspdebug    : pspDebugScreenInitEx, pspDebugScreenPrintf (OBRIGATÓRIO para texto)
# - pspkernel   : incluído via pspkernel.h / pspkubridge implícito em pspsdk
# - pspsdk      : runtime PSP (callbacks, threads)
# - c, m        : libc e libm standard
LIBS            = -lpspdisplay -lpspge -lpspctrl -lpspdebug -lpspsdk -lc -lm

# Localizar PSPSDK via psp-config (funciona no container pspdev/pspdev)
PSPSDK         ?= $(shell psp-config --pspsdk-path 2>/dev/null)

ifndef PSPSDK
  $(error PSPSDK nao encontrado. Instala pspdev ou define PSPDEV no ambiente.)
endif

include $(PSPSDK)/lib/build.mak
