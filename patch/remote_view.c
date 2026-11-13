#include "lv.h"
#include "remote.h"

#define REMOTE_VIEW_ID 0x2c
#define VOICE_ASSISTANT_SCENE 0x30bd0452u

struct jx_view {
    uint32_t scene_id;
    void *scene_ctx;
    uint32_t unused[2];
    void **view_data;
    struct remote_ctx *ctx;
    uint16_t view_id;
    uint8_t flags;
};

enum mode { MODE_REMOTE, MODE_TYPE };

/* Typing screen: nine letter/number keys, a bottom row, and a preview line.
   Each key is a left flick, a tap and a right flick. 0 means no character. */
#define PAGE_LETTERS 0
#define PAGE_NUMBERS 1
static const char pages[2][10][3] = {
    {
        {'B', 'A', 'C'}, {'D', 'E', 'F'}, {'G', 'H', 'I'},
        {'J', 'L', 'K'}, {'M', 'N', 'O'}, {'P', 'R', 'Q'},
        {'S', 'T', 'U'}, {'V', 'W', 'X'}, {'Z', 'Y', '.'},
        {0, ' ', 0},
    },
    {
        {'.', '1', ','}, {'?', '2', '!'}, {'\'', '3', '"'},
        {':', '4', ';'}, {'-', '5', '_'}, {'/', '6', '\\'},
        {'(', '7', ')'}, {'@', '8', '#'}, {'+', '9', '='},
        {' ', '0', '%'},
    },
};

#define GRID_X0 140
#define GRID_Y0 144
#define GRID_DX 93
#define GRID_DY 90
#define KEY_HALF_W 44
#define KEY_HALF_H 39
#define BOTTOM_Y0 367
#define BOTTOM_Y1 425
#define TOGGLE_X0 78
#define TOGGLE_X1 146
#define MID_X0 157
#define MID_X1 286
#define DEL_X0 296
#define DEL_X1 383
#define MID_KEY 9
#define KEY_TOGGLE 10
#define KEY_DELETE 11
#define KEY_NONE 0xff

#define LABELS 32              /* 10 keys x 3, then toggle and delete */
#define LABEL_TOGGLE 30
#define LABEL_DELETE 31
#define LABEL_NONE 0xff
#define TAP_PX 28
#define REPEAT_DELAY_MS 650
#define REPEAT_MS 160

/* Dot-matrix layout (design 2): link LED, two-line clock, one status word. */
struct remote_ctx {
    lv_obj_t *scr;
    lv_obj_t *root;
    lv_obj_t *led;
    lv_obj_t *hours;
    lv_obj_t *minutes;
    lv_obj_t *status;
    lv_timer_t *tap_timer;
    lv_timer_t *tick_timer;
    uint8_t clock_font_loaded;
    uint8_t word_font_loaded;
    uint8_t pending_tap;
    uint8_t second_press;
    uint8_t crown_down;
    uint8_t linked;        /* 0 no phone, 1 phone, 0xff unknown (forces first paint) */
    uint8_t flash_ticks;   /* ticks left showing the last command */
    uint8_t last_minute;
    uint8_t screen_held;
    uint8_t swiped;        /* this touch became a swipe: ignore its click / long press */
    lv_timer_t *exit_timer;
    lv_coord_t press_x, press_y;
    uint16_t idle_ticks;   /* ticks since the last gesture; the screen hold ends at IDLE_TICKS */
    uint8_t mode;          /* enum mode */
    uint8_t page;          /* PAGE_LETTERS or PAGE_NUMBERS */
    uint8_t type_key;      /* key under the finger, KEY_NONE between touches */
    uint8_t type_cancelled;
    uint8_t repeat_fired;
    uint8_t hot;           /* label drawn in the accent colour, LABEL_NONE if none */
    lv_timer_t *repeat_timer;
    lv_obj_t *type_layer;
    lv_obj_t *keys[LABELS];
    lv_obj_t *preview;
    char label_text[LABELS][2];
    char preview_text[2];
    uint32_t clock_font[16];
    uint32_t word_font[16];
};

