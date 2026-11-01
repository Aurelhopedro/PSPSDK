/*
 * p3d_anim.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 05 — Sistema de animação esquelética AXS1 para PSP.
 *
 * Pipeline por frame:
 *   1. p3d_anim_update(): interpola keyframes, calcula matrizes
 *      de ossos em world space, aplica skinning CPU aos vértices
 *      bind-pose → skin_buffer.
 *   2. p3d_anim_draw(): envia skin_buffer para o GE com
 *      sceGumDrawArray, respeitando a matriz MODEL do jogador.
 *
 * Skinning CPU é adequado para a PSP com modelos < 1000 vértices.
 * Para modelos maiores, considerar skinning por hardware (VTYPE).
 */

#include "p3d_anim.h"

#include <pspkernel.h>
#include <pspiofilemgr.h>
#include <pspgu.h>
#include <pspgum.h>

#include <malloc.h>
#include <string.h>
#include <math.h>

/* ------------------------------------------------------------------ */
/* Constantes do formato AXS1                                         */
/* ------------------------------------------------------------------ */

#define AXS1_VERSION      1
#define AXS1_VERTEX_SIZE  64   /* bytes por AXS1Vertex */
#define AXS1_KEY_SIZE     32   /* bytes por AXS1Key */
#define AXS1_BONE_SIZE    48   /* bytes por AXS1Bone on-disk */
#define AXS1_CLIP_HDR     24   /* magic16 + frame_count(4) + fps(4) */

/* Vértice de saída para o GE (UV+Normal+Posição, 32 bytes). */
typedef struct {
    float u, v;
    float nx, ny, nz;
    float px, py, pz;
} SkinVertex;

/* ------------------------------------------------------------------ */
/* Matemática de quaterniões (mínima, sem dependências externas)      */
/* ------------------------------------------------------------------ */

static void quat_slerp(
    const float *a, const float *b, float t, float *out
) {
    /* LERP normalizado — adequado para PSP (evita acos). */
    float dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2] + a[3]*b[3];

    float bx = b[0], by = b[1], bz = b[2], bw = b[3];
    if (dot < 0.0f) {
        bx = -bx; by = -by; bz = -bz; bw = -bw;
        dot = -dot;
    }

    float rx = a[0] + t*(bx - a[0]);
    float ry = a[1] + t*(by - a[1]);
    float rz = a[2] + t*(bz - a[2]);
    float rw = a[3] + t*(bw - a[3]);

    float len = sqrtf(rx*rx + ry*ry + rz*rz + rw*rw);
    if (len > 0.0001f) {
        out[0] = rx/len; out[1] = ry/len;
        out[2] = rz/len; out[3] = rw/len;
    } else {
        out[0] = 0; out[1] = 0; out[2] = 0; out[3] = 1;
    }
}

/* Converter quaternião + posição para matriz 4×4 (linha-maior). */
static void quat_to_mat4(
    const float *q, const float *pos, float *m
) {
    float x=q[0], y=q[1], z=q[2], w=q[3];
    float x2=x+x, y2=y+y, z2=z+z;
    float xx=x*x2, yy=y*y2, zz=z*z2;
    float xy=x*y2, xz=x*z2, yz=y*z2;
    float wx=w*x2, wy=w*y2, wz=w*z2;

    /* Linha 0 */
    m[ 0]=1-(yy+zz); m[ 1]=xy+wz;    m[ 2]=xz-wy;    m[ 3]=0;
    /* Linha 1 */
    m[ 4]=xy-wz;    m[ 5]=1-(xx+zz); m[ 6]=yz+wx;    m[ 7]=0;
    /* Linha 2 */
    m[ 8]=xz+wy;    m[ 9]=yz-wx;     m[10]=1-(xx+yy); m[11]=0;
    /* Linha 3: translação */
    m[12]=pos[0];   m[13]=pos[1];    m[14]=pos[2];    m[15]=1;
}

