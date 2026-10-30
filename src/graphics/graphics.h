/*
 * graphics.h — RPG Axel Digital
 * Criado por Axev Digital
 *
 * Interface pública do sistema gráfico PSP GU/GUM.
 * FASE 01: Motor 3D — cubo colorido com rotação.
 */

#ifndef GRAPHICS_H
#define GRAPHICS_H

#include <pspgu.h>
#include <pspgum.h>
#include <pspdisplay.h>

/* ---------------------------------------------------------- */
/* Constantes de resolução                                    */
/* ---------------------------------------------------------- */
#define GFX_SCR_WIDTH   480
#define GFX_SCR_HEIGHT  272
#define GFX_BUF_WIDTH   512   /* potência de 2 exigida pelo GU */

/* ---------------------------------------------------------- */
/* Interface pública                                          */
/* ---------------------------------------------------------- */

/* Inicializa o GU, configura buffers e Z-buffer.
   Deve ser chamada uma única vez no arranque. */
void gfx_init(void);

/* Inicia um novo frame: limpa ecrã e Z-buffer, configura matrizes. */
void gfx_begin_frame(void);

/* Finaliza o frame: sincroniza GU e apresenta o buffer. */
void gfx_end_frame(void);

/* Termina o sistema gráfico. */
void gfx_shutdown(void);

#endif /* GRAPHICS_H */