struct rtc_time {
    uint8_t sec, min, hour, mday, mon, wday;
    uint16_t year;
    uint16_t ms;
    uint16_t pad;
};

struct view_reg {
    uint8_t flags0, flags1;
    uint16_t id;
    uint16_t ctx_size, pad;
    uint32_t scene_id;
    int (*create_a)(struct jx_view *);
    int (*create_b)(struct jx_view *);
    int (*focus)(struct jx_view *, int);
    int (*get_res_dsc)(unsigned, void *);
    int (*inflate)(struct jx_view *);
    int (*destroy)(struct jx_view *);
    int (*lang_change)(struct jx_view *, int);
    int (*key)(struct jx_view *, unsigned);
    int (*event)(struct jx_view *, unsigned);
    const void *sub0, *sub1;
};

extern int stock_voice_assistant_res_dsc(unsigned id, void *dsc);
extern int stock_ui_view_creater(const struct view_reg *reg, unsigned id, void *view_data, unsigned msg, void *msg_data);
extern int stock_font_load(void *font, const char *path);
extern void stock_font_unload(void *font);
extern int stock_view_open(unsigned view_id, void *arg);
extern void stock_rtc_get_time(struct rtc_time *out);
extern void *stock_phone_connection(void);
extern int stock_ux2sys_set(int id, void *buf, int len);
/* Per-id screen hold (stock apps pass their view id): the first hold takes a full wake
   lock, the last release drops it. */
extern void stock_screen_hold(unsigned id);
extern void stock_screen_release(unsigned id);
/* ui-service swipe handling (view slide / swipe back): 0 = off, 30 = all four directions.
   Stock views turn it off while focused and restore 30 when they lose focus. */
extern void stock_gesture_set(unsigned dirs);
extern void stock_view_back(void);

/* ux2sys id 38: vibrate at the user's strength (vibration off = no buzz). */
#define UX2SYS_VIBRATE 38
#define VIBRATE_60MS 6
#define VIBRATE_20MS 8

#define COLOR_ACCENT LV_COLOR_HEX(0xF0552D)
#define COLOR_INK LV_COLOR_HEX(0xF0F0F0)
#define COLOR_MUTED LV_COLOR_HEX(0x9A9EA3)
#define COLOR_SIDE LV_COLOR_HEX(0x5C6066)
#define FLASH_TICKS 3          /* x 500 ms */
#define TICK_MS 500
#define GESTURES_ALL 30
#define TP_SWIPE_DOWN 0xffff006eu
#define TP_SWIPE_UP 0xffff006fu
#define TP_SWIPE_LEFT 0xffff0070u
#define TP_SWIPE_RIGHT 0xffff0071u
#define EDGE_PX 80             /* swipe right starting this close to the left edge = back */
#define DRAG_PX 40             /* a long press that has moved this far is a slow swipe */
#define IDLE_TICKS (10 * 60 * 1000 / TICK_MS)   /* 10 min without a gesture: normal timeout again */

#define VOICE_ASSISTANT_VIEW_ID 0xcf

static void set_word(struct remote_ctx *c, const char *text, lv_color_t color)
{
    if (!c->status)
        return;
    lv_label_set_text(c->status, text);
    lv_obj_set_style_text_color(c->status, color, LV_PART_MAIN);
}

static void paint_idle(struct remote_ctx *c)
{
    if (c->linked)
        set_word(c, "READY", COLOR_MUTED);
    else
        set_word(c, "NO LINK", COLOR_ACCENT);
    if (c->led)
        lv_obj_set_style_bg_color(c->led, c->linked ? COLOR_INK : COLOR_ACCENT, LV_PART_MAIN);
}

static void show(struct remote_ctx *c, const char *text)
{
    set_word(c, text, COLOR_ACCENT);
    c->flash_ticks = FLASH_TICKS;
}

static void update_clock(struct remote_ctx *c, int force)
{
    struct rtc_time t = {0};
    stock_rtc_get_time(&t);
    if (!force && t.min == c->last_minute)
        return;
    c->last_minute = t.min;
    if (c->hours)
        lv_label_set_text_fmt(c->hours, "%02d", t.hour);
    if (c->minutes)
        lv_label_set_text_fmt(c->minutes, "%02d", t.min);
}

