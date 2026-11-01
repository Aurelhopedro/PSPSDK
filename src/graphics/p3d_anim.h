/*
 * p3d_anim.h — RPG Axel Digital
 * FASE 05 — Sistema de animação esquelética para PSP.
 *
 * Formato AXS1 (Axel Skeleton v1):
 *
 * Cabeçalho (AXS1Header, 32 bytes):
 *   magic[4]       "AXS1"
 *   version        1
 *   bone_count     número de ossos (max 24)
 *   vertex_count   número de vértices skinned
 *   clip_count     número de clips de animação
 *
 * Secção de ossos (bone_count × AXS1Bone, 48 bytes cada):
 *   name[16]       nome do osso
 *   parent_index   índice do pai (-1 = raiz)
 *   bind_pos[3]    posição de bind em local space (float×3)
 *   bind_rot[4]    rotação de bind como quaternião (float×4)
 *
 * Secção de vértices skinned (vertex_count × AXS1Vertex, 64 bytes):
 *   u, v           UV (float×2)
 *   nx, ny, nz     normal (float×3)
 *   px, py, pz     posição bind (float×3)
 *   bone_idx[4]    índices dos 4 ossos influentes (unsigned char×4)
 *   weight[4]      pesos normalizados (float×4, soma=1.0)
 *
 * Secção de clips (clip_count × AXS1Clip):
 *   name[16]       nome do clip
 *   frame_count    número de frames
 *   fps            frames por segundo (float)
 *   Seguido de frame_count × bone_count × AXS1Key (32 bytes cada):
 *     rot[4]       quaternião de rotação (float×4)
 *     pos[3]       tradução local (float×3)
 *     pad          (float×1, alinhamento)
 *
 * O loader devolve ponteiros para os dados em memória
 * alinhada a 16 bytes. A interpolação LERP entre keyframes
 * é realizada por p3d_anim_update() a cada frame.
 */

#ifndef P3D_ANIM_H
#define P3D_ANIM_H

#include <pspgu.h>
#include <pspgum.h>

/* ------------------------------------------------------------------ */
/* Limites                                                             */
/* ------------------------------------------------------------------ */

#define AXS1_MAX_BONES    24
#define AXS1_MAX_CLIPS    8
#define AXS1_BONE_WEIGHTS 4   /* pesos por vértice */

/* ------------------------------------------------------------------ */
/* Estruturas em memória                                               */
/* ------------------------------------------------------------------ */

typedef struct {
    char  name[16];
    int   parent_index;
    float bind_pos[3];
    float bind_rot[4];  /* quaternião xyzw */
} AXS1Bone;

typedef struct {
    float u, v;
    float nx, ny, nz;
    float px, py, pz;
    unsigned char bone_idx[AXS1_BONE_WEIGHTS];
    float         weight[AXS1_BONE_WEIGHTS];
} AXS1Vertex;

typedef struct {
    float rot[4];   /* quaternião xyzw */
    float pos[3];
    float pad;
} AXS1Key;

typedef struct {
    char  name[16];
    int   frame_count;
    float fps;
    /*
     * keys[frame][bone] — ponteiro para o bloco contíguo de keys.
     * Armazenado como flat array: keys[frame * bone_count + bone].
     */
    AXS1Key *keys;
} AXS1Clip;

/* ------------------------------------------------------------------ */
/* Modelo animado completo                                            */
/* ------------------------------------------------------------------ */

typedef struct {
    /* Geometria. */
    AXS1Vertex *vertices;
    unsigned int vertex_count;

    /* Esqueleto. */
    AXS1Bone bones[AXS1_MAX_BONES];
    int       bone_count;

    /* Clips. */
    AXS1Clip clips[AXS1_MAX_CLIPS];
    int       clip_count;

    /* Buffer de vértices transformados (skinning CPU). */
    void        *skin_buffer;   /* GU_TEXTURE_32BITF|NORMAL|VERTEX, 32B/v */
    unsigned int skin_size;

    /* Bloco de memória alocado pelo loader. */
    void *raw_data;

    int loaded;
} P3DAnim;

/* ------------------------------------------------------------------ */
/* Índices de clip convencionais                                       */
/* ------------------------------------------------------------------ */

#define CLIP_IDLE  0
#define CLIP_WALK  1
#define CLIP_RUN   2
#define CLIP_JUMP  3
#define CLIP_LAND  4

/* ------------------------------------------------------------------ */
/* Estado de reprodução                                               */
/* ------------------------------------------------------------------ */

typedef struct {
    int   clip_index;   /* clip atual */
    float time;         /* tempo em segundos dentro do clip */
    float blend_time;   /* tempo de blend entre clips (não usado na F05) */
    int   loop;         /* 1 = loop contínuo */
} P3DAnimState;

/* ------------------------------------------------------------------ */
/* Interface pública                                                   */
/* ------------------------------------------------------------------ */

/* Inicializa a estrutura. */
void p3d_anim_init(P3DAnim *anim);

/* Carrega um ficheiro AXS1. Devolve 1 em sucesso, 0 em falha. */
int  p3d_anim_load(P3DAnim *anim, const char *path);

/* Liberta toda a memória. */
void p3d_anim_unload(P3DAnim *anim);

/*
 * Avança o estado de animação por delta_time segundos.
 * Interpola keyframes e aplica skinning CPU → skin_buffer.
 * Deve ser chamada uma vez por frame antes de p3d_anim_draw.
 */
void p3d_anim_update(P3DAnim *anim, P3DAnimState *state, float delta_time);

/*
 * Envia skin_buffer para o GE usando sceGumDrawArray.
 * A matriz GU_MODEL corrente é aplicada (posição/rotação do jogador).
 */
void p3d_anim_draw(const P3DAnim *anim);

/*
 * Muda para um clip pelo índice.
 * Se já estiver a reproduzir o mesmo clip, não reinicia.
 */
void p3d_anim_set_clip(P3DAnimState *state, int clip_index, int loop);

/* Inicializa o estado de animação no clip idle em loop. */
void p3d_anim_state_init(P3DAnimState *state);

#endif /* P3D_ANIM_H */
