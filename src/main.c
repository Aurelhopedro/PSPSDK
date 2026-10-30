/*
 * main.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 01: Motor gráfico 3D — cubo colorido com rotação contínua.
 * Renderização via PSP GU/GUM com double buffering e Z-buffer.
 */

#include <pspkernel.h>
#include <pspctrl.h>
#include <pspgu.h>
#include <pspgum.h>
#include <math.h>

#include "graphics/graphics.h"
#include "graphics/camera.h"
#include "graphics/cube.h"

/* ---------------------------------------------------------- */
/* Módulo PSP                                                 */
/* ---------------------------------------------------------- */
PSP_MODULE_INFO("RPG_AXEL_DIGITAL", 0, 1, 0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);
PSP_HEAP_SIZE_KB(20480);

/* ---------------------------------------------------------- */
/* Callback de saída                                          */
/* ---------------------------------------------------------- */
static volatile int running = 1;

static int exit_callback(int arg1, int arg2, void *common) {
    (void)arg1; (void)arg2; (void)common;
    running = 0;
    return 0;
}

static int callback_thread(SceSize args, void *argp) {
    (void)args; (void)argp;
    int cbid = sceKernelCreateCallback("Exit Callback", exit_callback, NULL);
    sceKernelRegisterExitCallback(cbid);
    sceKernelSleepThreadCB();
    return 0;
}

static void setup_callbacks(void) {
    int thid = sceKernelCreateThread("cb_thread", callback_thread,
                                      0x11, 0xFA0, 0, 0);
    if (thid >= 0) sceKernelStartThread(thid, 0, 0);
}

/* ---------------------------------------------------------- */
/* Conversão graus → radianos para GUM                       */
/* ---------------------------------------------------------- */
#ifndef GU_PI
#define GU_PI 3.14159265358979323846f
#endif
#define DEG2RAD(d) ((d) * GU_PI / 180.0f)

/* ---------------------------------------------------------- */
/* Entrada principal                                          */
/* ---------------------------------------------------------- */
int main(void) {
    setup_callbacks();

    /* Inicializar GU e câmara */
    gfx_init();

    Camera cam;
    camera_init(&cam);

    cube_init();

    /* Estado de rotação (em radianos) */
    float rot_x = 0.0f;
    float rot_y = 0.0f;
    float rot_z = 0.0f;

    /* Velocidade de rotação por frame (~60 fps) */
    const float speed_x = DEG2RAD(0.5f);
    const float speed_y = DEG2RAD(0.8f);
    const float speed_z = DEG2RAD(0.3f);

    /* Controlos */
    sceCtrlSetSamplingCycle(0);
    sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);

    /* -------------------------------------------------- */
    /* Ciclo principal                                    */
    /* -------------------------------------------------- */
    while (running) {
        /* 1. Ler controlos */
        SceCtrlData pad;
        sceCtrlReadBufferPositive(&pad, 1);
        if (pad.Buttons & PSP_CTRL_CROSS) {
            running = 0;
        }

        /* 2. Atualizar rotação */
        rot_x += speed_x;
        rot_y += speed_y;
        rot_z += speed_z;

        /* Manter valores no intervalo [0, 2π] para evitar drift */
        if (rot_x > 2.0f * GU_PI) rot_x -= 2.0f * GU_PI;
        if (rot_y > 2.0f * GU_PI) rot_y -= 2.0f * GU_PI;
        if (rot_z > 2.0f * GU_PI) rot_z -= 2.0f * GU_PI;

        /* 3-4. Iniciar frame e limpar ecrã/Z-buffer */
        gfx_begin_frame();

        /* 5. Configurar câmara */
        camera_apply_projection(&cam);
        camera_apply_view(&cam);

        /* 6. Desenhar cubo */
        cube_draw(rot_x, rot_y, rot_z);

        /* 7-9. Finalizar e apresentar frame */
        gfx_end_frame();

        /* 10. Continuar ciclo */
    }

    /* Encerramento */
    gfx_shutdown();
    sceKernelExitGame();
    return 0;
}
