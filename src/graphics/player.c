/*
 * player.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 02: Personagem 3D, movimento, gravidade e animação.
 * FASE 03: Limites do terreno (clamp).
 * FASE 04: Integração do modelo AXP3, correção de matrizes GUM.
 * FASE 05: Suporte a relevo (ground_y), animação AXS1,
 *          seleção de clips por estado do jogador.
 * FASE 05.1: Deteção de aterragem (LAND), transição correta
 *            salto→land→idle/walk.
 */

#include "player.h"

#include <pspgu.h>
#include <pspgum.h>
#include <math.h>

/* ------------------------------------------------------------------ */
/* Constantes de movimento                                             */
/* ------------------------------------------------------------------ */

#define DEADZONE     20.0f
#define MOVE_SPEED    2.5f
#define GRAVITY       9.8f
#define JUMP_FORCE    4.5f
#define TERRAIN_LIMIT 48.0f

/*
 * Escala do modelo AXP3 / AXS1.
 * Ajustar se o modelo exportado tiver dimensões diferentes
 * do personagem provisório (altura ~2 unidades).
 */
#define MODEL_SCALE 1.0f

/* ------------------------------------------------------------------ */
/* Geometria do personagem provisório                                  */
/* ------------------------------------------------------------------ */

typedef struct { float x, y, z; } Vertex;

