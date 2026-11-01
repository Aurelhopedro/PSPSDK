/*
 * p3d_anim.h — RPG Axel Digital
 * FASE 05.1 — Formato AXS1 corrigido: layout binário explícito,
 *             inverse bind pose, convenção column-major consistente.
 *
 * ================================================================
 * LAYOUT BINÁRIO AXS1 — ESPECIFICAÇÃO DEFINITIVA
 * ================================================================
 *
 * Todos os campos são little-endian. Sem padding implícito entre
 * secções — o conversor DEVE respeitar os tamanhos abaixo.
 *
 * [AXS1Header — 32 bytes]
 *   Offset  0: magic[4]         "AXS1"
 *   Offset  4: version          uint32  (deve ser 1)
 *   Offset  8: bone_count       uint32  (1..AXS1_MAX_BONES)
 *   Offset 12: vertex_count     uint32  (>0)
 *   Offset 16: clip_count       uint32  (1..AXS1_MAX_CLIPS)
 *   Offset 20: reserved[3]      uint32×3 (zeros)
 *
 * [Secção de ossos — bone_count × 48 bytes]
 *   Offset  0: name[16]         char×16 (null-terminated)
 *   Offset 16: parent_index     int32   (-1 = raiz)
 *   Offset 20: pad[4]           (alinhamento, zeros)  ← NOVO
 *   Offset 24: bind_pos[3]      float×3 (posição local bind)
 *   Offset 36: bind_rot[4]      float×4 (quaternião xyzw bind)
 *   Total: 52 bytes → padded to 56 bytes on-disk
 *   NOTA: AXS1_BONE_ONDISK = 56 bytes (corrigido de 48).
 *
 *   *** CORREÇÃO: layout anterior (48B) estava errado porque
 *   não havia pad entre parent_index e bind_pos, causando
 *   desalinhamento de float[]. O layout correto é 56B. ***
 *
 *   Layout 56B:
 *     name[16] + parent_index(4) + pad(4) + bind_pos(12) + bind_rot(16) = 52
 *     + pad_end(4) = 56B (múltiplo de 16 para alinhamento).
 *
 *   SIMPLIFICAÇÃO: para manter compatibilidade e evitar confusão,
 *   o on-disk usa exatamente sizeof(AXS1BoneOnDisk) = 56B.
 *
 * [Secção de vértices — vertex_count × 52 bytes]
 *   Offset  0: u, v             float×2  (8B)
 *   Offset  8: nx, ny, nz       float×3  (12B)
 *   Offset 20: px, py, pz       float×3  (12B)
 *   Offset 32: bone_idx[4]      uint8×4  (4B)
 *   Offset 36: weight[4]        float×4  (16B)
 *   Total: 52 bytes
 *   AXS1_VERTEX_ONDISK = 52 bytes.
 *   (A declaração anterior de 64B estava errada.)
 *
 * [Secção de clips — clip_count vezes:]
 *   [Cabeçalho do clip — 24 bytes]
 *     Offset  0: name[16]       char×16
 *     Offset 16: frame_count    int32
 *     Offset 20: fps            float
 *   [Keyframes — frame_count × bone_count × 32 bytes]
 *     Offset  0: rot[4]         float×4 (quaternião xyzw)
 *     Offset 16: pos[3]         float×3
 *     Offset 28: pad            float×1
 *     Total: 32 bytes. AXS1_KEY_ONDISK = 32 bytes (correto).
 *
 * ================================================================
 * CONVENÇÃO DE MATRIZES
 * ================================================================
 * Column-major, igual ao OpenGL e PSP GU.
 * m[col*4 + row], ou seja:
 *   m[0..3]  = coluna 0 (eixo X + 0)
 *   m[4..7]  = coluna 1 (eixo Y + 0)
 *   m[8..11] = coluna 2 (eixo Z + 0)
 *   m[12..15]= coluna 3 (translação + 1)
 * ================================================================
 */

#ifndef P3D_ANIM_H
#define P3D_ANIM_H

#include <pspgu.h>
#include <pspgum.h>

/* ------------------------------------------------------------------ */
/* Limites                                                             */
/* ------------------------------------------------------------------ */

