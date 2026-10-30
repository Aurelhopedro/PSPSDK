/*
 * graphics.c — RPG Axel Digital
 * Criado por Axev Digital
 *
 * Inicialização e gestão do PSP GU.
 * Double buffering, Z-buffer, viewport, sincronização de frames.
 * FASE 01: Motor 3D.
 */

#include "graphics.h"
#include <string.h>

/* ---------------------------------------------------------- */
/* Layout de memória de vídeo da PSP                         */
/*                                                            */
/* Frame buffer A : 0x00000000 (tamanho: 512*272*4 = 557056) */
/* Frame buffer B : 0x00088000 (offset 557056, alinhado)     */
/* Z-buffer       : 0x00110000 (offset 1114112)              */
/*                                                            */
/* Os ponteiros passados ao GU são offsets a partir de       */
/* 0x04000000 (início da VRAM) quando usados com sceGuInit.  */
/* O GU aceita endereços relativos (sem o prefixo 0x04…)     */
/* para buffers de frame e depth através de sceGuDrawBuffer. */
/* ---------------------------------------------------------- */

#define VRAM_FB0      0x00000000
#define VRAM_FB1      0x00088000
#define VRAM_DEPTH    0x00110000

/* Display list — alinhada a 16 bytes, em RAM normal */
static unsigned int __attribute__((aligned(16))) display_list[262144];

/* Ponteiro para o framebuffer visível atual */
static void *draw_buffer  = (void *)VRAM_FB0;
static void *disp_buffer  = (void *)VRAM_FB1;
static void *depth_buffer = (void *)VRAM_DEPTH;

/* ---------------------------------------------------------- */
/* gfx_init                                                   */
/* ---------------------------------------------------------- */
void gfx_init(void) {
    /* Inicializar o GU */
    sceGuInit();

    /* Abrir display list inicial de configuração */
    sceGuStart(GU_DIRECT, display_list);

    /* Buffers de frame e profundidade */
    sceGuDrawBuffer(GU_PSM_8888, draw_buffer, GFX_BUF_WIDTH);
    sceGuDispBuffer(GFX_SCR_WIDTH, GFX_SCR_HEIGHT, disp_buffer, GFX_BUF_WIDTH);
    sceGuDepthBuffer(depth_buffer, GFX_BUF_WIDTH);

    /* Viewport: mapeia coordenadas NDC para ecrã PSP */
    sceGuOffset(2048 - (GFX_SCR_WIDTH / 2), 2048 - (GFX_SCR_HEIGHT / 2));
    sceGuViewport(2048, 2048, GFX_SCR_WIDTH, GFX_SCR_HEIGHT);

    /* Z-buffer: 0 = próximo, 65535 = distante */
    sceGuDepthRange(65535, 0);

    /* Scissor: área de recorte = ecrã completo */
    sceGuScissor(0, 0, GFX_SCR_WIDTH, GFX_SCR_HEIGHT);
    sceGuEnable(GU_SCISSOR_TEST);

    /* Teste de profundidade */
    sceGuDepthFunc(GU_GEQUAL);
    sceGuEnable(GU_DEPTH_TEST);

    /* Sem back-face culling — queremos ver todas as faces do cubo */
    sceGuFrontFace(GU_CCW);
    sceGuDisable(GU_CULL_FACE);

    /* Cor lisa (sem textura) */
    sceGuShadeModel(GU_SMOOTH);
    sceGuDisable(GU_TEXTURE_2D);

    /* Blending desativado (sem transparência) */
    sceGuDisable(GU_BLEND);

    /* Fechar lista de configuração */
    sceGuFinish();
    sceGuSync(GU_SYNC_FINISH, GU_SYNC_WHAT_DONE);

    /* Ativar display */
    sceGuDisplay(GU_TRUE);
}

/* ---------------------------------------------------------- */
/* gfx_begin_frame                                            */
/* ---------------------------------------------------------- */
void gfx_begin_frame(void) {
    sceGuStart(GU_DIRECT, display_list);

    /* Limpar cor e Z-buffer */
    sceGuClearColor(0xFF1a0a2e);   /* fundo: roxo escuro */
    sceGuClearDepth(0);
    sceGuClear(GU_COLOR_BUFFER_BIT | GU_DEPTH_BUFFER_BIT);
}

/* ---------------------------------------------------------- */
/* gfx_end_frame                                              */
/* ---------------------------------------------------------- */
void gfx_end_frame(void) {
    sceGuFinish();
    sceGuSync(GU_SYNC_FINISH, GU_SYNC_WHAT_DONE);

    /* Esperar VBlank antes de trocar buffers */
    sceDisplayWaitVblankStart();
    sceGuSwapBuffers();
}

/* ---------------------------------------------------------- */
/* gfx_shutdown                                               */
/* ---------------------------------------------------------- */
void gfx_shutdown(void) {
    sceGuDisplay(GU_FALSE);
    sceGuTerm();
}
