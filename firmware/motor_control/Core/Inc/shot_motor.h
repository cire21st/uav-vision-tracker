#pragma once

// Initialize D7 as an output held LOW. Call before triggering.
void shot_motor_init(void);

// Start a 1380 ms pulse. Returns false if a pulse is already active.
bool shot_motor_trigger(void);

// Call frequently from loop(); lowers D7 once the pulse has elapsed.
void shot_motor_update(void);

