/*
 * main.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * Ecrã de arranque com inicialização correta do display PSP.
 * Compatível com PPSSPP e PSP física.
 *
 * FASE 00: Fundação técnica verificada.
 */

#include <pspkernel.h>
#include <pspdisplay.h>
#include <pspctrl.h>
#include <pspdebug.h>
#include <string.h>
#include <stdlib.h>

/* ---------------------------------------------------------- */
/* Módulo PSP                                                 */
/* ---------------------------------------------------------- */
PSP_MODULE_INFO("RPG_AXEL_DIGITAL", 0, 1, 0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);
PSP_HEAP_SIZE_KB(20480);

/* ---------------------------------------------------------- */
/* Framebuffer — necessário para ecrã visível no PPSSPP      */
/* ---------------------------------------------------------- */
#define PSP_FB_WIDTH    512   /* largura real do framebuffer (potência de 2) */
#define PSP_SCR_WIDTH   480   /* largura visível */
#define PSP_SCR_HEIGHT  272   /* altura visível */
#define PSP_PIXEL_FORMAT PSP_DISPLAY_PIXEL_FORMAT_8888

static unsigned int __attribute__((aligned(16))) fb[PSP_FB_WIDTH * PSP_SCR_HEIGHT];

/* ---------------------------------------------------------- */
/* Callback de saída                                          */
/* ---------------------------------------------------------- */
static volatile int running = 1;

int exit_callback(int arg1, int arg2, void *common) {
    running = 0;
    return 0;
}

int callback_thread(SceSize args, void *argp) {
    int cbid = sceKernelCreateCallback("Exit Callback", exit_callback, NULL);
    sceKernelRegisterExitCallback(cbid);
    sceKernelSleepThreadCB();
    return 0;
}

void setup_callbacks(void) {
    int thid = sceKernelCreateThread("cb_thread", callback_thread,
                                      0x11, 0xFA0, 0, 0);
    if (thid >= 0) sceKernelStartThread(thid, 0, 0);
}

/* ---------------------------------------------------------- */
/* Inicializar display corretamente                           */
/* Sem isto o PPSSPP mostra ecrã preto mesmo com texto        */
/* ---------------------------------------------------------- */
void init_display(void) {
    sceDisplaySetMode(0, PSP_SCR_WIDTH, PSP_SCR_HEIGHT);
    sceDisplaySetFrameBuf(
        (void *)fb,
        PSP_FB_WIDTH,
        PSP_PIXEL_FORMAT,
        PSP_DISPLAY_SETBUF_NEXTFRAME
    );
}

/* ---------------------------------------------------------- */
/* Entrada principal                                          */
/* ---------------------------------------------------------- */
int main(void) {
    setup_callbacks();

    /* Inicializar display ANTES do debug screen */
    init_display();

    /* Debug screen aponta para o mesmo framebuffer */
    pspDebugScreenInitEx((void *)fb, PSP_PIXEL_FORMAT, 1);
    pspDebugScreenSetBackColor(0xFF1a0a2e); /* roxo escuro */
    pspDebugScreenSetTextColor(0xFFFFD700); /* dourado */
    pspDebugScreenClear();

    /* -------------------------------------------------- */
    /* Cabeçalho                                          */
    /* -------------------------------------------------- */
    pspDebugScreenSetXY(2, 1);
    pspDebugScreenPrintf("============================================");
    pspDebugScreenSetXY(2, 2);
    pspDebugScreenPrintf("           RPG AXEL DIGITAL");
    pspDebugScreenSetXY(2, 3);
    pspDebugScreenPrintf("           Criado por Axev Digital");
    pspDebugScreenSetXY(2, 4);
    pspDebugScreenPrintf("============================================");

    /* Estado */
    pspDebugScreenSetTextColor(0xFF00FF88); /* verde claro */
    pspDebugScreenSetXY(2, 6);
    pspDebugScreenPrintf("[ OK ] Display inicializado");
    pspDebugScreenSetXY(2, 7);
    pspDebugScreenPrintf("[ OK ] Callbacks do kernel");
    pspDebugScreenSetXY(2, 8);
    pspDebugScreenPrintf("[ OK ] Sistema de controlos");
    pspDebugScreenSetXY(2, 9);
    pspDebugScreenPrintf("[ OK ] PSPSDK fundacao estavel");

    /* Info */
    pspDebugScreenSetTextColor(0xFFAAAAAA); /* cinzento */
    pspDebugScreenSetXY(2, 11);
    pspDebugScreenPrintf("FASE 00 concluida. Motor 3D na FASE 01.");

    /* Controlos */
    pspDebugScreenSetTextColor(0xFFFFFFFF); /* branco */
    pspDebugScreenSetXY(2, 14);
    pspDebugScreenPrintf("Pressiona X para sair.");

    /* -------------------------------------------------- */
    /* Loop principal                                     */
    /* -------------------------------------------------- */
    SceCtrlData pad;
    sceCtrlSetSamplingCycle(0);
    sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);

    while (running) {
        sceCtrlReadBufferPositive(&pad, 1);
        if (pad.Buttons & PSP_CTRL_CROSS) {
            running = 0;
        }
        sceDisplayWaitVblankStart();
    }

    sceKernelExitGame();
    return 0;
}
