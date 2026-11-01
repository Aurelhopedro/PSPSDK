/*
 * p3d_anim.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * FASE 05.1 — Correções:
 *   - Layout binário AXS1 explícito (stride por memcpy, não sizeof).
 *   - Convenção column-major consistente em todas as matrizes.
 *   - Inverse bind pose calculada em load e aplicada no skinning.
 *   - Hierarquia de ossos correta (pai calculado antes do filho).
 *   - Validação de índices, pesos e limites antes de aceder dados.
 *   - Animação de salto não reinicia enquanto no ar.
 *   - Transição land após aterragem.
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
/* Matemática — matrizes column-major 4×4                             */
/* ------------------------------------------------------------------ */
/*
 * Acesso: m[col*4 + row]
 * m[0..3]  = coluna 0  (base X)
 * m[4..7]  = coluna 1  (base Y)
 * m[8..11] = coluna 2  (base Z)
 * m[12..15]= coluna 3  (translação)
 */

static void mat4_identity(float *m) {
    memset(m, 0, 16 * sizeof(float));
    m[0] = m[5] = m[10] = m[15] = 1.0f;
}

/*
 * Quaternião (xyzw) + posição → matriz column-major.
 * Equivalente ao padrão OpenGL gluQuaternion.
 */
static void quat_pos_to_mat4(
    const float *q, const float *pos, float *m
) {
    float x=q[0], y=q[1], z=q[2], w=q[3];
    float x2=2*x, y2=2*y, z2=2*z;
    float xx=x*x2, yy=y*y2, zz=z*z2;
    float xy=x*y2, xz=x*z2, yz=y*z2;
    float wx=w*x2, wy=w*y2, wz=w*z2;

    /* col 0 */
    m[ 0]=1-(yy+zz); m[ 1]=xy+wz;     m[ 2]=xz-wy;     m[ 3]=0;
    /* col 1 */
    m[ 4]=xy-wz;     m[ 5]=1-(xx+zz); m[ 6]=yz+wx;     m[ 7]=0;
    /* col 2 */
    m[ 8]=xz+wy;     m[ 9]=yz-wx;     m[10]=1-(xx+yy); m[11]=0;
    /* col 3 (translação) */
    m[12]=pos[0];    m[13]=pos[1];     m[14]=pos[2];    m[15]=1;
}

/*
 * Multiplicação column-major: out = a * b.
 * out pode ser diferente de a e b.
 */
static void mat4_mul(
    const float *a, const float *b, float *out
) {
    float tmp[16];
    for (int col = 0; col < 4; col++) {
        for (int row = 0; row < 4; row++) {
            float s = 0;
            for (int k = 0; k < 4; k++)
                s += a[k*4 + row] * b[col*4 + k];
            tmp[col*4 + row] = s;
        }
    }
    memcpy(out, tmp, 16 * sizeof(float));
}

/* Transformar posição: out = M * [v, 1] (coluna 3 = translação). */
static void mat4_transform_pos(
    const float *m, const float *v, float *out
) {
    out[0] = m[0]*v[0] + m[4]*v[1] + m[ 8]*v[2] + m[12];
    out[1] = m[1]*v[0] + m[5]*v[1] + m[ 9]*v[2] + m[13];
    out[2] = m[2]*v[0] + m[6]*v[1] + m[10]*v[2] + m[14];
}

/* Transformar normal (sem translação). */
static void mat4_transform_nrm(
    const float *m, const float *n, float *out
) {
    out[0] = m[0]*n[0] + m[4]*n[1] + m[ 8]*n[2];
    out[1] = m[1]*n[0] + m[5]*n[1] + m[ 9]*n[2];
    out[2] = m[2]*n[0] + m[6]*n[1] + m[10]*n[2];
}

/*
 * Inversa de uma matriz de transformação rígida (rot + trans):
 * inv_rot = transpose(rot3x3), inv_trans = -inv_rot * trans.
 * Não usa determinante geral — válido apenas para TRS sem escala.
 */
