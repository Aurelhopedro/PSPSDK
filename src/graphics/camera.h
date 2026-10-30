/*
 * camera.h — RPG Axel Digital
 * Criado por Axev Digital
 *
 * Estrutura e interface da câmara 3D.
 * FASE 01: Projeção perspetiva via PSP GUM.
 */

#ifndef CAMERA_H
#define CAMERA_H

#include <pspgum.h>

/* ---------------------------------------------------------- */
/* Estrutura da câmara                                        */
/* ---------------------------------------------------------- */
typedef struct {
    ScePspFVector3 pos;      /* posição no espaço */
    ScePspFVector3 target;   /* ponto para onde aponta */
    ScePspFVector3 up;       /* vetor "cima" */
    float fov;               /* campo de visão em graus */
    float aspect;            /* relação de aspeto (largura/altura) */
    float near_plane;        /* plano próximo */
    float far_plane;         /* plano distante */
} Camera;

/* ---------------------------------------------------------- */
/* Interface pública                                          */
/* ---------------------------------------------------------- */

/* Inicializa a câmara com valores adequados para a Fase 01. */
void camera_init(Camera *cam);

/* Aplica projeção perspetiva (GU_PROJECTION). */
void camera_apply_projection(const Camera *cam);

/* Aplica matriz de visualização (GU_VIEW). */
void camera_apply_view(const Camera *cam);

#endif /* CAMERA_H */
