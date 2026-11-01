/*
 * world.h — RPG Axel Digital
 * FASE 05 — Elementos do mundo: árvores, pedras, arbustos.
 *
 * Objetos estáticos distribuídos pelo cenário.
 * Cada objeto tem posição e raio de colisão cilíndrica.
 */

#ifndef WORLD_H
#define WORLD_H

/* Número máximo de objetos estáticos no mundo. */
#define WORLD_OBJECTS_MAX 64

typedef enum {
    WORLD_OBJ_TREE   = 0,
    WORLD_OBJ_ROCK   = 1,
    WORLD_OBJ_BUSH   = 2
} WorldObjType;

typedef struct {
    float         x;
    float         y;   /* base do objeto, calculada pelo terreno */
    float         z;
    float         radius;   /* raio de colisão cilíndrica */
    WorldObjType  type;
    int           active;
} WorldObject;

/* Inicializa e distribui os objetos pelo mundo. */
void world_init(void);

/* Desenha todos os objetos ativos. */
void world_draw(void);

/*
 * Testa colisão cilíndrica entre o jogador e os objetos.
 * Se houver sobreposição, (px, pz) são empurrados para fora.
 * Chamar após player_update, antes de aplicar terrain_height_at.
 */
void world_collide_player(float *px, float *pz, float player_radius);

/* Acesso à lista de objetos (para futuras interações). */
const WorldObject *world_get_objects(int *count);

#endif
