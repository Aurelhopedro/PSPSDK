/*
 * player.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 02: Personagem 3D, movimento e animação.
 */

#include "player.h"

#include <pspgu.h>
#include <pspgum.h>
#include <math.h>

#define PI 3.14159265358979323846f
#define DEADZONE 20.0f
#define MOVE_SPEED 2.5f
#define GRAVITY 9.8f

typedef struct {
    unsigned int color;
    float x, y, z;
} __attribute__((aligned(16))) Vertex;

/* Cubo unitário com seis faces. */
static Vertex __attribute__((aligned(16))) box_vertices[] = {
    /* Frente */
    {0xFF3030FF,-1,-1, 1}, {0xFF3030FF,1,-1,1},
    {0xFF3030FF,1,1,1},
    {0xFF3030FF,-1,-1,1}, {0xFF3030FF,1,1,1},
    {0xFF3030FF,-1,1,1},

    /* Trás */
    {0xFF30FF30,1,-1,-1}, {0xFF30FF30,-1,-1,-1},
    {0xFF30FF30,-1,1,-1},
    {0xFF30FF30,1,-1,-1}, {0xFF30FF30,-1,1,-1},
    {0xFF30FF30,1,1,-1},

    /* Topo */
    {0xFFFF4040,-1,1,1}, {0xFFFF4040,1,1,1},
    {0xFFFF4040,1,1,-1},
    {0xFFFF4040,-1,1,1}, {0xFFFF4040,1,1,-1},
    {0xFFFF4040,-1,1,-1},

    /* Base */
    {0xFF40FFFF,-1,-1,-1}, {0xFF40FFFF,1,-1,-1},
    {0xFF40FFFF,1,-1,1},
    {0xFF40FFFF,-1,-1,-1}, {0xFF40FFFF,1,-1,1},
    {0xFF40FFFF,-1,-1,1},

    /* Direita */
    {0xFFFF40FF,1,-1,1}, {0xFFFF40FF,1,-1,-1},
    {0xFFFF40FF,1,1,-1},
    {0xFFFF40FF,1,-1,1}, {0xFFFF40FF,1,1,-1},
    {0xFFFF40FF,1,1,1},

    /* Esquerda */
    {0xFFFFFF40,-1,-1,-1}, {0xFFFFFF40,-1,-1,1},
    {0xFFFFFF40,-1,1,1},
    {0xFFFFFF40,-1,-1,-1}, {0xFFFFFF40,-1,1,1},
    {0xFFFFFF40,-1,1,-1}
};

/* Plano de chão. */
static Vertex __attribute__((aligned(16))) ground_vertices[] = {
    {0xFF555555,-20,0,-20},
    {0xFF555555, 20,0,-20},
    {0xFF555555, 20,0, 20},

    {0xFF555555,-20,0,-20},
    {0xFF555555, 20,0, 20},
    {0xFF555555,-20,0, 20}
};

static void draw_box(
    float x, float y, float z,
    float sx, float sy, float sz,
    float rotation_x,
    unsigned int color
) {
    ScePspFVector3 position = {x,y,z};
    ScePspFVector3 scale = {sx,sy,sz};

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
        GU_COLOR_8888 |
        GU_VERTEX_32BITF |
        GU_TRANSFORM_3D,
        36,
        NULL,
        box_vertices
    );

    sceGumPopMatrix();
}

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

    float length = sqrtf(axis_x * axis_x + axis_z * axis_z);

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

    /* Gravidade simples e contacto com o chão. */
    if (!player->grounded) {
        player->vertical_velocity -= GRAVITY * delta_time;
        player->y += player->vertical_velocity * delta_time;
    }

    if (player->y <= 0.0f) {
        player->y = 0.0f;
        player->vertical_velocity = 0.0f;
        player->grounded = 1;
    }
}

void player_draw(const Player *player) {
    float swing = 0.0f;

    if (player->moving)
        swing = sinf(player->walk_time) * 0.45f;

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

    /* Pernas */
    draw_box(-0.25f,0.40f,0,0.17f,0.40f,0.18f,
             swing,0xFF3030FF);

    draw_box(0.25f,0.40f,0,0.17f,0.40f,0.18f,
             -swing,0xFF3030FF);

    /* Tronco */
    draw_box(0,1.15f,0,0.42f,0.55f,0.25f,
             0,0xFF20A0E0);

    /* Cabeça */
    draw_box(0,1.95f,0,0.30f,0.30f,0.30f,
             0,0xFFE0B080);

    /* Braços */
    draw_box(-0.55f,1.15f,0,0.15f,0.48f,0.16f,
             -swing,0xFF20A0E0);

    draw_box(0.55f,1.15f,0,0.15f,0.48f,0.16f,
             swing,0xFF20A0E0);

    sceGumPopMatrix();
}

void player_draw_ground(void) {
    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();

    sceGuColor(0xFFFFFFFF);

    sceGumDrawArray(
        GU_TRIANGLES,
        GU_COLOR_8888 |
        GU_VERTEX_32BITF |
        GU_TRANSFORM_3D,
        6,
        NULL,
        ground_vertices
    );
}