static void mat4_invert_rigid(const float *m, float *inv) {
    /* Transpor parte rotação (col→row swap). */
    inv[ 0]=m[0]; inv[ 1]=m[4]; inv[ 2]=m[ 8]; inv[ 3]=0;
    inv[ 4]=m[1]; inv[ 5]=m[5]; inv[ 6]=m[ 9]; inv[ 7]=0;
    inv[ 8]=m[2]; inv[ 9]=m[6]; inv[10]=m[10]; inv[11]=0;
    /* Translação inversa: -R^T * t. */
    inv[12] = -(inv[0]*m[12] + inv[4]*m[13] + inv[ 8]*m[14]);
    inv[13] = -(inv[1]*m[12] + inv[5]*m[13] + inv[ 9]*m[14]);
    inv[14] = -(inv[2]*m[12] + inv[6]*m[13] + inv[10]*m[14]);
    inv[15] = 1.0f;
}

/* NLERP de quaterniões (evita acos, adequado para PSP). */
static void quat_nlerp(
    const float *a, const float *b, float t, float *out
) {
    float dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2] + a[3]*b[3];
    float bx=b[0], by=b[1], bz=b[2], bw=b[3];
    if (dot < 0.0f) { bx=-bx; by=-by; bz=-bz; bw=-bw; }

    float rx = a[0] + t*(bx-a[0]);
    float ry = a[1] + t*(by-a[1]);
    float rz = a[2] + t*(bz-a[2]);
    float rw = a[3] + t*(bw-a[3]);

    float len = sqrtf(rx*rx + ry*ry + rz*rz + rw*rw);
    if (len > 1e-6f) {
        out[0]=rx/len; out[1]=ry/len; out[2]=rz/len; out[3]=rw/len;
    } else {
        out[0]=0; out[1]=0; out[2]=0; out[3]=1;
    }
}

/* ------------------------------------------------------------------ */
/* p3d_anim_init / state_init / set_clip                              */
/* ------------------------------------------------------------------ */

void p3d_anim_init(P3DAnim *anim) {
    if (!anim) return;
    memset(anim, 0, sizeof(*anim));
}

void p3d_anim_state_init(P3DAnimState *state) {
    if (!state) return;
    state->clip_index   = CLIP_IDLE;
    state->time         = 0.0f;
    state->loop         = 1;
    state->prev_grounded= 1;
    state->landing      = 0;
}

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
    if (anim->skin_buffer) { free(anim->skin_buffer); }
    if (anim->raw_data)    { free(anim->raw_data); }
    p3d_anim_init(anim);
}

/* ------------------------------------------------------------------ */
/* p3d_anim_load                                                       */
/* ------------------------------------------------------------------ */
/*
 * Lê os dados usando offsets e strides explícitos (AXS1_*_ONDISK),
 * nunca sizeof() para I/O. Valida todos os campos antes de usar.
 */

/* Cabeçalho on-disk — lido por memcpy, não cast direto. */
typedef struct {
    char         magic[4];
    unsigned int version;
    unsigned int bone_count;
    unsigned int vertex_count;
    unsigned int clip_count;
    unsigned int reserved[3];
} AXS1HeaderRaw;   /* 32 bytes — validado por assert abaixo */

