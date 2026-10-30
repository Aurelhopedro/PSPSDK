# ============================================================
# Makefile — PSP RPG 3D
# Compatível com PSPSDK (pspdev toolchain)
# ============================================================

TARGET      = psp_rpg
OBJS        = src/main.o

# Título exibido no XMB da PSP
PSP_EBOOT_TITLE = PSP RPG 3D

# Flags do compilador
CFLAGS      = -O2 -G0 -Wall -DPSP
CXXFLAGS    = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS     = $(CFLAGS)

# Bibliotecas PSP para fase inicial
LIBS        = -lpspdisplay -lpspge -lpspctrl -lpspsdk -lc -lm

# Localizar PSPSDK automaticamente via psp-config
# O container pspdev/pspdev já tem psp-config no PATH
PSPSDK     ?= $(shell psp-config --pspsdk-path 2>/dev/null)

ifndef PSPSDK
  $(error PSPSDK nao encontrado. Instala pspdev ou define PSPDEV no ambiente.)
endif

include $(PSPSDK)/lib/build.mak
