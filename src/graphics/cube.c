/*
 * cube.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * Geometria 3D do cubo com seis faces coloridas.
 * Renderizado com PSP GU/GUM, vértices estáticos alinhados.
 * FASE 01.
 */

#include "cube.h"
#include <pspgu.h>
#include <pspgum.h>

/* ---------------------------------------------------------- */
/* Estrutura de vértice compatível com GU_COLOR_8888 | GU_VERTEX_32BITF */
/* O GU lê: cor (u32) seguido de x, y, z (float)             */
/* ---------------------------------------------------------- */
typedef struct {
    unsigned int color;  /* ABGR */
    float x, y, z;
} __attribute__((packed, aligned(4))) Vertex;

/* ---------------------------------------------------------- */
/* 36 vértices: 6 faces × 2 triângulos × 3 vértices          */
/*                                                            */
/* Cores por face (ABGR):                                     */
/*   +Z  frente   vermelho    0xFF0000FF  →  ABGR 0xFF0000FF */
/*   -Z  trás     verde       0xFF00FF00                     */
/*   +Y  topo     azul        0xFFFF0000                     */
/*   -Y  base     amarelo     0xFF00FFFF                     */
/*   +X  direita  magenta     0xFFFF00FF                     */
/*   -X  esquerda ciano       0xFFFFFF00                     */
/*                                                            */
/* Nota: PSP GU usa ABGR (A=alpha, B=azul, G=verde, R=vermelho) */
/* ---------------------------------------------------------- */

static Vertex __attribute__((aligned(16))) cube_verts[36] = {

    /* ---- FRENTE (+Z) — vermelho ---- */
    { 0xFF0000FF, -1.0f, -1.0f,  1.0f },
    { 0xFF0000FF,  1.0f, -1.0f,  1.0f },
    { 0xFF0000FF,  1.0f,  1.0f,  1.0f },

    { 0xFF0000FF, -1.0f, -1.0f,  1.0f },
    { 0xFF0000FF,  1.0f,  1.0f,  1.0f },
    { 0xFF0000FF, -1.0f,  1.0f,  1.0f },

    /* ---- TRÁS (-Z) — verde ---- */
    { 0xFF00FF00,  1.0f, -1.0f, -1.0f },
    { 0xFF00FF00, -1.0f, -1.0f, -1.0f },
    { 0xFF00FF00, -1.0f,  1.0f, -1.0f },

    { 0xFF00FF00,  1.0f, -1.0f, -1.0f },
    { 0xFF00FF00, -1.0f,  1.0f, -1.0f },
    { 0xFF00FF00,  1.0f,  1.0f, -1.0f },

    /* ---- TOPO (+Y) — azul ---- */
    { 0xFFFF0000, -1.0f,  1.0f,  1.0f },
    { 0xFFFF0000,  1.0f,  1.0f,  1.0f },
    { 0xFFFF0000,  1.0f,  1.0f, -1.0f },

    { 0xFFFF0000, -1.0f,  1.0f,  1.0f },
    { 0xFFFF0000,  1.0f,  1.0f, -1.0f },
    { 0xFFFF0000, -1.0f,  1.0f, -1.0f },

    /* ---- BASE (-Y) — amarelo ---- */
    { 0xFF00FFFF, -1.0f, -1.0f, -1.0f },
    { 0xFF00FFFF,  1.0f, -1.0f, -1.0f },
    { 0xFF00FFFF,  1.0f, -1.0f,  1.0f },

    { 0xFF00FFFF, -1.0f, -1.0f, -1.0f },
    { 0xFF00FFFF,  1.0f, -1.0f,  1.0f },
    { 0xFF00FFFF, -1.0f, -1.0f,  1.0f },

    /* ---- DIREITA (+X) — magenta ---- */
    { 0xFFFF00FF,  1.0f, -1.0f,  1.0f },
    { 0xFFFF00FF,  1.0f, -1.0f, -1.0f },
    { 0xFFFF00FF,  1.0f,  1.0f, -1.0f },

    { 0xFFFF00FF,  1.0f, -1.0f,  1.0f },
    { 0xFFFF00FF,  1.0f,  1.0f, -1.0f },
    { 0xFFFF00FF,  1.0f,  1.0f,  1.0f },

    /* ---- ESQUERDA (-X) — ciano ---- */
    { 0xFFFFFF00, -1.0f, -1.0f, -1.0f },
    { 0xFFFFFF00, -1.0f, -1.0f,  1.0f },
    { 0xFFFFFF00, -1.0f,  1.0f,  1.0f },

    { 0xFFFFFF00, -1.0f, -1.0f, -1.0f },
    { 0xFFFFFF00, -1.0f,  1.0f,  1.0f },
    { 0xFFFFFF00, -1.0f,  1.0f, -1.0f },
};

/* ---------------------------------------------------------- */
/* cube_init                                                  */
/* ---------------------------------------------------------- */
void cube_init(void) {
    /* Geometria já declarada estaticamente — nada a fazer */
}

/* ---------------------------------------------------------- */
/* cube_draw                                                  */
/* ---------------------------------------------------------- */
void cube_draw(float rot_x, float rot_y, float rot_z) {
    /* Matriz de modelo: identidade + rotações */
    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();
    {
        ScePspFVector3 rx = { 1.0f, 0.0f, 0.0f };
        ScePspFVector3 ry = { 0.0f, 1.0f, 0.0f };
        ScePspFVector3 rz = { 0.0f, 0.0f, 1.0f };
        sceGumRotate(&rx, rot_x);
        sceGumRotate(&ry, rot_y);
        sceGumRotate(&rz, rot_z);
    }

    /* Renderizar triângulos com cor por vértice */
    sceGuColor(0xFFFFFFFF); /* branco — a cor real vem dos vértices */
    sceGumDrawArray(
        GU_TRIANGLES,
        GU_COLOR_8888 | GU_VERTEX_32BITF | GU_TRANSFORM_3D,
        36,      /* número de vértices */
        NULL,    /* sem índices */
        cube_verts
    );
}
