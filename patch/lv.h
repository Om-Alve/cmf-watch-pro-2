#pragma once
#include <stdint.h>

typedef struct _lv_obj_t lv_obj_t;
typedef struct _lv_event_t lv_event_t;
typedef struct _lv_timer_t lv_timer_t;
typedef struct _lv_font_t lv_font_t;
typedef int32_t lv_coord_t;
typedef uint16_t lv_color_t;
typedef void (*lv_event_cb_t)(lv_event_t *e);
typedef void (*lv_timer_cb_t)(lv_timer_t *t);
typedef struct _lv_indev_t lv_indev_t;
typedef struct { lv_coord_t x, y; } lv_point_t;
enum { LV_DIR_LEFT = 1, LV_DIR_RIGHT = 2, LV_DIR_TOP = 4, LV_DIR_BOTTOM = 8 };

enum {
    LV_EVENT_ALL = 0,
    LV_EVENT_PRESSED = 1,
    LV_EVENT_PRESSING = 2,
    LV_EVENT_PRESS_LOST = 3,
    LV_EVENT_SHORT_CLICKED = 4,
    LV_EVENT_LONG_PRESSED = 5,
    LV_EVENT_CLICKED = 7,
    LV_EVENT_RELEASED = 8,
    LV_EVENT_GESTURE = 12,
    LV_EVENT_KEY = 13,
    LV_EVENT_KNOB = 45,
};
enum { LV_ALIGN_TOP_MID = 2, LV_ALIGN_BOTTOM_MID = 5, LV_ALIGN_CENTER = 9 };
enum { LV_OBJ_FLAG_HIDDEN = 1 << 0, LV_OBJ_FLAG_CLICKABLE = 1 << 1, LV_OBJ_FLAG_SCROLLABLE = 1 << 4, LV_OBJ_FLAG_GESTURE_BUBBLE = 1 << 15 };
enum { LV_TEXT_ALIGN_CENTER = 2 };
#define LV_PART_MAIN 0
#define LV_OPA_COVER 255
#define LV_COLOR_HEX(c) ((lv_color_t)((((c) >> 19) & 0x1f) << 11 | (((c) >> 10) & 0x3f) << 5 | (((c) >> 3) & 0x1f)))

static inline void *lv_event_user_data(lv_event_t *e) { return ((void **)e)[3]; }
static inline void *lv_event_param(lv_event_t *e) { return ((void **)e)[4]; }
static inline void *lv_timer_user_data(lv_timer_t *t) { return ((void **)t)[3]; }

lv_obj_t *lv_disp_get_scr_act(void *disp);
lv_obj_t *lv_obj_create(lv_obj_t *parent);
void lv_obj_del(lv_obj_t *obj);
void lv_obj_set_size(lv_obj_t *obj, lv_coord_t w, lv_coord_t h);
void lv_obj_align(lv_obj_t *obj, uint8_t align, lv_coord_t x, lv_coord_t y);
void lv_obj_add_flag(lv_obj_t *obj, uint32_t f);
void lv_obj_clear_flag(lv_obj_t *obj, uint32_t f);
void *lv_obj_add_event_cb(lv_obj_t *obj, lv_event_cb_t cb, uint32_t filter, void *user_data);
uint32_t lv_event_get_code(lv_event_t *e);
void lv_obj_set_style_bg_color(lv_obj_t *obj, lv_color_t c, uint32_t sel);
void lv_obj_set_style_bg_opa(lv_obj_t *obj, uint8_t opa, uint32_t sel);
void lv_obj_set_style_border_width(lv_obj_t *obj, lv_coord_t w, uint32_t sel);
void lv_obj_set_style_text_color(lv_obj_t *obj, lv_color_t c, uint32_t sel);
void lv_obj_set_style_text_font(lv_obj_t *obj, const lv_font_t *f, uint32_t sel);
void lv_obj_set_style_text_align(lv_obj_t *obj, uint8_t a, uint32_t sel);
lv_obj_t *lv_label_create(lv_obj_t *parent);
void lv_label_set_text(lv_obj_t *obj, const char *text);
void lv_label_set_text_static(lv_obj_t *obj, const char *text);
void lv_label_set_text_fmt(lv_obj_t *obj, const char *fmt, ...);
void lv_obj_set_style_radius(lv_obj_t *obj, lv_coord_t r, uint32_t sel);
void lv_obj_set_width(lv_obj_t *obj, lv_coord_t w);
lv_timer_t *lv_timer_create(lv_timer_cb_t cb, uint32_t period, void *user_data);
void lv_timer_del(lv_timer_t *t);

lv_indev_t *lv_indev_get_act(void);
void lv_indev_get_point(const lv_indev_t *indev, lv_point_t *point);
uint8_t lv_indev_get_gesture_dir(const lv_indev_t *indev);
void lv_indev_wait_release(lv_indev_t *indev);
