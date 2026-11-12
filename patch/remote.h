#pragma once

enum remote_key {
    KEY_VOLUMEDOWN = 0,
    KEY_VOLUMEUP = 1,
    KEY_MUTE = 2,
    KEY_PLAYPAUSE = 3,
    KEY_PREVIOUSSONG = 4,
    KEY_NEXTSONG = 5,
    KEY_LAST = 6,
    KEY_REWIND = 7,
    /* Swipes: the HID report has only 8 keys, so each swipe is two keys pressed together
       (LAST + one other); g2-ring-remote reads the pair as one event. */
    KEY_SWIPE_UP = 8,
    KEY_SWIPE_DOWN = 9,
    KEY_SWIPE_LEFT = 10,
    KEY_SWIPE_RIGHT = 11,
};

void remote_log(const char *fmt, unsigned arg);
void remote_key(enum remote_key key);
void remote_prime(void);