static void screen_hold(struct remote_ctx *c)
{
    c->idle_ticks = 0;
    if (!c->screen_held) {
        stock_screen_hold(REMOTE_VIEW_ID);
        c->screen_held = 1;
    }
}

static void screen_release(struct remote_ctx *c)
{
    if (c->screen_held) {
        stock_screen_release(REMOTE_VIEW_ID);
        c->screen_held = 0;
    }
}

static lv_color_t label_color(uint8_t idx)
{
    return idx >= LABEL_TOGGLE || idx % 3 == 1 ? COLOR_INK : COLOR_SIDE;
}

static void set_hot(struct remote_ctx *c, uint8_t idx)
{
    if (idx == c->hot)
        return;
    if (c->hot != LABEL_NONE)
        lv_obj_set_style_text_color(c->keys[c->hot], label_color(c->hot), LV_PART_MAIN);
    if (idx != LABEL_NONE)
        lv_obj_set_style_text_color(c->keys[idx], COLOR_ACCENT, LV_PART_MAIN);
    c->hot = idx;
}

static void set_preview(struct remote_ctx *c, char ch)
{
    if (!ch)
        lv_label_set_text_static(c->preview, "");
    else if (ch == ' ')
        lv_label_set_text_static(c->preview, "SPACE");
    else if (ch == '\b')
        lv_label_set_text_static(c->preview, "DEL");
    else {
        c->preview_text[0] = ch;
        c->preview_text[1] = 0;
        lv_label_set_text_static(c->preview, c->preview_text);
    }
}

static void set_cell(struct remote_ctx *c, uint8_t idx, char ch)
{
    if (ch == ' ') {
        lv_label_set_text_static(c->keys[idx], idx == MID_KEY * 3 + 1 ? "SPACE" : "SP");
        return;
    }
    c->label_text[idx][0] = ch;
    c->label_text[idx][1] = 0;
    lv_label_set_text_static(c->keys[idx], c->label_text[idx]);
}

static void set_page(struct remote_ctx *c, uint8_t page)
{
    c->page = page;
    for (uint8_t i = 0; i < 10; i++)
        for (uint8_t k = 0; k < 3; k++)
            set_cell(c, i * 3 + k, pages[page][i][k]);
    lv_label_set_text_static(c->keys[LABEL_TOGGLE], page == PAGE_LETTERS ? "123" : "ABC");
}

static void tick(lv_timer_t *timer)
{
    struct remote_ctx *c = lv_timer_user_data(timer);
    if (c->screen_held && ++c->idle_ticks >= IDLE_TICKS)
        screen_release(c);
    uint8_t linked = stock_phone_connection() != 0;
    update_clock(c, 0);
    if (c->flash_ticks) {
        if (--c->flash_ticks == 0)
            paint_idle(c);
    } else if (linked != c->linked) {
        c->linked = linked;
        paint_idle(c);
    }
    c->linked = linked;
}

static void buzz(uint32_t pattern)
{
    stock_ux2sys_set(UX2SYS_VIBRATE, &pattern, sizeof(pattern));
}

static void send(struct remote_ctx *c, enum remote_key key, const char *label)
{
    screen_hold(c);
    show(c, label);
    buzz(key == KEY_LAST || key == KEY_VOLUMEUP ? VIBRATE_20MS : VIBRATE_60MS);
    remote_key(key);
}

static void cancel_tap_timer(struct remote_ctx *c)
{
    if (c->tap_timer) {
        lv_timer_del(c->tap_timer);
        c->tap_timer = 0;
    }
}

static void cancel_repeat(struct remote_ctx *c)
{
    if (c->repeat_timer) {
        lv_timer_del(c->repeat_timer);
        c->repeat_timer = 0;
    }
}

