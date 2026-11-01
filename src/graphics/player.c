/*
 * player.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 02: Personagem 3D, movimento, gravidade e animação.
 * FASE 03: Limites do terreno (clamp).
 * FASE 04: Integração do modelo AXP3 do protagonista.
 */

#include "player.h"

#include <pspgu.h>
#include <pspgum.h>
#include <math.h>

#define DEADZONE 20.0f
#define MOVE_SPEED 2.5f
#define GRAVITY 9.8f
#define JUMP_FORCE 4.5f

/* O terreno tem 100x100 unidades centradas em 0,0.
   Usamos 48 como limite (margem de 2 unidades antes da borda). */
#define TERRAIN_LIMIT 48.0f

typedef struct {
    float x;
    float y;
    float z;
} Vertex;
/* Cubo unitário com seis faces. */
static Vertex __attribute__((aligned(16))) box_vertices[] = {
    /* Frente */
    {-1,-1, 1}, { 1,-1, 1}, { 1, 1, 1},
    {-1,-1, 1}, { 1, 1, 1}, {-1, 1, 1},

    /* Trás */
    { 1,-1,-1}, {-1,-1,-1}, {-1, 1,-1},
    { 1,-1,-1}, {-1, 1,-1}, { 1, 1,-1},

    /* Topo */
    {-1, 1, 1}, { 1, 1, 1}, { 1, 1,-1},
    {-1, 1, 1}, { 1, 1,-1}, {-1, 1,-1},

    /* Base */
    {-1,-1,-1}, { 1,-1,-1}, { 1,-1, 1},
    {-1,-1,-1}, { 1,-1, 1}, {-1,-1, 1},

    /* Direita */
    {1,-1, 1}, {1,-1,-1}, {1, 1,-1},
    {1,-1, 1}, {1, 1,-1}, {1, 1, 1},

    /* Esquerda */
    {-1,-1,-1}, {-1,-1, 1}, {-1, 1, 1},
    {-1,-1,-1}, {-1, 1, 1}, {-1, 1,-1}
};

/* Plano de chão. */
static Vertex __attribute__((aligned(16))) ground_vertices[] = {
    {-20,0,-20},
    { 20,0,-20},
    { 20,0, 20},

    {-20,0,-20},
    { 20,0, 20},
    {-20,0, 20}
};

/* Desenha uma caixa com uma cor uniforme. */
static void draw_box(
    float x, float y, float z,
    float sx, float sy, float sz,
    float rotation_x,
    unsigned int color
) {
    ScePspFVector3 position = {x, y, z};
    ScePspFVector3 scale = {sx, sy, sz};

    ScePspFQuaternion rotation;

    float half = rotation_x * 0.5f;

    rotation.x = sinf(half);
    rotation.y = 0.0f;
    rotation.z = 0.0f;
    rotation.w = cosf(half);

    sceGumPushMatrix();

    sceGumTranslate(&position);
    sceGumRotate(&rotation);
    sceGumScale(&scale);

    sceGuColor(color);

    sceGumDrawArray(
        GU_TRIANGLES,
        GU_VERTEX_32BITF | GU_TRANSFORM_3D,
        36,
        NULL,
        box_vertices
    );

    sceGumPopMatrix();
}

/* Inicialização do personagem. */
void player_init(Player *player) {
    player->x = 0.0f;
    player->y = 0.0f;
    player->z = 0.0f;

    player->yaw = 0.0f;

    player->vertical_velocity = 0.0f;
    player->walk_time = 0.0f;

    player->grounded = 1;
    player->moving = 0;
}