static Vertex __attribute__((aligned(16))) box_vertices[] = {
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

static Vertex __attribute__((aligned(16))) ground_vertices[] = {
    {-20,0,-20},{ 20,0,-20},{ 20,0, 20},
    {-20,0,-20},{ 20,0, 20},{-20,0, 20}
};

/* ------------------------------------------------------------------ */
/* Auxiliar: desenhar caixa                                            */
/* ------------------------------------------------------------------ */

static void draw_box(
    float x, float y, float z,
    float sx, float sy, float sz,
    float rotation_x,
    unsigned int color
) {
    ScePspFVector3 position = {x, y, z};
    ScePspFVector3 scale    = {sx, sy, sz};
    ScePspFQuaternion rot;
    float half = rotation_x * 0.5f;
    rot.x = sinf(half); rot.y = 0; rot.z = 0; rot.w = cosf(half);

    sceGumPushMatrix();
    sceGumTranslate(&position);
    sceGumRotate(&rot);
    sceGumScale(&scale);
    sceGuColor(color);
    sceGumDrawArray(
        GU_TRIANGLES,
        GU_VERTEX_32BITF | GU_TRANSFORM_3D,
        36, NULL, box_vertices
    );
    sceGumPopMatrix();
}

/* ------------------------------------------------------------------ */
/* player_init                                                         */
/* ------------------------------------------------------------------ */

void player_init(Player *player) {
    player->x = 0.0f; player->y = 0.0f; player->z = 0.0f;
    player->yaw = 0.0f;
    player->vertical_velocity = 0.0f;
    player->walk_time = 0.0f;
    player->grounded  = 1;
    player->moving    = 0;
    player->was_grounded = 1;
}

/* ------------------------------------------------------------------ */
/* player_update                                                       */
/* ------------------------------------------------------------------ */
/*
 * FASE 05: recebe ground_y (elevação do terreno já calculada
 * externamente por terrain_height_at e corrigida por world_collide).
 * O jogador assenta em ground_y em vez de y=0.
 */

void player_update(
    Player *player,
    const SceCtrlData *pad,
    float delta_time,
    float ground_y
) {
    /* Guardar estado anterior para detetar aterragem. */
    player->was_grounded = player->grounded;

    float axis_x = ((float)pad->Lx - 128.0f) / 127.0f;
    float axis_z = ((float)pad->Ly - 128.0f) / 127.0f;

    if (fabsf(axis_x) < DEADZONE / 127.0f) axis_x = 0.0f;
    if (fabsf(axis_z) < DEADZONE / 127.0f) axis_z = 0.0f;

    float length = sqrtf(axis_x*axis_x + axis_z*axis_z);
    if (length > 1.0f) { axis_x /= length; axis_z /= length; }

    player->moving = (length > 0.05f);

    if (player->moving) {
        player->x += axis_x * MOVE_SPEED * delta_time;
        player->z += axis_z * MOVE_SPEED * delta_time;
        player->yaw = atan2f(axis_x, axis_z);
        player->walk_time += delta_time * 9.0f;
    } else {
        player->walk_time = 0.0f;
    }

    /* Limites do terreno. */
    if (player->x >  TERRAIN_LIMIT) player->x =  TERRAIN_LIMIT;
    if (player->x < -TERRAIN_LIMIT) player->x = -TERRAIN_LIMIT;
    if (player->z >  TERRAIN_LIMIT) player->z =  TERRAIN_LIMIT;
    if (player->z < -TERRAIN_LIMIT) player->z = -TERRAIN_LIMIT;

    /* Salto: só pode saltar se estiver no chão. */
    if ((pad->Buttons & PSP_CTRL_CIRCLE) && player->grounded) {
        player->vertical_velocity = JUMP_FORCE;
        player->grounded = 0;
    }

    /* Gravidade. */
    if (!player->grounded) {
        player->vertical_velocity -= GRAVITY * delta_time;
        player->y += player->vertical_velocity * delta_time;
    }

    /* Assentar no terreno (ground_y em vez de 0). */
    if (player->y <= ground_y) {
        player->y = ground_y;
        player->vertical_velocity = 0.0f;
        player->grounded = 1;
    }
}

/* ------------------------------------------------------------------ */
/* player_select_anim                                                  */
/* ------------------------------------------------------------------ */
/*
 * Escolhe o clip de animação com base no estado do jogador.
 *
 * Prioridades:
 *   1. No ar → JUMP (não reinicia se já está a saltar)
 *   2. Acabou de aterrar → LAND (sem loop, uma vez)
 *   3. Em movimento → WALK
 *   4. Parado → IDLE
 *
 * A deteção de aterragem usa was_grounded:
 *   - No frame anterior: !grounded (estava no ar)
 *   - No frame atual:   grounded  (tocou no chão)
 *   → disparar LAND
 */

void player_select_anim(
    const Player *player,
    P3DAnimState *state
) {
    if (!state) return;

    /* Aterragem: transição ar → chão. */
    int just_landed = (!player->was_grounded && player->grounded);

    if (!player->grounded) {
        /* No ar: JUMP sem loop (reproduz uma vez; frame congela no fim). */
        p3d_anim_set_clip(state, CLIP_JUMP, 0);
        state->landing = 0;
    } else if (just_landed) {
        /* Acabou de aterrar: disparar LAND sem loop. */
        p3d_anim_set_clip(state, CLIP_LAND, 0);
        state->landing = 1;
    } else if (state->landing) {
        /* Continuar LAND até terminar (p3d_anim_update trata de transitar
         * automaticamente para IDLE quando landing=1 e clip termina). */
        /* Não alteramos o clip aqui. */
    } else if (player->moving) {
        p3d_anim_set_clip(state, CLIP_WALK, 1);
    } else {
        p3d_anim_set_clip(state, CLIP_IDLE, 1);
    }
}

/* ------------------------------------------------------------------ */
/* player_draw                                                         */
/* ------------------------------------------------------------------ */

void player_draw(
    const Player  *player,
    const P3DModel *model,
    P3DAnim        *anim
) {
    ScePspFVector3 pos = { player->x, player->y, player->z };

    ScePspFQuaternion rot;
    float half = player->yaw * 0.5f;
    rot.x = 0.0f; rot.y = sinf(half); rot.z = 0.0f; rot.w = cosf(half);

    /* Matriz MODEL limpa antes do push. */
    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();
    sceGumPushMatrix();

    sceGumTranslate(&pos);
    sceGumRotate(&rot);

    /* --- Modelo animado AXS1 (prioridade máxima). --- */
    if (anim && anim->loaded) {

        ScePspFVector3 scale = { MODEL_SCALE, MODEL_SCALE, MODEL_SCALE };
        sceGumScale(&scale);
        p3d_anim_draw(anim);

    /* --- Modelo estático AXP3. --- */
    } else if (model && model->loaded) {

        ScePspFVector3 scale = { MODEL_SCALE, MODEL_SCALE, MODEL_SCALE };
        sceGumScale(&scale);
        p3d_model_draw(model);

    /* --- Personagem provisório de caixas. --- */
    } else {

        unsigned int leg_color  = 0xFF3030FF;
        unsigned int body_color = 0xFF20A0E0;
        unsigned int head_color = 0xFFE0B080;

        /* Tint de diagnóstico: modelo tentado mas falhou. */
        if ((model && !model->loaded) || (anim && !anim->loaded)) {
            leg_color  = 0xFF2020CC;
            body_color = 0xFF2020CC;
            head_color = 0xFF4040CC;
        }

        float swing = 0.0f;
        if (player->moving && player->grounded)
            swing = sinf(player->walk_time) * 0.45f;

        draw_box(-0.25f, 0.40f, 0, 0.17f, 0.40f, 0.18f,  swing, leg_color);
        draw_box( 0.25f, 0.40f, 0, 0.17f, 0.40f, 0.18f, -swing, leg_color);
        draw_box(     0, 1.15f, 0, 0.42f, 0.55f, 0.25f,      0, body_color);
        draw_box(     0, 1.95f, 0, 0.30f, 0.30f, 0.30f,      0, head_color);
        draw_box(-0.55f, 1.15f, 0, 0.15f, 0.48f, 0.16f, -swing, body_color);
        draw_box( 0.55f, 1.15f, 0, 0.15f, 0.48f, 0.16f,  swing, body_color);
    }

    sceGumPopMatrix();
}

/* ------------------------------------------------------------------ */
/* player_draw_ground                                                  */
/* ------------------------------------------------------------------ */

void player_draw_ground(void) {
    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();
    sceGuColor(0xFF555555);
    sceGumDrawArray(
        GU_TRIANGLES,
        GU_VERTEX_32BITF | GU_TRANSFORM_3D,
        6, NULL, ground_vertices
    );
}