#define AXS1_MAX_BONES     24
#define AXS1_MAX_CLIPS      8
#define AXS1_BONE_WEIGHTS   4

/* Tamanhos on-disk (usados pelo loader e pelo conversor). */
#define AXS1_HEADER_SIZE    32
#define AXS1_BONE_ONDISK    56   /* ver especificação acima */
#define AXS1_VERTEX_ONDISK  52   /* ver especificação acima */
#define AXS1_CLIP_HDR_SIZE  24
#define AXS1_KEY_ONDISK     32

#define AXS1_VERSION         1
#define AXS1_MAX_VERTICES 8192   /* limite de segurança */

/* ------------------------------------------------------------------ */
/* Estruturas em memória (usadas apenas em runtime)                   */
/* Não devem ser usadas diretamente com sizeof() para I/O.            */
/* ------------------------------------------------------------------ */

/* Vértice em memória após load (campos acessíveis por nome). */
typedef struct {
    float u, v;
    float nx, ny, nz;
    float px, py, pz;
    unsigned char bone_idx[AXS1_BONE_WEIGHTS];
    float         weight[AXS1_BONE_WEIGHTS];
} AXS1Vertex;
/* sizeof(AXS1Vertex) ≈ 52B em MIPS/PSP sem padding extra. */

/* Osso em memória. */
typedef struct {
    char  name[16];
    int   parent_index;
    float bind_pos[3];
    float bind_rot[4];   /* quaternião xyzw */
} AXS1Bone;

/* Keyframe em memória. */
typedef struct {
    float rot[4];   /* quaternião xyzw */
    float pos[3];
} AXS1Key;

/* Clip em memória. */
typedef struct {
    char     name[16];
    int      frame_count;
    float    fps;
    AXS1Key *keys;   /* flat array: keys[frame * bone_count + bone] */
} AXS1Clip;

/* Vértice de saída para o GE (UV + Normal + Posição = 32 bytes). */
typedef struct {
    float u, v;
    float nx, ny, nz;
    float px, py, pz;
} AXS1SkinVtx;

/* ------------------------------------------------------------------ */
/* Modelo animado completo                                             */
/* ------------------------------------------------------------------ */

typedef struct {
    /* Geometria (apontadores para raw_data). */
    AXS1Vertex  *vertices;
    unsigned int vertex_count;

    /* Esqueleto. */
    AXS1Bone bones[AXS1_MAX_BONES];
    int       bone_count;

    /* Inverse bind pose matrices (column-major, 4×4). */
    float inv_bind[AXS1_MAX_BONES][16];

    /* Clips. */
    AXS1Clip clips[AXS1_MAX_CLIPS];
    int      clip_count;

    /* Buffer de vértices skinned para o GE. */
    AXS1SkinVtx *skin_buffer;
    unsigned int skin_size;

    /* Bloco de memória alocado. */
    void *raw_data;
    unsigned int raw_size;

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
/* Estado de reprodução                                                */
/* ------------------------------------------------------------------ */

typedef struct {
    int   clip_index;
    float time;
    int   loop;
    int   prev_grounded;   /* para detetar transição terra→ar */
    int   landing;         /* 1 enquanto reproduz CLIP_LAND (sem loop) */
} P3DAnimState;

/* ------------------------------------------------------------------ */
/* Interface pública                                                   */
/* ------------------------------------------------------------------ */

void p3d_anim_init(P3DAnim *anim);
int  p3d_anim_load(P3DAnim *anim, const char *path);
void p3d_anim_unload(P3DAnim *anim);

void p3d_anim_update(P3DAnim *anim, P3DAnimState *state, float delta_time);
void p3d_anim_draw(const P3DAnim *anim);

/*
 * Muda para clip_index apenas se diferente do clip atual.
 * loop: 1 = repetir, 0 = reproduzir uma vez e manter último frame.
 */
void p3d_anim_set_clip(P3DAnimState *state, int clip_index, int loop);

/* Inicializa estado em CLIP_IDLE com loop. */
void p3d_anim_state_init(P3DAnimState *state);

#endif /* P3D_ANIM_H */