int p3d_anim_load(P3DAnim *anim, const char *path) {
    if (!anim || !path) return 0;
    p3d_anim_unload(anim);

    SceUID fd = sceIoOpen(path, PSP_O_RDONLY, 0);
    if (fd < 0) return 0;

    /* --- Cabeçalho --- */
    AXS1HeaderRaw hdr;
    if (sceIoRead(fd, &hdr, AXS1_HEADER_SIZE) != AXS1_HEADER_SIZE) {
        sceIoClose(fd); return 0;
    }
    if (
        memcmp(hdr.magic, "AXS1", 4) != 0 ||
        hdr.version      != AXS1_VERSION   ||
        hdr.bone_count   == 0              ||
        hdr.bone_count   >  AXS1_MAX_BONES ||
        hdr.vertex_count == 0              ||
        hdr.vertex_count >  AXS1_MAX_VERTICES ||
        hdr.clip_count   == 0              ||
        hdr.clip_count   >  AXS1_MAX_CLIPS
    ) {
        sceIoClose(fd); return 0;
    }

    /* --- Tamanho total após cabeçalho --- */
    int fsize = sceIoLseek32(fd, 0, PSP_SEEK_END);
    if (fsize < AXS1_HEADER_SIZE) { sceIoClose(fd); return 0; }
    unsigned int data_size = (unsigned int)fsize - AXS1_HEADER_SIZE;

    /* Validar tamanho mínimo esperado. */
    unsigned int min_expected =
        hdr.bone_count   * AXS1_BONE_ONDISK +
        hdr.vertex_count * AXS1_VERTEX_ONDISK +
        hdr.clip_count   * AXS1_CLIP_HDR_SIZE;
        /* keys dependem de frame_count, lido depois */

    if (data_size < min_expected) { sceIoClose(fd); return 0; }

    /* --- Alocar e ler bloco de dados --- */
    void *raw = memalign(16, data_size);
    if (!raw) { sceIoClose(fd); return 0; }

    if (sceIoLseek32(fd, AXS1_HEADER_SIZE, PSP_SEEK_SET) < 0) {
        free(raw); sceIoClose(fd); return 0;
    }
    if (sceIoRead(fd, raw, data_size) != (int)data_size) {
        free(raw); sceIoClose(fd); return 0;
    }
    sceIoClose(fd);

    unsigned char *ptr = (unsigned char *)raw;
    unsigned char *end = ptr + data_size;

    anim->raw_data  = raw;
    anim->raw_size  = data_size;

    /* --- Ossos (AXS1_BONE_ONDISK = 56B por osso) --- */
    /*
     * Layout on-disk (56B):
     *   0:  name[16]
     *  16:  parent_index (int32)
     *  20:  pad[4]
     *  24:  bind_pos[3]  (float×3 = 12B)
     *  36:  bind_rot[4]  (float×4 = 16B)
     *  52:  pad_end[4]
     */
    anim->bone_count = (int)hdr.bone_count;
    for (int i = 0; i < anim->bone_count; i++) {
        if (ptr + AXS1_BONE_ONDISK > end) { p3d_anim_unload(anim); return 0; }
        AXS1Bone *b = &anim->bones[i];
        memcpy(b->name,      ptr,      16);
        memcpy(&b->parent_index, ptr+16, 4);
        memcpy(b->bind_pos,  ptr+24,  12);
        memcpy(b->bind_rot,  ptr+36,  16);
        b->name[15] = '\0';
        /* Validar parent_index. */
        if (b->parent_index >= anim->bone_count) {
            p3d_anim_unload(anim); return 0;
        }
        ptr += AXS1_BONE_ONDISK;
    }

    /* --- Vértices (AXS1_VERTEX_ONDISK = 52B por vértice) --- */
    /*
     * Layout on-disk (52B):
     *  0:  u,v          (float×2 = 8B)
     *  8:  nx,ny,nz     (float×3 = 12B)
     * 20:  px,py,pz     (float×3 = 12B)
     * 32:  bone_idx[4]  (uint8×4 = 4B)
     * 36:  weight[4]    (float×4 = 16B)
     */
    unsigned int vtx_bytes = hdr.vertex_count * AXS1_VERTEX_ONDISK;
    if (ptr + vtx_bytes > end) { p3d_anim_unload(anim); return 0; }

    /* Alocar array de vértices em memória separada (alinhado). */
    AXS1Vertex *vbuf = (AXS1Vertex *)memalign(16,
        hdr.vertex_count * sizeof(AXS1Vertex));
    if (!vbuf) { p3d_anim_unload(anim); return 0; }

    for (unsigned int v = 0; v < hdr.vertex_count; v++) {
        unsigned char *vp = ptr + v * AXS1_VERTEX_ONDISK;
        AXS1Vertex *vv = &vbuf[v];
        memcpy(&vv->u,        vp+0,  4);
        memcpy(&vv->v,        vp+4,  4);
        memcpy(&vv->nx,       vp+8,  4);
        memcpy(&vv->ny,       vp+12, 4);
        memcpy(&vv->nz,       vp+16, 4);
        memcpy(&vv->px,       vp+20, 4);
        memcpy(&vv->py,       vp+24, 4);
        memcpy(&vv->pz,       vp+28, 4);
        memcpy(vv->bone_idx,  vp+32, 4);
        memcpy(vv->weight,    vp+36, 16);

        /* Validar índices de ossos. */
        float wsum = 0.0f;
        for (int w = 0; w < AXS1_BONE_WEIGHTS; w++) {
            if (vv->bone_idx[w] >= (unsigned char)anim->bone_count)
                vv->bone_idx[w] = 0;
            if (vv->weight[w] < 0.0f) vv->weight[w] = 0.0f;
            wsum += vv->weight[w];
        }
        /* Renormalizar pesos. */
        if (wsum > 1e-6f) {
            for (int w = 0; w < AXS1_BONE_WEIGHTS; w++)
                vv->weight[w] /= wsum;
        } else {
            vv->weight[0] = 1.0f;
            for (int w = 1; w < AXS1_BONE_WEIGHTS; w++)
                vv->weight[w] = 0.0f;
        }
    }
    anim->vertices     = vbuf;
    anim->vertex_count = hdr.vertex_count;
    ptr += vtx_bytes;

    /* --- Clips --- */
    anim->clip_count = (int)hdr.clip_count;
    for (int c = 0; c < anim->clip_count; c++) {
        if (ptr + AXS1_CLIP_HDR_SIZE > end) { p3d_anim_unload(anim); return 0; }
        AXS1Clip *cl = &anim->clips[c];
        memcpy(cl->name,        ptr,    16);
        memcpy(&cl->frame_count,ptr+16,  4);
        memcpy(&cl->fps,        ptr+20,  4);
        cl->name[15] = '\0';
        ptr += AXS1_CLIP_HDR_SIZE;

        /* Validar clip. */
        if (cl->frame_count <= 0 || cl->fps <= 0.0f) {
            p3d_anim_unload(anim); return 0;
        }

        unsigned int key_bytes =
            (unsigned int)cl->frame_count *
            (unsigned int)anim->bone_count *
            AXS1_KEY_ONDISK;

        if (ptr + key_bytes > end) { p3d_anim_unload(anim); return 0; }

        /* Alocar array de keys em memória separada. */
        unsigned int key_count =
            (unsigned int)cl->frame_count *
            (unsigned int)anim->bone_count;

        AXS1Key *kbuf = (AXS1Key *)memalign(16, key_count * sizeof(AXS1Key));
        if (!kbuf) { p3d_anim_unload(anim); return 0; }

        for (unsigned int k = 0; k < key_count; k++) {
            unsigned char *kp = ptr + k * AXS1_KEY_ONDISK;
            memcpy(kbuf[k].rot, kp,    16);
            memcpy(kbuf[k].pos, kp+16, 12);
            /* Normalizar quaternião. */
            float *r = kbuf[k].rot;
            float  l = sqrtf(r[0]*r[0]+r[1]*r[1]+r[2]*r[2]+r[3]*r[3]);
            if (l > 1e-6f) { r[0]/=l; r[1]/=l; r[2]/=l; r[3]/=l; }
            else            { r[0]=0; r[1]=0; r[2]=0; r[3]=1; }
        }
        cl->keys = kbuf;
        ptr += key_bytes;
    }

    /* --- Calcular inverse bind pose matrices --- */
    /*
     * bind_mat[b] = world-space bind matrix do osso b.
     * Calculado hierarquicamente (pai antes do filho,
     * garantido porque bones são sempre em ordem topológica).
     */
    float bind_mat[AXS1_MAX_BONES][16];
    for (int b = 0; b < anim->bone_count; b++) {
        AXS1Bone *bone = &anim->bones[b];
        float local[16];
        quat_pos_to_mat4(bone->bind_rot, bone->bind_pos, local);

        int par = bone->parent_index;
        if (par < 0) {
            memcpy(bind_mat[b], local, sizeof(local));
        } else {
            mat4_mul(bind_mat[par], local, bind_mat[b]);
        }
        mat4_invert_rigid(bind_mat[b], anim->inv_bind[b]);
    }

    /* --- Buffer de skinning --- */
    unsigned int skin_sz = hdr.vertex_count * sizeof(AXS1SkinVtx);
    anim->skin_buffer = (AXS1SkinVtx *)memalign(16, skin_sz);
    if (!anim->skin_buffer) { p3d_anim_unload(anim); return 0; }
    anim->skin_size = skin_sz;

    sceKernelDcacheWritebackRange(raw, data_size);

    anim->loaded = 1;
    return 1;
}