/* Movimento, salto e gravidade. */
void player_update(
    Player *player,
    const SceCtrlData *pad,
    float delta_time
) {
    float axis_x = ((float)pad->Lx - 128.0f) / 127.0f;
    float axis_z = ((float)pad->Ly - 128.0f) / 127.0f;

    if (fabsf(axis_x) < DEADZONE / 127.0f)
        axis_x = 0.0f;

    if (fabsf(axis_z) < DEADZONE / 127.0f)
        axis_z = 0.0f;

    float length = sqrtf(
        axis_x * axis_x +
        axis_z * axis_z
    );

    if (length > 1.0f) {
        axis_x /= length;
        axis_z /= length;
    }

    player->moving = (length > 0.05f);

    if (player->moving) {
        player->x += axis_x * MOVE_SPEED * delta_time;
        player->z += axis_z * MOVE_SPEED * delta_time;

        player->yaw = atan2f(axis_x, axis_z);

        player->walk_time += delta_time * 9.0f;
    } else {
        player->walk_time = 0.0f;
    }

    /* Limites do terreno: impedir saída da área explorável. */
    if (player->x >  TERRAIN_LIMIT) player->x =  TERRAIN_LIMIT;
    if (player->x < -TERRAIN_LIMIT) player->x = -TERRAIN_LIMIT;
    if (player->z >  TERRAIN_LIMIT) player->z =  TERRAIN_LIMIT;
    if (player->z < -TERRAIN_LIMIT) player->z = -TERRAIN_LIMIT;

    /* Salto: botão Círculo. */
    if ((pad->Buttons & PSP_CTRL_CIRCLE) && player->grounded) {
        player->vertical_velocity = JUMP_FORCE;
        player->grounded = 0;
    }

    /* Aplicar gravidade. */
    if (!player->grounded) {
        player->vertical_velocity -= GRAVITY * delta_time;

        player->y += player->vertical_velocity * delta_time;
    }

    /* Impedir que o personagem atravesse o chão. */
    if (player->y <= 0.0f) {
        player->y = 0.0f;
        player->vertical_velocity = 0.0f;
        player->grounded = 1;
    }
}

/* Desenhar o personagem. */
void player_draw(const Player *player, const P3DModel *model) {

    ScePspFQuaternion body_rotation;

    float half = player->yaw * 0.5f;

    body_rotation.x = 0.0f;
    body_rotation.y = sinf(half);
    body_rotation.z = 0.0f;
    body_rotation.w = cosf(half);

    ScePspFVector3 body_position = {
        player->x,
        player->y,
        player->z
    };

    sceGumMatrixMode(GU_MODEL);
    sceGumPushMatrix();

    sceGumTranslate(&body_position);
    sceGumRotate(&body_rotation);

    /* Se o modelo AXP3 estiver carregado, usá-lo. */
    if (model && model->loaded) {

        p3d_model_draw(model);

    } else {

        /* Personagem provisório: caixas geométricas. */
        float swing = 0.0f;

        if (player->moving && player->grounded) {
            swing = sinf(player->walk_time) * 0.45f;
        }

        /* Pernas. */
        draw_box(
            -0.25f, 0.40f, 0,
            0.17f, 0.40f, 0.18f,
            swing,
            0xFF3030FF
        );

        draw_box(
            0.25f, 0.40f, 0,
            0.17f, 0.40f, 0.18f,
            -swing,
            0xFF3030FF
        );

        /* Tronco. */
        draw_box(
            0, 1.15f, 0,
            0.42f, 0.55f, 0.25f,
            0,
            0xFF20A0E0
        );

        /* Cabeça. */
        draw_box(
            0, 1.95f, 0,
            0.30f, 0.30f, 0.30f,
            0,
            0xFFE0B080
        );

        /* Braços. */
        draw_box(
            -0.55f, 1.15f, 0,
            0.15f, 0.48f, 0.16f,
            -swing,
            0xFF20A0E0
        );

        draw_box(
            0.55f, 1.15f, 0,
            0.15f, 0.48f, 0.16f,
            swing,
            0xFF20A0E0
        );
    }

    sceGumPopMatrix();
}

/* Desenhar o chão. */
void player_draw_ground(void) {
    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();

    sceGuColor(0xFF555555);

    sceGumDrawArray(
        GU_TRIANGLES,
        GU_VERTEX_32BITF | GU_TRANSFORM_3D,
        6,
        NULL,
        ground_vertices
    );
}