static void tap_timeout(lv_timer_t *t)
{
    struct remote_ctx *c = lv_timer_user_data(t);
    lv_timer_del(t);
    c->tap_timer = 0;
    if (c->pending_tap && !c->second_press) {
        c->pending_tap = 0;
        send(c, KEY_PLAYPAUSE, "SELECT");
    }
}

static void exit_timeout(lv_timer_t *t)
{
    struct remote_ctx *c = lv_timer_user_data(t);
    lv_timer_del(t);
    c->exit_timer = 0;
    stock_view_back();
}

static void set_mode(struct remote_ctx *c, enum mode mode)
{
    remote_log("faceclaw-remote: mode %d\n", mode);
    cancel_tap_timer(c);
    cancel_repeat(c);
    c->pending_tap = 0;
    c->second_press = 0;
    c->type_key = KEY_NONE;
    set_hot(c, LABEL_NONE);
    set_preview(c, 0);
    c->mode = mode;
    if (mode == MODE_TYPE)
        lv_obj_clear_flag(c->type_layer, LV_OBJ_FLAG_HIDDEN);
    else
        lv_obj_add_flag(c->type_layer, LV_OBJ_FLAG_HIDDEN);
    screen_hold(c);
}

static int inside(lv_coord_t x, lv_coord_t y)
{
    int dx = x - 233, dy = y - 233;
    return dx * dx + dy * dy <= 233 * 233;
}

static uint8_t key_at(lv_coord_t x, lv_coord_t y)
{
    if (!inside(x, y))
        return KEY_NONE;
    if (y >= BOTTOM_Y0 && y <= BOTTOM_Y1) {
        if (x >= TOGGLE_X0 && x <= TOGGLE_X1)
            return KEY_TOGGLE;
        if (x >= MID_X0 && x <= MID_X1)
            return MID_KEY;
        if (x >= DEL_X0 && x <= DEL_X1)
            return KEY_DELETE;
        return KEY_NONE;
    }
    for (uint8_t i = 0; i < 9; i++) {
        lv_coord_t cx = GRID_X0 + i % 3 * GRID_DX, cy = GRID_Y0 + i / 3 * GRID_DY;
        if (x >= cx - KEY_HALF_W && x <= cx + KEY_HALF_W && y >= cy - KEY_HALF_H && y <= cy + KEY_HALF_H)
            return i;
    }
    return KEY_NONE;
}

static int tap_only(const char *row)
{
    return !row[0] && !row[2];
}

static char flick_char(const char *row, lv_coord_t dx, lv_coord_t dy)
{
    int ax = dx < 0 ? -dx : dx, ay = dy < 0 ? -dy : dy;
    if (ay > 60 || ax > 140)
        return 0;
    if (ax < TAP_PX)
        return row[1];
    if (10 * ax < 13 * ay)
        return 0;
    return row[dx < 0 ? 0 : 2];
}

static char type_candidate(struct remote_ctx *c, lv_coord_t x, lv_coord_t y)
{
    const char *row;
    lv_coord_t dx, dy;
    if (c->type_key >= KEY_TOGGLE || c->type_cancelled || !inside(x, y))
        return 0;
    dx = x - c->press_x;
    dy = y - c->press_y;
    row = pages[c->page][c->type_key];
    if (tap_only(row))
        return dx * dx + dy * dy < TAP_PX * TAP_PX ? row[1] : 0;
    return flick_char(row, dx, dy);
}

static void type_char(struct remote_ctx *c, char ch)
{
    screen_hold(c);
    buzz(VIBRATE_20MS);
    if (ch >= 'A' && ch <= 'Z')
        ch += 'a' - 'A';
    remote_text(ch);
}

static void repeat_timeout(lv_timer_t *t)
{
    struct remote_ctx *c = lv_timer_user_data(t);
    if (c->type_key != KEY_DELETE || c->type_cancelled) {
        lv_timer_del(t);
        c->repeat_timer = 0;
        return;
    }
    if (!c->repeat_fired) {
        c->repeat_fired = 1;
        lv_timer_del(t);
        c->repeat_timer = lv_timer_create(repeat_timeout, REPEAT_MS, c);
    }
    type_char(c, '\b');
}

