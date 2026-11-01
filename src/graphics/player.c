/*
 * player.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 02: Personagem 3D, movimento, gravidade e animação.
 * FASE 03: Limites do terreno (clamp).
 * FASE 04: Integração do modelo AXP3 do protagonista.
 * FASE 04.1: Corrigida matriz GU_MODEL; adicionada escala e
 *            LoadIdentity antes do push para evitar contaminação
 *            por matrizes do terreno ou da câmara.
 */

#include "player.h"

#include <pspgu.h>
#include <pspgum.h>
#include <math.h>

#define DEADZONE     20.0f
#define MOVE_SPEED    2.5f
#define GRAVITY       9.8f
#define JUMP_FORCE    4.5f

/* O terreno tem 100x100 unidades centradas em 0,0.
   Usamos 48 como limite (margem de 2 unidades antes da borda). */
#define TERRAIN_LIMIT 48.0f

/*
 * Escala aplicada ao modelo AXP3.
 * Ajustar se o modelo exportado tiver dimensões muito diferentes
 * do personagem provisório (altura ~2 unidades de mundo).
 */
#define MODEL_SCALE 1.0f

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
    { 1,-1, 1}, { 1,-1,-1}, { 1, 1,-1},
    { 1,-1, 1}, { 1, 1,-1}, { 1, 1, 1},

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
    ScePspFVector3 scale    = {sx, sy, sz};

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

/* -------------------------------------------------- */
/* INICIALIZAÇÃO                                      */
/* -------------------------------------------------- */

void player_init(Player *player) {
    player->x = 0.0f;
    player->y = 0.0f;
    player->z = 0.0f;

    player->yaw = 0.0f;

    player->vertical_velocity = 0.0f;
    player->walk_time          = 0.0f;

    player->grounded = 1;
    player->moving   = 0;
}

/* -------------------------------------------------- */
/* ATUALIZAÇÃO                                        */
/* -------------------------------------------------- */

void player_update(
    Player *player,
    const SceCtrlData *pad,
    float delta_time
) {
    float axis_x = ((float)pad->Lx - 128.0f) / 127.0f;
    float axis_z = ((float)pad->Ly - 128.0f) / 127.0f;

    if (fabsf(axis_x) < DEADZONE / 127.0f) axis_x = 0.0f;
    if (fabsf(axis_z) < DEADZONE / 127.0f) axis_z = 0.0f;

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

    /* Limites do terreno. */
    if (player->x >  TERRAIN_LIMIT) player->x =  TERRAIN_LIMIT;
    if (player->x < -TERRAIN_LIMIT) player->x = -TERRAIN_LIMIT;
    if (player->z >  TERRAIN_LIMIT) player->z =  TERRAIN_LIMIT;
    if (player->z < -TERRAIN_LIMIT) player->z = -TERRAIN_LIMIT;

    /* Salto: botão Círculo. */
    if ((pad->Buttons & PSP_CTRL_CIRCLE) && player->grounded) {
        player->vertical_velocity = JUMP_FORCE;
        player->grounded = 0;
    }

    /* Gravidade. */
    if (!player->grounded) {
        player->vertical_velocity -= GRAVITY * delta_time;
        player->y += player->vertical_velocity * delta_time;
    }

    /* Chão. */
    if (player->y <= 0.0f) {
        player->y = 0.0f;
        player->vertical_velocity = 0.0f;
        player->grounded = 1;
    }
}

/* -------------------------------------------------- */
/* DESENHAR PERSONAGEM                                */
/* -------------------------------------------------- */
/*
 * CORREÇÃO FASE 04.1:
 *
 * 1. sceGumMatrixMode(GU_MODEL) seguido de sceGumLoadIdentity()
 *    garante que a matriz parte de um estado limpo, sem
 *    contaminação por transformações do terreno ou da câmara.
 *
 * 2. sceGumPushMatrix() empilha essa identidade limpa.
 *    Translate + Rotate aplicam posição e yaw do jogador.
 *
 * 3. Para o modelo AXP3: sceGumScale() aplica MODEL_SCALE
 *    antes de chamar p3d_model_draw(), que usa sceGumDrawArray
 *    e respeita a matriz corrente.
 *
 * 4. Fallback: personagem provisório em caso de falha de
 *    carregamento, com tint vermelho para diagnóstico visual.
 */

void player_draw(const Player *player, const P3DModel *model) {

    /* Posição do jogador no mundo. */
    ScePspFVector3 pos = {
        player->x,
        player->y,
        player->z
    };

    /* Rotação yaw como quaternião em torno do eixo Y. */
    ScePspFQuaternion rot;
    float half = player->yaw * 0.5f;
    rot.x = 0.0f;
    rot.y = sinf(half);
    rot.z = 0.0f;
    rot.w = cosf(half);

    /*
     * Inicializar a matriz MODEL com identidade antes de push.
     * Evita que transformações residuais do terreno ou da câmara
     * contaminem a posição do personagem.
     */
    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();
    sceGumPushMatrix();

    sceGumTranslate(&pos);
    sceGumRotate(&rot);

    if (model && model->loaded) {

        /* Escala uniforme para o modelo AXP3. */
        ScePspFVector3 scale = {
            MODEL_SCALE,
            MODEL_SCALE,
            MODEL_SCALE
        };
        sceGumScale(&scale);

        p3d_model_draw(model);

    } else {

        /*
         * Personagem provisório.
         * Tint vermelho indica falha de carregamento do modelo;
         * cores normais indicam que nunca foi tentado o load
         * (model == NULL) ou que está em uso deliberado.
         */
        unsigned int leg_color  = 0xFF3030FF;
        unsigned int body_color = 0xFF20A0E0;
        unsigned int head_color = 0xFFE0B080;

        if (model && !model->loaded) {
            /* Falhou o carregamento: tint vermelho. */
            leg_color  = 0xFF2020CC;
            body_color = 0xFF2020CC;
            head_color = 0xFF4040CC;
        }

        float swing = 0.0f;
        if (player->moving && player->grounded)
            swing = sinf(player->walk_time) * 0.45f;

        /* Pernas. */
        draw_box(-0.25f, 0.40f, 0, 0.17f, 0.40f, 0.18f,  swing, leg_color);
        draw_box( 0.25f, 0.40f, 0, 0.17f, 0.40f, 0.18f, -swing, leg_color);

        /* Tronco. */
        draw_box(0, 1.15f, 0, 0.42f, 0.55f, 0.25f, 0, body_color);

        /* Cabeça. */
        draw_box(0, 1.95f, 0, 0.30f, 0.30f, 0.30f, 0, head_color);

        /* Braços. */
        draw_box(-0.55f, 1.15f, 0, 0.15f, 0.48f, 0.16f, -swing, body_color);
        draw_box( 0.55f, 1.15f, 0, 0.15f, 0.48f, 0.16f,  swing, body_color);
    }

    sceGumPopMatrix();
}

/* -------------------------------------------------- */
/* DESENHAR O CHÃO                                    */
/* -------------------------------------------------- */

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
