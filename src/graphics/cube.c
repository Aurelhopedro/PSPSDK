/*
 * cube.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * Geometria 3D do cubo com seis faces coloridas.
 * Renderizado com PSP GU/GUM.
 * FASE 01.
 */

#include "cube.h"
#include <pspgu.h>
#include <pspgum.h>
#include <math.h>

/*
 * Estrutura do vértice:
 * Cor ABGR + coordenadas X, Y, Z.
 */
typedef struct {
    unsigned int color;
    float x, y, z;
} __attribute__((packed, aligned(4))) Vertex;

/*
 * 36 vértices:
 * 6 faces × 2 triângulos × 3 vértices.
 *
 * Cores em formato ABGR.
 */

static Vertex __attribute__((aligned(16))) cube_verts[36] = {

    /* FRENTE (+Z) — vermelho */
    {0xFF0000FF, -1.0f, -1.0f,  1.0f},
    {0xFF0000FF,  1.0f, -1.0f,  1.0f},
    {0xFF0000FF,  1.0f,  1.0f,  1.0f},

    {0xFF0000FF, -1.0f, -1.0f,  1.0f},
    {0xFF0000FF,  1.0f,  1.0f,  1.0f},
    {0xFF0000FF, -1.0f,  1.0f,  1.0f},

    /* TRÁS (-Z) — verde */
    {0xFF00FF00,  1.0f, -1.0f, -1.0f},
    {0xFF00FF00, -1.0f, -1.0f, -1.0f},
    {0xFF00FF00, -1.0f,  1.0f, -1.0f},

    {0xFF00FF00,  1.0f, -1.0f, -1.0f},
    {0xFF00FF00, -1.0f,  1.0f, -1.0f},
    {0xFF00FF00,  1.0f,  1.0f, -1.0f},

    /* TOPO (+Y) — azul */
    {0xFFFF0000, -1.0f,  1.0f,  1.0f},
    {0xFFFF0000,  1.0f,  1.0f,  1.0f},
    {0xFFFF0000,  1.0f,  1.0f, -1.0f},

    {0xFFFF0000, -1.0f,  1.0f,  1.0f},
    {0xFFFF0000,  1.0f,  1.0f, -1.0f},
    {0xFFFF0000, -1.0f,  1.0f, -1.0f},

    /* BASE (-Y) — amarelo */
    {0xFF00FFFF, -1.0f, -1.0f, -1.0f},
    {0xFF00FFFF,  1.0f, -1.0f, -1.0f},
    {0xFF00FFFF,  1.0f, -1.0f,  1.0f},

    {0xFF00FFFF, -1.0f, -1.0f, -1.0f},
    {0xFF00FFFF,  1.0f, -1.0f,  1.0f},
    {0xFF00FFFF, -1.0f, -1.0f,  1.0f},

    /* DIREITA (+X) — magenta */
    {0xFFFF00FF,  1.0f, -1.0f,  1.0f},
    {0xFFFF00FF,  1.0f, -1.0f, -1.0f},
    {0xFFFF00FF,  1.0f,  1.0f, -1.0f},

    {0xFFFF00FF,  1.0f, -1.0f,  1.0f},
    {0xFFFF00FF,  1.0f,  1.0f, -1.0f},
    {0xFFFF00FF,  1.0f,  1.0f,  1.0f},

    /* ESQUERDA (-X) — ciano */
    {0xFFFFFF00, -1.0f, -1.0f, -1.0f},
    {0xFFFFFF00, -1.0f, -1.0f,  1.0f},
    {0xFFFFFF00, -1.0f,  1.0f,  1.0f},

    {0xFFFFFF00, -1.0f, -1.0f, -1.0f},
    {0xFFFFFF00, -1.0f,  1.0f,  1.0f},
    {0xFFFFFF00, -1.0f,  1.0f, -1.0f}
};

/*
 * Inicialização da geometria.
 * Os vértices já estão declarados estaticamente.
 */
void cube_init(void) {
    /* Não necessita de alocação dinâmica. */
}

/*
 * Converte ângulo em radianos para quaternion.
 *
 * O PSP GUM espera um ponteiro para quaternion
 * em sceGumRotate(), não um vetor e um ângulo.
 */
static void make_axis_quaternion(
    ScePspFQuaternion *q,
    float x,
    float y,
    float z,
    float angle
) {
    float half_angle = angle * 0.5f;
    float s = sinf(half_angle);

    q->x = x * s;
    q->y = y * s;
    q->z = z * s;
    q->w = cosf(half_angle);
}

/*
 * Desenha o cubo com rotação nos três eixos.
 */
void cube_draw(float rot_x, float rot_y, float rot_z) {

    ScePspFQuaternion qx __attribute__((aligned(16)));
    ScePspFQuaternion qy __attribute__((aligned(16)));
    ScePspFQuaternion qz __attribute__((aligned(16)));

    /* Criar os três quaternions de rotação. */
    make_axis_quaternion(&qx, 1.0f, 0.0f, 0.0f, rot_x);
    make_axis_quaternion(&qy, 0.0f, 1.0f, 0.0f, rot_y);
    make_axis_quaternion(&qz, 0.0f, 0.0f, 1.0f, rot_z);

    /* Matriz de transformação do modelo. */
    sceGumMatrixMode(GU_MODEL);
    sceGumLoadIdentity();

    /* Aplicar rotações X, Y e Z. */
    sceGumRotate(&qx);
    sceGumRotate(&qy);
    sceGumRotate(&qz);

    /* Cor branca: preservar as cores individuais dos vértices. */
    sceGuColor(0xFFFFFFFF);

    /* Desenhar os 36 vértices como triângulos. */
    sceGumDrawArray(
        GU_TRIANGLES,
        GU_COLOR_8888 | GU_VERTEX_32BITF | GU_TRANSFORM_3D,
        36,
        NULL,
        cube_verts
    );
}
