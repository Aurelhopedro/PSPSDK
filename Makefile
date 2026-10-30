# RPG Axel Digital
# Criado por Axev Digital
# FASE 03 — Primeiro ambiente

TARGET = rpg_axel_digital

OBJS = src/main.o \
       src/graphics/graphics.o \
       src/graphics/camera.o \
       src/graphics/player.o \
       src/graphics/terrain.o

PSP_EBOOT_TITLE = RPG Axel Digital

CFLAGS = -O2 -G0 -Wall -DPSP
CXXFLAGS = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS = $(CFLAGS)

LIBS = -lpspgu -lpspgum -lpspdisplay -lpspge \
       -lpspctrl -lpspkernel -lpspsdk -lc -lm

PSPSDK ?= $(shell psp-config --pspsdk-path 2>/dev/null)

ifndef PSPSDK
$(error PSPSDK nao encontrado.)
endif

include $(PSPSDK)/lib/build.mak
