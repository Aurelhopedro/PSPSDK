/*
 * main.c — PSP RPG 3D
 * FASE 00: Programa inicial para verificar fundação do projeto.
 *
 * Exibe um ecrã de boot com texto, cor de fundo e aguarda
 * que o utilizador pressione X para sair.
 *
 * Compilar com: make
 * Testar em:    PPSSPP ou PSP real
 */

#include <pspkernel.h>
#include <pspdisplay.h>
#include <pspctrl.h>
#include <pspdebug.h>
#include <string.h>
#include <stdlib.h>

/* Módulo PSP obrigatório */
PSP_MODULE_INFO("PSP_RPG_3D", 0, 1, 0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);
PSP_HEAP_SIZE_KB(20480);

/* ---------------------------------------------------------- */
/* Callback de saída                                          */
/* ---------------------------------------------------------- */
static int running = 1;

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
    int thid = sceKernelCreateThread("update_thread", callback_thread,
                                      0x11, 0xFA0, 0, 0);
    if (thid >= 0) sceKernelStartThread(thid, 0, 0);
}

/* ---------------------------------------------------------- */
/* Entrada principal                                          */
/* ---------------------------------------------------------- */
int main(void) {
    setup_callbacks();

    /* Inicializar ecrã de debug — suficiente para FASE 00 */
    pspDebugScreenInit();
    pspDebugScreenSetBackColor(0xFF000033); /* azul escuro */
    pspDebugScreenSetTextColor(0xFFFFFFFF); /* branco */
    pspDebugScreenClear();

    /* Cabeçalho */
    pspDebugScreenSetXY(2, 2);
    pspDebugScreenPrintf("==============================");
    pspDebugScreenSetXY(2, 3);
    pspDebugScreenPrintf("       PSP RPG 3D");
    pspDebugScreenSetXY(2, 4);
    pspDebugScreenPrintf("==============================");

    /* Info da fase */
    pspDebugScreenSetXY(2, 6);
    pspDebugScreenPrintf("FASE 00 — Fundacao OK");
    pspDebugScreenSetXY(2, 7);
    pspDebugScreenPrintf("Sistema: PSPSDK Inicializado");
    pspDebugScreenSetXY(2, 8);
    pspDebugScreenPrintf("Display: 480x272 @ 60fps");

    /* Controlos */
    pspDebugScreenSetXY(2, 11);
    pspDebugScreenPrintf("Pressiona X para sair.");

    /* Estado do sistema */
    pspDebugScreenSetXY(2, 13);
    pspDebugScreenPrintf("[ OK ] Kernel callbacks");
    pspDebugScreenSetXY(2, 14);
    pspDebugScreenPrintf("[ OK ] Debug screen");
    pspDebugScreenSetXY(2, 15);
    pspDebugScreenPrintf("[ OK ] Controlo de input");

    /* Aguardar input */
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
