#ifndef PLAYER_H
#define PLAYER_H

/*
 * player.h — RPG Axel Digital
 * FASE 05 — Suporte a terreno com relevo, colisão com objetos,
 *            e animação esquelética AXS1.
 */

#include <pspctrl.h>

#include "p3d_model.h"
#include "p3d_anim.h"

typedef struct {
    float x;
    float y;
    float z;

    float yaw;

    float vertical_velocity;
    float walk_time;

    int grounded;
    int moving;
} Player;

void player_init(Player *player);

/*
 * Atualiza movimento, gravidade e salto.
 * Recebe o terreno e os objetos do mundo via parâmetros de callback:
 *   - ground_y: elevação do terreno na posição do jogador.
 *   - px, pz após colisão com objetos (já ajustados por world_collide_player).
 */
void player_update(
    Player *player,
    const SceCtrlData *pad,
    float delta_time,
    float ground_y
);

/*
 * Desenha o personagem:
 *   - Se anim != NULL && anim->loaded: usa animação esquelética AXS1.
 *   - Se model != NULL && model->loaded: usa modelo AXP3 estático.
 *   - Senão: personagem provisório de caixas.
 */
void player_draw(
    const Player  *player,
    const P3DModel *model,
    P3DAnim        *anim
);

/*
 * Seleciona o clip de animação adequado ao estado do jogador.
 * Chamar após player_update, antes de p3d_anim_update.
 */
void player_select_anim(
    const Player *player,
    P3DAnimState *state
);

void player_draw_ground(void);

#endif
