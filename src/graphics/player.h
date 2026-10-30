#ifndef PLAYER_H
#define PLAYER_H

#include <pspctrl.h>

typedef struct {
    float x;
    float y;
    float z;

    float yaw;

    float vertical_velocity;
    float walk_time;

    int grounded;
    int moving;
} Player;

void player_init(Player *player);

void player_update(
    Player *player,
    const SceCtrlData *pad,
    float delta_time
);

void player_draw(const Player *player);

void player_draw_ground(void);

#endif
