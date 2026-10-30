/*
 * p3d_model.h — RPG Axel Digital
 * FASE 04 — Carregador de modelos AXP3
 */

#ifndef P3D_MODEL_H
#define P3D_MODEL_H

typedef struct {
    void *vertices;
    unsigned int vertex_count;
    unsigned int data_size;
    int loaded;
} P3DModel;

/* Inicializa a estrutura do modelo. */
void p3d_model_init(P3DModel *model);

/* Carrega um ficheiro AXP3 da memória da PSP. */
int p3d_model_load(P3DModel *model, const char *path);

/* Desenha o modelo através do PSP GU. */
void p3d_model_draw(const P3DModel *model);

/* Liberta a memória ocupada pelo modelo. */
void p3d_model_unload(P3DModel *model);

#endif
