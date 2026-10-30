# ============================================================
# Makefile — PSP RPG 3D
# Compatível com PSPSDK (pspdev toolchain)
# ============================================================

TARGET      = psp_rpg
OBJS        = src/main.o

# Título e versão exibidos no XMB da PSP
TITLE       = PSP RPG 3D
PSP_EBOOT_TITLE = $(TITLE)
PSP_EBOOT   = EBOOT.PBP

# Flags do compilador
CFLAGS      = -O2 -G0 -Wall -DPSP
CXXFLAGS    = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS     = $(CFLAGS)

# Bibliotecas PSP necessárias para fase inicial
LIBS        = -lpspdisplay -lpspge -lpspctrl -lpspsdk -lc -lpspnet \
              -lpspnet_inet -lpspnet_apctl -lm

# Incluir sistema de build do PSPSDK
PSPSDK      = $(shell psp-config --pspsdk-path)
include     $(PSPSDK)/lib/build.mak