/* Transformar posição por matriz 4×4. */
static void mat4_transform_pos(
    const float *m, const float *v, float *out
) {
    out[0] = m[0]*v[0] + m[4]*v[1] + m[ 8]*v[2] + m[12];
    out[1] = m[1]*v[0] + m[5]*v[1] + m[ 9]*v[2] + m[13];
    out[2] = m[2]*v[0] + m[6]*v[1] + m[10]*v[2] + m[14];
}

/* Transformar normal por matriz 4×4 (sem translação). */
static void mat4_transform_nrm(
    const float *m, const float *n, float *out
) {
    out[0] = m[0]*n[0] + m[4]*n[1] + m[ 8]*n[2];
    out[1] = m[1]*n[0] + m[5]*n[1] + m[ 9]*n[2];
    out[2] = m[2]*n[0] + m[6]*n[1] + m[10]*n[2];
}

/* Multiplicar duas matrizes 4×4. */
static void mat4_mul(
    const float *a, const float *b, float *out
) {
    for (int r = 0; r < 4; r++) {
        for (int c = 0; c < 4; c++) {
            float s = 0;
            for (int k = 0; k < 4; k++)
                s += a[r*4+k] * b[k*4+c];
            out[r*4+c] = s;
        }
    }
}

/* ------------------------------------------------------------------ */
/* p3d_anim_init                                                       */
/* ------------------------------------------------------------------ */

void p3d_anim_init(P3DAnim *anim) {
    if (!anim) return;
    memset(anim, 0, sizeof(*anim));
}

/* ------------------------------------------------------------------ */
/* p3d_anim_state_init                                                 */
/* ------------------------------------------------------------------ */

void p3d_anim_state_init(P3DAnimState *state) {
    if (!state) return;
    state->clip_index  = CLIP_IDLE;
    state->time        = 0.0f;
    state->blend_time  = 0.0f;
    state->loop        = 1;
}

/* ------------------------------------------------------------------ */
/* p3d_anim_set_clip                                                   */
/* ------------------------------------------------------------------ */

void p3d_anim_set_clip(P3DAnimState *state, int clip_index, int loop) {
    if (!state) return;
    if (state->clip_index == clip_index) return;
    state->clip_index = clip_index;
    state->time       = 0.0f;
    state->loop       = loop;
}

/* ------------------------------------------------------------------ */
/* p3d_anim_unload                                                     */
/* ------------------------------------------------------------------ */

void p3d_anim_unload(P3DAnim *anim) {
    if (!anim) return;

    if (anim->skin_buffer) {
        free(anim->skin_buffer);
        anim->skin_buffer = NULL;
    }
    if (anim->raw_data) {
        free(anim->raw_data);
        anim->raw_data = NULL;
    }
    p3d_anim_init(anim);
}

/* ------------------------------------------------------------------ */
/* p3d_anim_load                                                       */
/* ------------------------------------------------------------------ */
/*
 * Estrutura do ficheiro AXS1:
 *   [AXS1Header 32B]
 *   [bone_count × AXS1Bone 48B]
 *   [vertex_count × AXS1Vertex 64B]
 *   para cada clip:
 *     [name 16B][frame_count 4B][fps 4B]
 *     [frame_count × bone_count × AXS1Key 32B]
 */

typedef struct {
    char         magic[4];
    unsigned int version;
    unsigned int bone_count;
    unsigned int vertex_count;
    unsigned int clip_count;
    unsigned int reserved[3];
} AXS1Header;

