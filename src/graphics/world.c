/*
 * world.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 05 — Elementos estáticos do mundo 3D.
 *
 * Implementa árvores, pedras e arbustos como geometria de caixas
 * simples (sem texturas), otimizados para a memória da PSP.
 *
 * Distribuição deterministicamente variada com LCG simples
 * para posições consistentes entre sessões sem ficheiro de mapa.
 *
 * Colisão cilíndrica: jogador é empurrado para fora do raio
 * de cada objeto.
 */

#include "world.h"
#include "terrain.h"

#include <pspgu.h>
#include <pspgum.h>
#include <math.h>

/* ------------------------------------------------------------------ */
/* Geometria base: cubo unitário (reutilizado de player.c)            */
/* ------------------------------------------------------------------ */

typedef struct { float x, y, z; } WVtx;

static WVtx __attribute__((aligned(16))) cube_v[] = {
    {-1,-1, 1},{ 1,-1, 1},{ 1, 1, 1},
    {-1,-1, 1},{ 1, 1, 1},{-1, 1, 1},
    { 1,-1,-1},{-1,-1,-1},{-1, 1,-1},
    { 1,-1,-1},{-1, 1,-1},{ 1, 1,-1},
    {-1, 1, 1},{ 1, 1, 1},{ 1, 1,-1},
    {-1, 1, 1},{ 1, 1,-1},{-1, 1,-1},
    {-1,-1,-1},{ 1,-1,-1},{ 1,-1, 1},
    {-1,-1,-1},{ 1,-1, 1},{-1,-1, 1},
    { 1,-1, 1},{ 1,-1,-1},{ 1, 1,-1},
    { 1,-1, 1},{ 1, 1,-1},{ 1, 1, 1},
    {-1,-1,-1},{-1,-1, 1},{-1, 1, 1},
    {-1,-1,-1},{-1, 1, 1},{-1, 1,-1}
};

/* ------------------------------------------------------------------ */
/* Objetos do mundo                                                    */
/* ------------------------------------------------------------------ */

static WorldObject objects[WORLD_OBJECTS_MAX];
static int obj_count = 0;
static int initialized = 0;

/* ------------------------------------------------------------------ */
/* LCG determinístico para distribuição de posições                   */
/* ------------------------------------------------------------------ */

static unsigned int lcg_state = 0x4A3F2E1D;

static float lcg_next_f(float min, float max) {
    lcg_state = lcg_state * 1664525u + 1013904223u;
    float t = (float)(lcg_state & 0xFFFF) / 65535.0f;
    return min + t * (max - min);
}

/* ------------------------------------------------------------------ */
/* Desenhar uma caixa com translate + scale                           */
/* ------------------------------------------------------------------ */

static void draw_box_ws(
    float cx, float cy, float cz,
    float sx, float sy, float sz,
    unsigned int color
) {
    ScePspFVector3 pos   = { cx, cy, cz };
    ScePspFVector3 scale = { sx, sy, sz };

    sceGumPushMatrix();
    sceGumTranslate(&pos);
    sceGumScale(&scale);
    sceGuColor(color);

    sceGumDrawArray(
        GU_TRIANGLES,
        GU_VERTEX_32BITF | GU_TRANSFORM_3D,
        36,
        NULL,
        cube_v
    );

    sceGumPopMatrix();
}

/* ------------------------------------------------------------------ */
/* Desenhar árvore                                                     */
/* ------------------------------------------------------------------ */
/*
 * Tronco: caixa castanha, 0.25 raio, altura ~1.5.
 * Copa:   caixa verde, escala 1.0×1.2×1.0, no topo do tronco.
 */
static void draw_tree(float x, float base_y, float z) {
    float trunk_h = 1.5f;
    float crown_h = 1.2f;

    /* Tronco. */
    draw_box_ws(
        x, base_y + trunk_h * 0.5f, z,
        0.25f, trunk_h * 0.5f, 0.25f,
        0xFF2A5C8A  /* castanho escuro ABGR */
    );

    /* Copa. */
    draw_box_ws(
        x, base_y + trunk_h + crown_h * 0.5f, z,
        1.0f, crown_h * 0.5f, 1.0f,
        0xFF1A7A1A  /* verde escuro */
    );
}

/* ------------------------------------------------------------------ */
/* Desenhar pedra                                                      */
/* ------------------------------------------------------------------ */
static void draw_rock(float x, float base_y, float z) {
    draw_box_ws(
        x, base_y + 0.35f, z,
        0.6f, 0.35f, 0.5f,
        0xFF707878  /* cinzento */
    );
}

