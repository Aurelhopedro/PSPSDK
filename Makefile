# ============================================================
# Makefile — RPG Axel Digital
# Criado por Axev Digital
# Compatível com PSPSDK (pspdev toolchain)
# FASE 01: Motor 3D — GU/GUM + câmara + cubo
# ============================================================

TARGET          = rpg_axel_digital

OBJS            = src/main.o \
                  src/graphics/graphics.o \
                  src/graphics/camera.o \
                  src/graphics/cube.o

# Identidade do jogo
PSP_EBOOT_TITLE = RPG Axel Digital

# Flags do compilador
CFLAGS          = -O2 -G0 -Wall -DPSP
CXXFLAGS        = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS         = $(CFLAGS)

# Bibliotecas PSP:
# - pspgu       : sceGu* (Graphics Utility)
# - pspgum      : sceGum* (Matrix/Transform)
# - pspdisplay  : sceDisplay* / sceDisplayWaitVblankStart
# - pspge       : Graphics Engine (necessário para GU)
# - pspctrl     : sceCtrl*
# - pspkernel   : kernel (threads, callbacks)
# - pspdebug    : mantido para compatibilidade (não usado na Fase 01)
# - pspsdk      : runtime PSP
# - c, m        : libc e libm standard
LIBS            = -lpspgu -lpspgum -lpspdisplay -lpspge -lpspctrl \
                  -lpspkernel -lpspdebug -lpspsdk -lc -lm

# Localizar PSPSDK via psp-config (funciona no container pspdev/pspdev)
PSPSDK         ?= $(shell psp-config --pspsdk-path 2>/dev/null)

ifndef PSPSDK
  $(error PSPSDK nao encontrado. Instala pspdev ou define PSPDEV no ambiente.)
endif

include $(PSPSDK)/lib/build.mak
