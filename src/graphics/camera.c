/*
 * camera.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * Inicialização e aplicação da câmara 3D com PSP GUM.
 * FASE 01: Projeção perspetiva e matriz de visualização.
 */

#include "camera.h"
#include "graphics.h"

/* ---------------------------------------------------------- */
/* camera_init                                                */
/* ---------------------------------------------------------- */
void camera_init(Camera *cam) {
    /* Posição: recuada no eixo Z para enquadrar o cubo */
    cam->pos.x    =  0.0f;
    cam->pos.y    =  0.0f;
    cam->pos.z    =  5.0f;

    /* Olhar para a origem */
    cam->target.x =  0.0f;
    cam->target.y =  0.0f;
    cam->target.z =  0.0f;

    /* Eixo "cima" = Y positivo */
    cam->up.x =  0.0f;
    cam->up.y =  1.0f;
    cam->up.z =  0.0f;

    /* Perspetiva */
    cam->fov         = 75.0f;
    cam->aspect      = (float)GFX_SCR_WIDTH / (float)GFX_SCR_HEIGHT; /* ~1.7647 */
    cam->near_plane  = 0.5f;
    cam->far_plane   = 1000.0f;
}

/* ---------------------------------------------------------- */
/* camera_apply_projection                                    */
/* ---------------------------------------------------------- */
void camera_apply_projection(const Camera *cam) {
    sceGumMatrixMode(GU_PROJECTION);
    sceGumLoadIdentity();
    sceGumPerspective(cam->fov, cam->aspect, cam->near_plane, cam->far_plane);
}

/* ---------------------------------------------------------- */
/* camera_apply_view                                          */
/* ---------------------------------------------------------- */
void camera_apply_view(const Camera *cam) {
    sceGumMatrixMode(GU_VIEW);
    sceGumLoadIdentity();
    sceGumLookAt(
        (ScePspFVector3 *)&cam->pos,
        (ScePspFVector3 *)&cam->target,
        (ScePspFVector3 *)&cam->up
    );
}