static void type_update(struct remote_ctx *c, lv_coord_t x, lv_coord_t y, int commit)
{
    lv_coord_t dx = x - c->press_x, dy = y - c->press_y;
    int tap = dx * dx + dy * dy < TAP_PX * TAP_PX;
    uint8_t idx = LABEL_NONE;
    char ch = 0;
    if (c->type_key == KEY_TOGGLE) {
        if (tap && inside(x, y)) {
            idx = LABEL_TOGGLE;
            if (commit) {
                buzz(VIBRATE_20MS);
                set_page(c, c->page == PAGE_LETTERS ? PAGE_NUMBERS : PAGE_LETTERS);
            }
        }
    } else if (c->type_key == KEY_DELETE) {
        if (tap && inside(x, y) && !c->type_cancelled) {
            idx = LABEL_DELETE;
            ch = '\b';
            if (commit && !c->repeat_fired)
                type_char(c, ch);
        }
    } else {
        ch = type_candidate(c, x, y);
        if (ch) {
            const char *row = pages[c->page][c->type_key];
            for (uint8_t k = 0; k < 3; k++)
                if (row[k] == ch)
                    idx = c->type_key * 3 + k;
            if (commit)
                type_char(c, ch);
        }
    }
    set_hot(c, idx);
    set_preview(c, ch);
}

static void on_type_touch(struct remote_ctx *c, uint32_t code)
{
    lv_point_t p;
    if (code == LV_EVENT_PRESS_LOST) {
        cancel_repeat(c);
        c->type_key = KEY_NONE;
        set_hot(c, LABEL_NONE);
        set_preview(c, 0);
        return;
    }
    if (code != LV_EVENT_PRESSED && code != LV_EVENT_PRESSING && code != LV_EVENT_RELEASED)
        return;
    lv_indev_get_point(lv_indev_get_act(), &p);
    if (code == LV_EVENT_PRESSED) {
        c->press_x = p.x;
        c->press_y = p.y;
        c->type_key = key_at(p.x, p.y);
        c->type_cancelled = 0;
        c->repeat_fired = 0;
        if (c->type_key == KEY_NONE)
            return;
        if (c->type_key == KEY_DELETE)
            c->repeat_timer = lv_timer_create(repeat_timeout, REPEAT_DELAY_MS, c);
        type_update(c, p.x, p.y, 0);
        return;
    }
    if (c->type_key == KEY_NONE)
        return;
    if (code == LV_EVENT_PRESSING) {
        lv_coord_t dx = p.x - c->press_x, dy = p.y - c->press_y;
        if (c->type_key == KEY_DELETE && dx * dx + dy * dy >= TAP_PX * TAP_PX) {
            c->type_cancelled = 1;
            cancel_repeat(c);
        }
        type_update(c, p.x, p.y, 0);
        return;
    }
    type_update(c, p.x, p.y, 1);
    cancel_repeat(c);
    c->type_key = KEY_NONE;
    set_hot(c, LABEL_NONE);
    set_preview(c, 0);
}

static void on_gesture(struct remote_ctx *c, lv_indev_t *indev)
{
    uint8_t dir = lv_indev_get_gesture_dir(indev);
    lv_indev_wait_release(indev);
    c->swiped = 1;
    cancel_tap_timer(c);
    c->pending_tap = 0;
    c->second_press = 0;
    switch (dir) {
    case LV_DIR_RIGHT:
        if (c->press_x < EDGE_PX) {
            if (!c->exit_timer)
                c->exit_timer = lv_timer_create(exit_timeout, 10, c);
            return;
        }
        send(c, KEY_SWIPE_RIGHT, "SWIPE RIGHT");
        break;
    case LV_DIR_LEFT:
        if (c->press_x >= 466 - EDGE_PX) {
            set_mode(c, MODE_TYPE);
            return;
        }
        send(c, KEY_SWIPE_LEFT, "SWIPE LEFT");
        break;
    case LV_DIR_TOP:
        send(c, KEY_SWIPE_UP, "SWIPE UP");
        break;
    case LV_DIR_BOTTOM:
        send(c, KEY_SWIPE_DOWN, "SWIPE DOWN");
        break;
    default:
        break;
    }
}

