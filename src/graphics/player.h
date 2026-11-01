#ifndef PLAYER_H
#define PLAYER_H

/*
 * player.h — RPG Axel Digital
 * FASE 05   — Suporte a terreno com relevo, colisão com objetos,
 *             e animação esquelética AXS1.
 * FASE 05.1 — Campo was_grounded para detetar aterragem (LAND).
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

    int grounded;       /* 1 se o jogador está no chão */
    int was_grounded;   /* estado de grounded no frame anterior */
    int moving;
} Player;

void player_init(Player *player);

/*
 * Atualiza movimento, gravidade e salto.
 * Recebe:
 *   - pad: estado dos controlos
 *   - delta_time: tempo do frame
 *   - ground_y: elevação do terreno na posição do jogador
 *               (já corrigida por world_collide_player)
 *
 * Internamente guarda was_grounded = grounded antes de atualizar,
 * para que player_select_anim possa detetar a transição ar→chão.
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
 *
 * Lógica:
 *   - No ar              → JUMP (sem loop)
 *   - Acabou de aterrar  → LAND (sem loop, uma vez)
 *   - A reproduzir LAND  → mantém LAND até terminar
 *   - Em movimento       → WALK (com loop)
 *   - Parado             → IDLE (com loop)
 */
void player_select_anim(
    const Player *player,
    P3DAnimState *state
);

void player_draw_ground(void);

#endif