int p3d_anim_load(P3DAnim *anim, const char *path) {
    if (!anim || !path) return 0;

    p3d_anim_unload(anim);

    SceUID fd = sceIoOpen(path, PSP_O_RDONLY, 0);
    if (fd < 0) return 0;

    /* Ler cabeçalho. */
    AXS1Header hdr;
    if (sceIoRead(fd, &hdr, sizeof(hdr)) != (int)sizeof(hdr)) {
        sceIoClose(fd); return 0;
    }

    if (
        memcmp(hdr.magic, "AXS1", 4) != 0 ||
        hdr.version != AXS1_VERSION ||
        hdr.bone_count == 0 ||
        hdr.bone_count > AXS1_MAX_BONES ||
        hdr.vertex_count == 0 ||
        hdr.clip_count == 0 ||
        hdr.clip_count > AXS1_MAX_CLIPS
    ) {
        sceIoClose(fd); return 0;
    }

    /* Calcular tamanho total do ficheiro para alocar de uma vez. */
    unsigned int bone_bytes   = hdr.bone_count * AXS1_BONE_SIZE;
    unsigned int vtx_bytes    = hdr.vertex_count * AXS1_VERTEX_SIZE;

    /* Precisamos do tamanho total do ficheiro para os clips. */
    int fsize = sceIoLseek32(fd, 0, PSP_SEEK_END);
    if (fsize < 0) { sceIoClose(fd); return 0; }

    unsigned int data_size = (unsigned int)fsize - (unsigned int)sizeof(hdr);

    void *raw = memalign(16, data_size);
    if (!raw) { sceIoClose(fd); return 0; }

    if (sceIoLseek32(fd, sizeof(hdr), PSP_SEEK_SET) < 0) {
        free(raw); sceIoClose(fd); return 0;
    }

    if (sceIoRead(fd, raw, data_size) != (int)data_size) {
        free(raw); sceIoClose(fd); return 0;
    }
    sceIoClose(fd);

    unsigned char *ptr = (unsigned char *)raw;

    /* Bones. */
    anim->bone_count = (int)hdr.bone_count;
    for (int i = 0; i < anim->bone_count; i++) {
        memcpy(&anim->bones[i], ptr, sizeof(AXS1Bone));
        ptr += AXS1_BONE_SIZE;
    }

    /* Vértices. */
    anim->vertices     = (AXS1Vertex *)ptr;
    anim->vertex_count = hdr.vertex_count;
    ptr += vtx_bytes;

    /* Clips. */
    anim->clip_count = (int)hdr.clip_count;
    for (int c = 0; c < anim->clip_count; c++) {
        memcpy(anim->clips[c].name, ptr, 16); ptr += 16;
        memcpy(&anim->clips[c].frame_count, ptr, 4); ptr += 4;
        memcpy(&anim->clips[c].fps, ptr, 4); ptr += 4;

        unsigned int key_bytes =
            (unsigned int)anim->clips[c].frame_count *
            (unsigned int)anim->bone_count * AXS1_KEY_SIZE;

        anim->clips[c].keys = (AXS1Key *)ptr;
        ptr += key_bytes;
    }

    anim->raw_data = raw;

    /* Alocar buffer de skinning. */
    unsigned int skin_sz = hdr.vertex_count * sizeof(SkinVertex);
    anim->skin_buffer = memalign(16, skin_sz);
    if (!anim->skin_buffer) {
        p3d_anim_unload(anim); return 0;
    }
    anim->skin_size = skin_sz;

    sceKernelDcacheWritebackRange(raw, data_size);

    anim->loaded = 1;
    return 1;
}

/* ------------------------------------------------------------------ */
/* p3d_anim_update                                                     */
/* ------------------------------------------------------------------ */
/*
 * 1. Avançar o tempo no clip.
 * 2. Interpolar keyframes.
 * 3. Calcular matrizes de ossos em world space.
 * 4. Calcular inverse-bind e aplicar skinning CPU.
 */

/* Matrizes de osso calculadas por frame (stack local, sem malloc). */
static float bone_mat[AXS1_MAX_BONES][16];

