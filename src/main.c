/*
 * RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 03 — Primeiro ambiente.
 * FASE 04 — Integração do protagonista 3D (AXP3).
 * FASE 05 — Mundo com relevo, objetos estáticos, animação AXS1.
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
#include "graphics/p3d_anim.h"
#include "graphics/world.h"

PSP_MODULE_INFO("RPG_AXEL_DIGITAL", 0, 1, 0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);
PSP_HEAP_SIZE_KB(20480);

static volatile int running = 1;

static int exit_callback(int a, int b, void *c) {
    (void)a; (void)b; (void)c;
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
    int thid = sceKernelCreateThread(
        "cb_thread", callback_thread, 0x11, 0xFA0, 0, 0
    );
    if (thid >= 0)
        sceKernelStartThread(thid, 0, 0);
}

int main(void) {
    setup_callbacks();

    gfx_init();

    /* Inicializar terreno e mundo. */
    terrain_init();
    world_init();

    Camera cam;
    camera_init(&cam);

    Player player;
    player_init(&player);

    /* Modelo estático AXP3 (fallback se AXS1 não estiver disponível). */
    P3DModel protagonist;
    p3d_model_init(&protagonist);
    p3d_model_load(
        &protagonist,
        "ms0:/PSP/GAME/RPGAXEL/assets/protagonist.p3d"
    );

    /* Modelo animado AXS1. */
    P3DAnim protagonist_anim;
    p3d_anim_init(&protagonist_anim);
    p3d_anim_load(
        &protagonist_anim,
        "ms0:/PSP/GAME/RPGAXEL/assets/protagonist.axs"
    );

    /* Estado de animação: começa em idle. */
    P3DAnimState anim_state;
    p3d_anim_state_init(&anim_state);

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

        /* Colisão com objetos do mundo (ajusta x, z antes do update). */
        world_collide_player(&player.x, &player.z, 0.35f);

        /* Altura do terreno na posição atual. */
        float ground_y = terrain_height_at(player.x, player.z);

        /* Atualizar movimento com relevo. */
        player_update(&player, &pad, delta_time, ground_y);

        /* Selecionar clip de animação e atualizar skinning. */
        if (protagonist_anim.loaded) {
            player_select_anim(&player, &anim_state);
            p3d_anim_update(&protagonist_anim, &anim_state, delta_time);
        }

        /* Câmara em terceira pessoa. */
        cam.pos.x = player.x - 5.0f * __builtin_sinf(player.yaw);
        cam.pos.y = player.y + 3.0f;
        cam.pos.z = player.z - 5.0f * __builtin_cosf(player.yaw);
        cam.target.x = player.x;
        cam.target.y = player.y + 1.0f;
        cam.target.z = player.z;

        gfx_begin_frame();
        camera_apply_projection(&cam);
        camera_apply_view(&cam);

        /* Desenhar ambiente. */
        terrain_draw();
        world_draw();

        /* Desenhar personagem (anim > model estático > fallback). */
        player_draw(&player, &protagonist, &protagonist_anim);

        gfx_end_frame();
    }

    /* Libertar recursos. */
    p3d_anim_unload(&protagonist_anim);
    p3d_model_unload(&protagonist);

    sceGuTerm();
    sceKernelExitGame();
    return 0;
}
