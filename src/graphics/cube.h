/*
 * cube.h — RPG Axel Digital
 * Criado por Axev Digital
 *
 * Declarações do cubo 3D colorido.
 * FASE 01.
 */

#ifndef CUBE_H
#define CUBE_H

/* Inicializa a geometria do cubo (estática, sem alocação por frame). */
void cube_init(void);

/* Desenha o cubo com as rotações atuais (graus).
   Deve ser chamada entre gfx_begin_frame() e gfx_end_frame(). */
void cube_draw(float rot_x, float rot_y, float rot_z);

#endif /* CUBE_H */
