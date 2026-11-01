#ifndef TERRAIN_H
#define TERRAIN_H

/*
 * terrain.h — RPG Axel Digital
 * FASE 05 — Terreno com relevo e heightmap procedural.
 */

void terrain_init(void);
void terrain_draw(void);

/*
 * Devolve a elevação Y do terreno na posição (x, z).
 * Usado pelo player_update para colocar o jogador
 * sobre o relevo em vez de y=0 fixo.
 */
float terrain_height_at(float x, float z);

#endif
