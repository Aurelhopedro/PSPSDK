/*
 * RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 03 — Primeiro ambiente.
 * FASE 04 — Integração do protagonista 3D (AXP3).
 */

#include <pspkernel.h>
#include <pspctrl.h>
#include <pspgu.h>
#include <pspgum.h>

#include "graphics/graphics.h"
#include "graphics/camera.h"
#include "graphics/player.h"
#include "graphics/terrain.h"
#include "graphics/p3d_model.h"

PSP_MODULE_INFO("RPG_AXEL_DIGITAL", 0, 1, 0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);
PSP_HEAP_SIZE_KB(20480);

static volatile int running = 1;

static int exit_callback(int a, int b, void *c) {
    (void)a;
    (void)b;
    (void)c;

    running = 0;
    return 0;
}

static int callback_thread(SceSize args, void *argp) {
    (void)args;
    (void)argp;

    int cbid = sceKernelCreateCallback(
        "Exit Callback",
        exit_callback,
        NULL
    );

    sceKernelRegisterExitCallback(cbid);
    sceKernelSleepThreadCB();

    return 0;
}

static void setup_callbacks(void) {
    int thid = sceKernelCreateThread(
        "cb_thread",
        callback_thread,
        0x11,
        0xFA0,
        0,
        0
    );

    if (thid >= 0)
        sceKernelStartThread(thid, 0, 0);
}

int main(void) {
    setup_callbacks();

    gfx_init();

    /* Inicializar o terreno. */
    terrain_init();

    Camera cam;
    camera_init(&cam);

    Player player;
    player_init(&player);

    /* Inicializar e carregar o modelo do protagonista. */
    P3DModel protagonist;
    p3d_model_init(&protagonist);

    p3d_model_load(
        &protagonist,
        "ms0:/PSP/GAME/RPGAXEL/assets/protagonist.p3d"
    );

    /* Se o carregamento falhar, protagonist.loaded == 0
       e player_draw usará o personagem provisório. */

    sceCtrlSetSamplingCycle(0);
    sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);

    const float delta_time = 1.0f / 60.0f;

    while (running) {
        SceCtrlData pad;

        sceCtrlReadBufferPositive(&pad, 1);

        if (pad.Buttons & PSP_CTRL_CROSS) {
            running = 0;
            break;
        }

        player_update(&player, &pad, delta_time);

        /* Câmara em terceira pessoa. */
        cam.pos.x = player.x -
                    5.0f * __builtin_sinf(player.yaw);

        cam.pos.y = player.y + 3.0f;

        cam.pos.z = player.z -
                    5.0f * __builtin_cosf(player.yaw);

        cam.target.x = player.x;
        cam.target.y = player.y + 1.0f;
        cam.target.z = player.z;

        gfx_begin_frame();

        camera_apply_projection(&cam);
        camera_apply_view(&cam);

        /* Desenhar o ambiente e o personagem. */
        terrain_draw();
        player_draw(&player, &protagonist);

        gfx_end_frame();
    }

    /* Libertar o modelo antes de sair. */
    p3d_model_unload(&protagonist);

    sceGuTerm();
    sceKernelExitGame();

    return 0;
}