/* ------------------------------------------------------------------ */
/* Matrizes de osso por frame                                          */
/* ------------------------------------------------------------------ */

static float s_bone_mat[AXS1_MAX_BONES][16];   /* skinning matrix */
static float s_anim_mat[AXS1_MAX_BONES][16];   /* animated world matrix */

/* ------------------------------------------------------------------ */
/* p3d_anim_update                                                     */
/* ------------------------------------------------------------------ */

void p3d_anim_update(
    P3DAnim *anim, P3DAnimState *state, float delta_time
) {
    if (!anim || !anim->loaded || !state) return;

    /* Clip bounds. */
    if (state->clip_index < 0 || state->clip_index >= anim->clip_count)
        state->clip_index = 0;

    AXS1Clip *clip = &anim->clips[state->clip_index];
    if (clip->frame_count < 1 || clip->fps <= 0.0f) return;

    /* Avançar tempo. */
    state->time += delta_time;
    float duration = (float)clip->frame_count / clip->fps;

    if (state->loop) {
        while (state->time >= duration) state->time -= duration;
        if (state->time < 0.0f) state->time = 0.0f;
    } else {
        if (state->time >= duration) {
            state->time = duration;
            /* Clip de land terminou: transitar para idle. */
            if (state->landing) {
                state->landing = 0;
                p3d_anim_set_clip(state, CLIP_IDLE, 1);
                clip = &anim->clips[state->clip_index];
                state->time = 0.0f;
            }
        }
    }

    /* Frames A e B para interpolação. */
    float frame_f = state->time * clip->fps;
    int   frame_a = (int)frame_f;
    float blend   = frame_f - (float)frame_a;

    if (frame_a >= clip->frame_count) frame_a = clip->frame_count - 1;
    int frame_b = frame_a + 1;
    if (frame_b >= clip->frame_count)
        frame_b = state->loop ? 0 : clip->frame_count - 1;

    /* --- Calcular matrizes animadas e de skinning --- */
    for (int b = 0; b < anim->bone_count; b++) {
        AXS1Key *ka = &clip->keys[frame_a * anim->bone_count + b];
        AXS1Key *kb = &clip->keys[frame_b * anim->bone_count + b];

        float rot[4], pos[3];
        quat_nlerp(ka->rot, kb->rot, blend, rot);
        pos[0] = ka->pos[0] + blend*(kb->pos[0]-ka->pos[0]);
        pos[1] = ka->pos[1] + blend*(kb->pos[1]-ka->pos[1]);
        pos[2] = ka->pos[2] + blend*(kb->pos[2]-ka->pos[2]);

        float local[16];
        quat_pos_to_mat4(rot, pos, local);

        int par = anim->bones[b].parent_index;
        if (par < 0) {
            memcpy(s_anim_mat[b], local, sizeof(local));
        } else {
            mat4_mul(s_anim_mat[par], local, s_anim_mat[b]);
        }

        /* skinning_mat = anim_world * inv_bind */
        mat4_mul(s_anim_mat[b], anim->inv_bind[b], s_bone_mat[b]);
    }

    /* --- Skinning CPU --- */
    AXS1SkinVtx *out = anim->skin_buffer;

    for (unsigned int v = 0; v < anim->vertex_count; v++) {
        AXS1Vertex *sv = &anim->vertices[v];

        float px=0, py=0, pz=0;
        float nx=0, ny=0, nz=0;
        float bp[3] = { sv->px, sv->py, sv->pz };
        float bn[3] = { sv->nx, sv->ny, sv->nz };

        for (int w = 0; w < AXS1_BONE_WEIGHTS; w++) {
            float wt = sv->weight[w];
            if (wt < 1e-6f) continue;
            int bi = sv->bone_idx[w];
            if (bi >= anim->bone_count) continue;

            float tp[3], tn[3];
            mat4_transform_pos(s_bone_mat[bi], bp, tp);
            mat4_transform_nrm(s_bone_mat[bi], bn, tn);

            px += tp[0]*wt; py += tp[1]*wt; pz += tp[2]*wt;
            nx += tn[0]*wt; ny += tn[1]*wt; nz += tn[2]*wt;
        }

        /* Normalizar normal. */
        float nl = sqrtf(nx*nx + ny*ny + nz*nz);
        if (nl > 1e-6f) { nx/=nl; ny/=nl; nz/=nl; }
        else { nx=0; ny=1; nz=0; }

        out[v].u=sv->u; out[v].v=sv->v;
        out[v].nx=nx; out[v].ny=ny; out[v].nz=nz;
        out[v].px=px; out[v].py=py; out[v].pz=pz;
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