static int dragged(struct remote_ctx *c)
{
    lv_point_t p;
    lv_indev_get_point(lv_indev_get_act(), &p);
    lv_coord_t dx = p.x - c->press_x, dy = p.y - c->press_y;
    return dx > DRAG_PX || dx < -DRAG_PX || dy > DRAG_PX || dy < -DRAG_PX;
}

static void on_touch(lv_event_t *e)
{
    struct remote_ctx *c = lv_event_user_data(e);
    uint32_t code = lv_event_get_code(e);
    if (c->mode == MODE_TYPE) {
        on_type_touch(c, code);
        return;
    }
    if (code == LV_EVENT_GESTURE) {
        on_gesture(c, lv_event_param(e));
        return;
    }
    if (c->swiped && code != LV_EVENT_PRESSED)
        return;
    switch (code) {
    case LV_EVENT_PRESSED: {
        lv_point_t p;
        lv_indev_get_point(lv_indev_get_act(), &p);
        c->press_x = p.x;
        c->press_y = p.y;
        c->swiped = 0;
        if (c->second_press) {
            cancel_tap_timer(c);
            c->pending_tap = 0;
            c->second_press = 0;
        } else if (c->pending_tap) {
            cancel_tap_timer(c);
            c->second_press = 1;
        }
        break;
    }
    case LV_EVENT_SHORT_CLICKED:
        if (c->second_press) {
            c->second_press = 0;
            c->pending_tap = 0;
            send(c, KEY_REWIND, "BACK");
        } else {
            c->pending_tap = 1;
            c->tap_timer = lv_timer_create(tap_timeout, 300, c);
        }
        break;
    case LV_EVENT_LONG_PRESSED:
        if (dragged(c))
            break;
        if (c->second_press) {
            c->second_press = 0;
            c->pending_tap = 0;
            send(c, KEY_PREVIOUSSONG, "APP MENU");
        } else {
            send(c, KEY_NEXTSONG, "MENU");
        }
        break;
    case LV_EVENT_PRESS_LOST:
        cancel_tap_timer(c);
        c->pending_tap = 0;
        c->second_press = 0;
        break;
    default:
        break;
    }
}

static void on_knob(lv_event_t *e)
{
    struct remote_ctx *c = lv_event_user_data(e);
    int32_t *step = lv_event_param(e);
    if (!step || *step == 0)
        return;
    if (c->mode == MODE_TYPE)
        return;
    /* On the real watch the stock list direction felt inverted: turning the crown the
       way that scrolls the app list down should scroll Faceclaw up. */
    if (*step > 0)
        send(c, KEY_VOLUMEUP, "UP");
    else
        send(c, KEY_LAST, "DOWN");
}

static int noop(struct jx_view *v) { (void)v; return 0; }
static int focus(struct jx_view *v, int focused)
{
    (void)v;
    stock_gesture_set(focused ? 0 : GESTURES_ALL);
    return 0;
}

static lv_obj_t *dot_label(struct remote_ctx *c, int use_clock_font, lv_color_t color, lv_coord_t y)
{
    lv_obj_t *l = lv_label_create(c->root);
    if (use_clock_font ? c->clock_font_loaded : c->word_font_loaded)
        lv_obj_set_style_text_font(l, (const lv_font_t *)(use_clock_font ? c->clock_font : c->word_font), LV_PART_MAIN);
    lv_obj_set_style_text_color(l, color, LV_PART_MAIN);
    lv_obj_set_width(l, 400);
    lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_obj_align(l, LV_ALIGN_CENTER, 0, y);
    return l;
}