void p3d_anim_update(
    P3DAnim *anim, P3DAnimState *state, float delta_time
) {
    if (!anim || !anim->loaded || !state) return;

    /* Clip válido? */
    if (state->clip_index < 0 || state->clip_index >= anim->clip_count)
        state->clip_index = 0;

    AXS1Clip *clip = &anim->clips[state->clip_index];

    if (clip->frame_count < 1) return;

    /* Avançar tempo. */
    state->time += delta_time;

    float duration = (float)clip->frame_count / clip->fps;
    if (state->loop) {
        while (state->time >= duration)
            state->time -= duration;
        if (state->time < 0.0f) state->time = 0.0f;
    } else {
        if (state->time > duration) state->time = duration;
    }

    /* Frame de interpolação. */
    float frame_f  = state->time * clip->fps;
    int   frame_a  = (int)frame_f;
    float blend    = frame_f - (float)frame_a;

    int frame_b = frame_a + 1;
    if (frame_b >= clip->frame_count) {
        frame_b = state->loop ? 0 : clip->frame_count - 1;
    }
    if (frame_a >= clip->frame_count)
        frame_a = clip->frame_count - 1;

    /* Calcular matrizes de osso. */
    for (int b = 0; b < anim->bone_count; b++) {
        AXS1Key *ka = &clip->keys[frame_a * anim->bone_count + b];
        AXS1Key *kb = &clip->keys[frame_b * anim->bone_count + b];

        float rot[4], pos[3];
        quat_slerp(ka->rot, kb->rot, blend, rot);

        pos[0] = ka->pos[0] + blend * (kb->pos[0] - ka->pos[0]);
        pos[1] = ka->pos[1] + blend * (kb->pos[1] - ka->pos[1]);
        pos[2] = ka->pos[2] + blend * (kb->pos[2] - ka->pos[2]);

        float local[16];
        quat_to_mat4(rot, pos, local);

        int par = anim->bones[b].parent_index;
        if (par < 0) {
            memcpy(bone_mat[b], local, sizeof(local));
        } else {
            mat4_mul(bone_mat[par], local, bone_mat[b]);
        }
    }

    /* Skinning CPU: transformar cada vértice. */
    SkinVertex *out = (SkinVertex *)anim->skin_buffer;

    for (unsigned int v = 0; v < anim->vertex_count; v++) {
        AXS1Vertex *sv = &anim->vertices[v];

        float px = 0, py = 0, pz = 0;
        float nx = 0, ny = 0, nz = 0;

        for (int w = 0; w < AXS1_BONE_WEIGHTS; w++) {
            float wt = sv->weight[w];
            if (wt < 0.0001f) continue;

            int bi = sv->bone_idx[w];
            if (bi >= anim->bone_count) continue;

            float tp[3], tn[3];
            float bp[3] = { sv->px, sv->py, sv->pz };
            float bn[3] = { sv->nx, sv->ny, sv->nz };

            mat4_transform_pos(bone_mat[bi], bp, tp);
            mat4_transform_nrm(bone_mat[bi], bn, tn);

            px += tp[0]*wt; py += tp[1]*wt; pz += tp[2]*wt;
            nx += tn[0]*wt; ny += tn[1]*wt; nz += tn[2]*wt;
        }

        /* Normalizar normal. */
        float nl = sqrtf(nx*nx + ny*ny + nz*nz);
        if (nl > 0.0001f) { nx/=nl; ny/=nl; nz/=nl; }

        out[v].u = sv->u; out[v].v = sv->v;
        out[v].nx = nx; out[v].ny = ny; out[v].nz = nz;
        out[v].px = px; out[v].py = py; out[v].pz = pz;
    }

    sceKernelDcacheWritebackRange(
        anim->skin_buffer, anim->skin_size
    );
}

/* ------------------------------------------------------------------ */
/* p3d_anim_draw                                                       */
/* ------------------------------------------------------------------ */

void p3d_anim_draw(const P3DAnim *anim) {
    if (!anim || !anim->loaded || !anim->skin_buffer) return;

    sceGuColor(0xFFFFFFFF);

    sceGumDrawArray(
        GU_TRIANGLES,
        GU_TEXTURE_32BITF | GU_NORMAL_32BITF |
        GU_VERTEX_32BITF  | GU_TRANSFORM_3D,
        (int)anim->vertex_count,
        NULL,
        anim->skin_buffer
    );
}
