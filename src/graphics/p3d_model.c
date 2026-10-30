/*
 * p3d_model.c — RPG Axel Digital
 * FASE 04 — Carregador AXP3 para PSP GU.
 *
 * Formato AXP3 v1:
 * Cabeçalho:
 *   magic[4]
 *   version
 *   vertex_count
 *   stride
 *
 * Cada vértice:
 *   U, V
 *   Normal X, Y, Z
 *   Posição X, Y, Z
 *
 * Total: 8 float32 = 32 bytes por vértice.
 */

#include "p3d_model.h"

#include <pspgu.h>
#include <pspkernel.h>
#include <pspiofilemgr.h>

#include <malloc.h>
#include <string.h>

#define P3D_VERSION       1
#define P3D_VERTEX_STRIDE 32

/* Limite de segurança para a memória da PSP. */
#define P3D_MAX_VERTICES 100000

/* Cada lote contém triângulos completos. */
#define P3D_DRAW_BATCH 2046

typedef struct {
    char magic[4];
    unsigned int version;
    unsigned int vertex_count;
    unsigned int stride;
} P3DHeader;


/* -------------------------------------------------- */
/* INICIALIZAÇÃO                                      */
/* -------------------------------------------------- */

void p3d_model_init(P3DModel *model) {

    if (!model)
        return;

    model->vertices = NULL;
    model->vertex_count = 0;
    model->data_size = 0;
    model->loaded = 0;
}


/* -------------------------------------------------- */
/* LIBERTAR MEMÓRIA                                   */
/* -------------------------------------------------- */

void p3d_model_unload(P3DModel *model) {

    if (!model)
        return;

    if (model->vertices) {
        free(model->vertices);
    }

    p3d_model_init(model);
}


/* -------------------------------------------------- */
/* CARREGAR MODELO                                    */
/* -------------------------------------------------- */

int p3d_model_load(P3DModel *model, const char *path) {

    if (!model || !path)
        return 0;

    /* O modelo deve ter sido inicializado previamente. */
    p3d_model_unload(model);

    SceUID fd = sceIoOpen(path, PSP_O_RDONLY, 0);

    if (fd < 0)
        return 0;

    P3DHeader header;

    int got = sceIoRead(
        fd,
        &header,
        sizeof(header)
    );

    if (got != (int)sizeof(header)) {

        sceIoClose(fd);
        return 0;
    }

    /* Validar o cabeçalho. */
    if (
        memcmp(header.magic, "AXP3", 4) != 0 ||
        header.version != P3D_VERSION ||
        header.stride != P3D_VERTEX_STRIDE ||
        header.vertex_count == 0 ||
        header.vertex_count > P3D_MAX_VERTICES ||
        (header.vertex_count % 3) != 0
    ) {

        sceIoClose(fd);
        return 0;
    }

    unsigned int data_size =
        header.vertex_count * P3D_VERTEX_STRIDE;

    /* Confirmar o tamanho real do ficheiro. */
    int file_size = sceIoLseek32(
        fd,
        0,
        PSP_SEEK_END
    );

    if (
        file_size < 0 ||
        (unsigned int)file_size !=
            (unsigned int)sizeof(P3DHeader) + data_size
    ) {

        sceIoClose(fd);
        return 0;
    }

    if (
        sceIoLseek32(
            fd,
            sizeof(P3DHeader),
            PSP_SEEK_SET
        ) < 0
    ) {

        sceIoClose(fd);
        return 0;
    }

    /* Alocar memória alinhada a 16 bytes. */
    void *buffer = memalign(16, data_size);

    if (!buffer) {

        sceIoClose(fd);
        return 0;
    }

    got = sceIoRead(
        fd,
        buffer,
        data_size
    );

    sceIoClose(fd);

    if (got != (int)data_size) {

        free(buffer);
        return 0;
    }

    /* Preparar os dados para acesso pelo hardware gráfico. */
    sceKernelDcacheWritebackRange(
        buffer,
        data_size
    );

    model->vertices = buffer;
    model->vertex_count = header.vertex_count;
    model->data_size = data_size;
    model->loaded = 1;

    return 1;
}


/* -------------------------------------------------- */
/* DESENHAR MODELO                                    */
/* -------------------------------------------------- */

void p3d_model_draw(const P3DModel *model) {

    if (
        !model ||
        !model->loaded ||
        !model->vertices
    ) {
        return;
    }

    sceGuColor(0xFFFFFFFF);

    unsigned int offset = 0;

    while (offset < model->vertex_count) {

        unsigned int count =
            model->vertex_count - offset;

        if (count > P3D_DRAW_BATCH) {
            count = P3D_DRAW_BATCH;
        }

        const void *batch =
            (const unsigned char *)model->vertices +
            (offset * P3D_VERTEX_STRIDE);

        sceGuDrawArray(
            GU_TRIANGLES,

            GU_TEXTURE_32BITF |
            GU_NORMAL_32BITF |
            GU_VERTEX_32BITF |
            GU_TRANSFORM_3D,

            count,
            NULL,
            batch
        );

        offset += count;
    }
}
