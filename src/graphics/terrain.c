/*
 * terrain.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 03 — Primeiro ambiente.
 * Terreno 3D de 100x100 unidades.
 */

#include "terrain.h"

#include <pspgu.h>
#include <pspgum.h>

#define TERRAIN_SIZE 100.0f
#define TERRAIN_CELLS 20
#define TERRAIN_STEP (TERRAIN_SIZE / TERRAIN_CELLS)

#define TERRAIN_VERTEX_COUNT (TERRAIN_CELLS * TERRAIN_CELLS * 6)

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

static void add_vertex(
    int *index,
    unsigned int color,
    float x,
    float z
) {
    vertices[*index].color = color;
    vertices[*index].x = x;
    vertices[*index].y = 0.0f;
    vertices[*index].z = z;

    (*index)++;
}

void terrain_init(void) {
    int index = 0;

    const float half = TERRAIN_SIZE * 0.5f;

    for (int z = 0; z < TERRAIN_CELLS; z++) {
        for (int x = 0; x < TERRAIN_CELLS; x++) {

            float x0 = -half + x * TERRAIN_STEP;
            float z0 = -half + z * TERRAIN_STEP;

            float x1 = x0 + TERRAIN_STEP;
            float z1 = z0 + TERRAIN_STEP;

            unsigned int color;

            if ((x + z) % 4 == 0) {
                color = 0xFF367D35;
            } else if ((x + z) % 4 == 1) {
                color = 0xFF408B3B;
            } else if ((x + z) % 4 == 2) {
                color = 0xFF478F40;
            } else {
                color = 0xFF3B8438;
            }

            /* Primeiro triângulo. */
            add_vertex(&index, color, x0, z0);
            add_vertex(&index, color, x1, z0);
            add_vertex(&index, color, x1, z1);

            /* Segundo triângulo. */
            add_vertex(&index, color, x0, z0);
            add_vertex(&index, color, x1, z1);
            add_vertex(&index, color, x0, z1);
        }
    }

    initialized = 1;
}

void terrain_draw(void) {
    if (!initialized)
        return;

    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();

    sceGuDisable(GU_TEXTURE_2D);
    sceGuShadeModel(GU_SMOOTH);

    sceGumDrawArray(
        GU_TRIANGLES,
        GU_COLOR_8888 |
        GU_VERTEX_32BITF |
        GU_TRANSFORM_3D,
        TERRAIN_VERTEX_COUNT,
        NULL,
        vertices
    );
}