static void plain(lv_obj_t *o)
{
    lv_obj_set_style_border_width(o, 0, LV_PART_MAIN);
    lv_obj_clear_flag(o, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
}

/* Touches fall through the layer and its labels to the root, which owns all input. */
static lv_obj_t *type_label(struct remote_ctx *c, lv_coord_t x, lv_coord_t y, lv_color_t color)
{
    lv_obj_t *l = lv_label_create(c->type_layer);
    if (c->word_font_loaded)
        lv_obj_set_style_text_font(l, (const lv_font_t *)c->word_font, LV_PART_MAIN);
    lv_obj_set_style_text_color(l, color, LV_PART_MAIN);
    lv_obj_align(l, LV_ALIGN_CENTER, x - 233, y - 233);
    return l;
}

static void build_type_layer(struct remote_ctx *c)
{
    c->type_layer = lv_obj_create(c->root);
    lv_obj_set_size(c->type_layer, 466, 466);
    lv_obj_align(c->type_layer, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_bg_color(c->type_layer, LV_COLOR_HEX(0x000000), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(c->type_layer, LV_OPA_COVER, LV_PART_MAIN);
    plain(c->type_layer);
    lv_obj_add_flag(c->type_layer, LV_OBJ_FLAG_HIDDEN);

    for (uint8_t i = 0; i < 10; i++) {
        lv_coord_t cx = i == MID_KEY ? (MID_X0 + MID_X1) / 2 : GRID_X0 + i % 3 * GRID_DX;
        lv_coord_t cy = i == MID_KEY ? (BOTTOM_Y0 + BOTTOM_Y1) / 2 : GRID_Y0 + i / 3 * GRID_DY;
        lv_coord_t off = i == MID_KEY ? 40 : 28;
        for (uint8_t k = 0; k < 3; k++)
            c->keys[i * 3 + k] = type_label(c, cx + (int)k * off - off, cy, label_color(i * 3 + k));
    }
    c->keys[LABEL_TOGGLE] = type_label(c, (TOGGLE_X0 + TOGGLE_X1) / 2, (BOTTOM_Y0 + BOTTOM_Y1) / 2, COLOR_INK);
    c->keys[LABEL_DELETE] = type_label(c, (DEL_X0 + DEL_X1) / 2, (BOTTOM_Y0 + BOTTOM_Y1) / 2, COLOR_INK);
    lv_label_set_text_static(c->keys[LABEL_DELETE], "DEL");

    c->preview = lv_label_create(c->type_layer);
    if (c->word_font_loaded)
        lv_obj_set_style_text_font(c->preview, (const lv_font_t *)c->word_font, LV_PART_MAIN);
    lv_obj_set_style_text_color(c->preview, COLOR_ACCENT, LV_PART_MAIN);
    lv_obj_set_width(c->preview, 400);
    lv_obj_set_style_text_align(c->preview, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_obj_align(c->preview, LV_ALIGN_CENTER, 0, -153);
    set_page(c, PAGE_LETTERS);
}

static int inflate(struct jx_view *v)
{
    struct remote_ctx *c = v->ctx;
    remote_log("faceclaw-remote: inflate ctx %x\n", (unsigned)c);
    if (!c->clock_font_loaded && stock_font_load(c->clock_font, "/NAND:A/nm104N.font") >= 0)
        c->clock_font_loaded = 1;
    if (!c->word_font_loaded && stock_font_load(c->word_font, "/NAND:A/font36N.font") >= 0)
        c->word_font_loaded = 1;
    c->scr = lv_disp_get_scr_act(v->view_data[0]);
    c->root = lv_obj_create(c->scr);
    lv_obj_set_size(c->root, 466, 466);
    lv_obj_align(c->root, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_bg_color(c->root, LV_COLOR_HEX(0x000000), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(c->root, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(c->root, 0, LV_PART_MAIN);
    lv_obj_clear_flag(c->root, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_add_flag(c->root, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(c->root, on_touch, LV_EVENT_ALL, c);
    lv_obj_add_event_cb(c->root, on_knob, LV_EVENT_KNOB, c);

    c->led = lv_obj_create(c->root);
    lv_obj_set_size(c->led, 18, 18);
    lv_obj_set_style_radius(c->led, 9, LV_PART_MAIN);
    lv_obj_set_style_border_width(c->led, 0, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(c->led, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_clear_flag(c->led, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_align(c->led, LV_ALIGN_TOP_MID, 0, 56);

    c->hours = dot_label(c, 1, COLOR_INK, -78);
    c->minutes = dot_label(c, 1, COLOR_INK, 38);
    c->status = dot_label(c, 0, COLOR_MUTED, 142);
    build_type_layer(c);
    c->mode = MODE_REMOTE;
    c->type_key = KEY_NONE;
    c->hot = LABEL_NONE;

    c->linked = stock_phone_connection() != 0;
    c->flash_ticks = 0;
    update_clock(c, 1);
    paint_idle(c);
    c->tick_timer = lv_timer_create(tick, TICK_MS, c);
    remote_prime();
    screen_hold(c);
    return 0;
}

static int destroy(struct jx_view *v)
{
    struct remote_ctx *c = v->ctx;
    remote_log("faceclaw-remote: destroy %d\n", 0);
    screen_release(c);
    cancel_tap_timer(c);
    cancel_repeat(c);
    if (c->exit_timer) {
        lv_timer_del(c->exit_timer);
        c->exit_timer = 0;
    }
    if (c->tick_timer) {
        lv_timer_del(c->tick_timer);
        c->tick_timer = 0;
    }
    if (c->root) {
        lv_obj_del(c->root);
        c->root = 0;
        c->status = 0;
        c->hours = 0;
        c->minutes = 0;
        c->led = 0;
        c->type_layer = 0;
    }
    if (c->clock_font_loaded) {
        stock_font_unload(c->clock_font);
        c->clock_font_loaded = 0;
    }
    if (c->word_font_loaded) {
        stock_font_unload(c->word_font);
        c->word_font_loaded = 0;
    }
    return 0;
}

static int lang_change(struct jx_view *v, int x) { (void)v; (void)x; return 0; }

#define CROWN_SHORT_DOWN 0x20000001u
#define CROWN_SHORT_UP 0x04000001u
#define CROWN_LONG_DOWN 0x10000001u
#define CROWN_LONG_UP 0x02000001u
#define CROWN_DOUBLE 0x40000001u

static int key(struct jx_view *v, unsigned event)
{
    struct remote_ctx *c = v->ctx;
    remote_log("faceclaw-remote: crown %x\n", event);
    switch (event) {
    case CROWN_SHORT_DOWN:
        c->crown_down = 1;
        return 1;
    case CROWN_SHORT_UP:
        if (c->crown_down) {
            c->crown_down = 0;
            if (c->mode == MODE_TYPE)
                set_mode(c, MODE_REMOTE);
            else
                send(c, KEY_MUTE, "VOICE");
        }
        return 1;
    case CROWN_LONG_DOWN:
        c->crown_down = 0;
        stock_view_open(VOICE_ASSISTANT_VIEW_ID, 0);
        return 1;
    case CROWN_LONG_UP:
    case CROWN_DOUBLE:
        c->crown_down = 0;
        return 1;
    case TP_SWIPE_DOWN:
    case TP_SWIPE_UP:
    case TP_SWIPE_LEFT:
    case TP_SWIPE_RIGHT:
        /* The touch controller also reports swipes as keys; unclaimed, swipe right is
           the global "back". The LVGL gesture handler sends them instead. */
        return 1;
    default:
        return 0;
    }
}

static int generic(struct jx_view *v, unsigned msg) { (void)v; (void)msg; return 0; }

static const struct view_reg remote_reg = {
    .flags0 = 0, .flags1 = 0x02, .id = REMOTE_VIEW_ID,
    .ctx_size = sizeof(struct remote_ctx), .scene_id = VOICE_ASSISTANT_SCENE,
    .create_a = noop, .create_b = noop, .focus = focus, .get_res_dsc = stock_voice_assistant_res_dsc,
    .inflate = inflate, .destroy = destroy, .lang_change = lang_change,
    .key = key, .event = generic,
};

int remote_view_proc(unsigned id, void *view_data, unsigned msg, void *msg_data)
{
    return stock_ui_view_creater(&remote_reg, id, view_data, msg, msg_data);
}