/* ------------------------------------------------------------------ */
/* Desenhar arbusto                                                    */
/* ------------------------------------------------------------------ */
static void draw_bush(float x, float base_y, float z) {
    draw_box_ws(
        x, base_y + 0.4f, z,
        0.7f, 0.4f, 0.7f,
        0xFF257A25  /* verde médio */
    );
}

/* ------------------------------------------------------------------ */
/* world_init                                                          */
/* ------------------------------------------------------------------ */
/*
 * Distribuição:
 *   30 árvores, 16 pedras, 18 arbustos.
 * Evitar o centro (raio 6) para não bloquear o spawn do jogador.
 * Evitar a borda absoluta (> 46) para não sobrepor o limite do terreno.
 */

#define SPAWN_INNER 6.0f
#define SPAWN_OUTER 46.0f

static void place_object(WorldObjType type, float radius) {
    if (obj_count >= WORLD_OBJECTS_MAX)
        return;

    /* Tentar até 8 posições candidatas. */
    for (int attempt = 0; attempt < 8; attempt++) {
        float px = lcg_next_f(-SPAWN_OUTER, SPAWN_OUTER);
        float pz = lcg_next_f(-SPAWN_OUTER, SPAWN_OUTER);

        /* Excluir zona central. */
        float d2 = px * px + pz * pz;
        if (d2 < SPAWN_INNER * SPAWN_INNER)
            continue;

        /* Verificar separação mínima entre objetos (2× raio). */
        int overlap = 0;
        for (int i = 0; i < obj_count; i++) {
            float dx = objects[i].x - px;
            float dz = objects[i].z - pz;
            float min_sep = objects[i].radius + radius + 0.5f;
            if (dx*dx + dz*dz < min_sep * min_sep) {
                overlap = 1;
                break;
            }
        }
        if (overlap) continue;

        WorldObject *o = &objects[obj_count++];
        o->x      = px;
        o->y      = terrain_height_at(px, pz);
        o->z      = pz;
        o->radius = radius;
        o->type   = type;
        o->active = 1;
        return;
    }
}

void world_init(void) {
    obj_count   = 0;
    initialized = 0;
    lcg_state   = 0x4A3F2E1D; /* semente fixa → distribuição consistente */

    /* 30 árvores. */
    for (int i = 0; i < 30; i++) place_object(WORLD_OBJ_TREE, 1.0f);
    /* 16 pedras. */
    for (int i = 0; i < 16; i++) place_object(WORLD_OBJ_ROCK, 0.65f);
    /* 18 arbustos. */
    for (int i = 0; i < 18; i++) place_object(WORLD_OBJ_BUSH, 0.75f);

    initialized = 1;
}

/* ------------------------------------------------------------------ */
/* world_draw                                                          */
/* ------------------------------------------------------------------ */

void world_draw(void) {
    if (!initialized)
        return;

    sceGumMatrixMode(GU_MODEL);
    sceGuDisable(GU_TEXTURE_2D);

    for (int i = 0; i < obj_count; i++) {
        if (!objects[i].active)
            continue;

        WorldObject *o = &objects[i];

        sceGumLoadIdentity();

        switch (o->type) {
            case WORLD_OBJ_TREE:
                draw_tree(o->x, o->y, o->z);
                break;
            case WORLD_OBJ_ROCK:
                draw_rock(o->x, o->y, o->z);
                break;
            case WORLD_OBJ_BUSH:
                draw_bush(o->x, o->y, o->z);
                break;
        }
    }
}

/* ------------------------------------------------------------------ */
/* world_collide_player                                                */
/* ------------------------------------------------------------------ */
/*
 * Colisão cilíndrica simples: se o jogador entrar no raio de um
 * objeto, é empurrado para a superfície do cilindro.
 */

void world_collide_player(float *px, float *pz, float player_radius) {
    if (!initialized || !px || !pz)
        return;

    for (int i = 0; i < obj_count; i++) {
        if (!objects[i].active)
            continue;

        float dx = *px - objects[i].x;
        float dz = *pz - objects[i].z;
        float d2 = dx*dx + dz*dz;
        float min_d = objects[i].radius + player_radius;

        if (d2 < min_d * min_d && d2 > 0.0001f) {
            float d   = sqrtf(d2);
            float push = min_d - d;
            *px += (dx / d) * push;
            *pz += (dz / d) * push;
        }
    }
}

/* ------------------------------------------------------------------ */
/* world_get_objects                                                   */
/* ------------------------------------------------------------------ */

const WorldObject *world_get_objects(int *count) {
    if (count) *count = obj_count;
    return objects;
}
