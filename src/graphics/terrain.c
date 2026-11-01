/*
 * terrain.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 03 — Primeiro ambiente, terreno plano.
 * FASE 05 — Relevo procedural, heightmap, terrain_height_at().
 *
 * Heightmap gerado por combinação de senos/cossenos.
 * Grelha 40×40 células sobre 100×100 unidades de mundo.
 * Buffer de vértices estático pré-calculado em terrain_init().
 */

#include "terrain.h"

#include <pspgu.h>
#include <pspgum.h>
#include <math.h>

/* ------------------------------------------------------------------ */
/* Constantes                                                          */
/* ------------------------------------------------------------------ */

#define TERRAIN_SIZE   100.0f
#define TERRAIN_CELLS  40
#define TERRAIN_STEP   (TERRAIN_SIZE / TERRAIN_CELLS)

/*
 * Cada célula = 2 triângulos = 6 vértices.
 * 40*40*6 = 9600 vértices — cabe confortavelmente em DRAM da PSP.
 */
#define TERRAIN_VERTEX_COUNT (TERRAIN_CELLS * TERRAIN_CELLS * 6)

/* ------------------------------------------------------------------ */
/* Vértice de terreno: cor + posição (sem textura, sem normal)        */
/* ------------------------------------------------------------------ */

typedef struct {
    unsigned int color;
    float x;
    float y;
    float z;
} TerrainVertex;

static TerrainVertex
__attribute__((aligned(16)))
vertices[TERRAIN_VERTEX_COUNT];

static int initialized = 0;

/* ------------------------------------------------------------------ */
/* Heightmap procedural                                                */
/* ------------------------------------------------------------------ */
/*
 * Combina três ondas de seno/coseno para criar relevo variado
 * mas suave. Amplitude máxima ≈ 2.5 unidades, adequada para
 * personagem com altura ~2 unidades.
 */
static float height_func(float x, float z) {
    return
        0.8f  * sinf(x * 0.12f) * cosf(z * 0.10f) +
        0.5f  * sinf(x * 0.23f + 1.1f) * sinf(z * 0.19f + 0.7f) +
        0.25f * cosf(x * 0.37f) * cosf(z * 0.31f + 1.5f);
}

/* ------------------------------------------------------------------ */
/* Cor da superfície baseada na altura e posição                      */
/* ------------------------------------------------------------------ */
static unsigned int surface_color(float x, float z, float y) {
    /* Picos mais claros, vales mais escuros. */
    int bright = (int)(y * 18.0f);
    if (bright >  30) bright =  30;
    if (bright < -20) bright = -20;

    /* Padrão base: quatro tons de verde. */
    int pattern = ((int)(x / TERRAIN_STEP) + (int)(z / TERRAIN_STEP)) & 3;

    unsigned int base;
    if      (pattern == 0) base = 0xFF367D35;
    else if (pattern == 1) base = 0xFF408B3B;
    else if (pattern == 2) base = 0xFF478F40;
    else                   base = 0xFF3B8438;

    /* Ajustar verde pelo relevo. */
    int g = (int)((base >> 8) & 0xFF) + bright;
    if (g > 255) g = 255;
    if (g <   0) g =   0;

    return (base & 0xFF0000FF) | ((unsigned int)g << 8) | 0xFF000000;
}

/* ------------------------------------------------------------------ */
/* terrain_init                                                        */
/* ------------------------------------------------------------------ */

void terrain_init(void) {
    int index = 0;
    const float half = TERRAIN_SIZE * 0.5f;

    for (int zi = 0; zi < TERRAIN_CELLS; zi++) {
        for (int xi = 0; xi < TERRAIN_CELLS; xi++) {

            float x0 = -half + xi * TERRAIN_STEP;
            float z0 = -half + zi * TERRAIN_STEP;
            float x1 = x0 + TERRAIN_STEP;
            float z1 = z0 + TERRAIN_STEP;

            float y00 = height_func(x0, z0);
            float y10 = height_func(x1, z0);
            float y11 = height_func(x1, z1);
            float y01 = height_func(x0, z1);

            /* Média de altura da célula para a cor. */
            float yavg = (y00 + y10 + y11 + y01) * 0.25f;
            unsigned int col = surface_color(x0, z0, yavg);

            /* Triângulo 1: (x0,z0) (x1,z0) (x1,z1) */
            vertices[index].color = col;
            vertices[index].x = x0; vertices[index].y = y00; vertices[index].z = z0; index++;

            vertices[index].color = col;
            vertices[index].x = x1; vertices[index].y = y10; vertices[index].z = z0; index++;

            vertices[index].color = col;
            vertices[index].x = x1; vertices[index].y = y11; vertices[index].z = z1; index++;

            /* Triângulo 2: (x0,z0) (x1,z1) (x0,z1) */
            vertices[index].color = col;
            vertices[index].x = x0; vertices[index].y = y00; vertices[index].z = z0; index++;

            vertices[index].color = col;
            vertices[index].x = x1; vertices[index].y = y11; vertices[index].z = z1; index++;

            vertices[index].color = col;
            vertices[index].x = x0; vertices[index].y = y01; vertices[index].z = z1; index++;
        }
    }

    initialized = 1;
}

/* ------------------------------------------------------------------ */
/* terrain_draw                                                        */
/* ------------------------------------------------------------------ */

void terrain_draw(void) {
    if (!initialized)
        return;

    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();

    sceGuDisable(GU_TEXTURE_2D);
    sceGuShadeModel(GU_SMOOTH);

    sceGumDrawArray(
        GU_TRIANGLES,
        GU_COLOR_8888 | GU_VERTEX_32BITF | GU_TRANSFORM_3D,
        TERRAIN_VERTEX_COUNT,
        NULL,
        vertices
    );
}

/* ------------------------------------------------------------------ */
/* terrain_height_at                                                   */
/* ------------------------------------------------------------------ */
/*
 * Interpolação bilinear da altura na posição (x, z).
 * Usado por player_update para assentar o jogador no relevo.
 */

float terrain_height_at(float x, float z) {
    const float half = TERRAIN_SIZE * 0.5f;

    /* Fora dos limites: devolver 0. */
    if (x < -half || x > half || z < -half || z > half)
        return 0.0f;

    /* Célula onde (x,z) cai. */
    float lx = (x + half) / TERRAIN_STEP;
    float lz = (z + half) / TERRAIN_STEP;

    int xi = (int)lx;
    int zi = (int)lz;

    /* Clamp para não sair do array. */
    if (xi >= TERRAIN_CELLS) xi = TERRAIN_CELLS - 1;
    if (zi >= TERRAIN_CELLS) zi = TERRAIN_CELLS - 1;

    float fx = lx - (float)xi;
    float fz = lz - (float)zi;

    /* Cantos da célula. */
    float x0 = -half + xi * TERRAIN_STEP;
    float z0 = -half + zi * TERRAIN_STEP;
    float x1 = x0 + TERRAIN_STEP;
    float z1 = z0 + TERRAIN_STEP;

    float h00 = height_func(x0, z0);
    float h10 = height_func(x1, z0);
    float h01 = height_func(x0, z1);
    float h11 = height_func(x1, z1);

    /* Interpolação bilinear. */
    float h0 = h00 + fx * (h10 - h00);
    float h1 = h01 + fx * (h11 - h01);

    return h0 + fz * (h1 - h0);
}
