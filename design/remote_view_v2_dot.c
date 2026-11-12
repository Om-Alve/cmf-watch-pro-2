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

/* ux2sys id 38: vibrate at the user's strength (vibration off = no buzz). */
#define UX2SYS_VIBRATE 38
#define VIBRATE_60MS 6
#define VIBRATE_20MS 8

#define COLOR_ACCENT LV_COLOR_HEX(0xF0552D)
#define COLOR_INK LV_COLOR_HEX(0xF0F0F0)
#define COLOR_MUTED LV_COLOR_HEX(0x9A9EA3)
#define FLASH_TICKS 3          /* x 500 ms */
#define TICK_MS 500

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

static void tick(lv_timer_t *timer)
{
    struct remote_ctx *c = lv_timer_user_data(timer);
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

static void on_touch(lv_event_t *e)
{
    struct remote_ctx *c = lv_event_user_data(e);
    switch (lv_event_get_code(e)) {
    case LV_EVENT_PRESSED:
        if (c->second_press) {
            cancel_tap_timer(c);
            c->pending_tap = 0;
            c->second_press = 0;
        } else if (c->pending_tap) {
            cancel_tap_timer(c);
            c->second_press = 1;
        }
        break;
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
    if (*step > 0)
        send(c, KEY_LAST, "DOWN");
    else
        send(c, KEY_VOLUMEUP, "UP");
}

static int noop(struct jx_view *v) { (void)v; return 0; }
static int noop_focus(struct jx_view *v, int f) { (void)v; (void)f; return 0; }

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
    lv_obj_clear_flag(c->root, LV_OBJ_FLAG_SCROLLABLE);
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

    c->linked = stock_phone_connection() != 0;
    c->flash_ticks = 0;
    update_clock(c, 1);
    paint_idle(c);
    c->tick_timer = lv_timer_create(tick, TICK_MS, c);
    remote_prime();
    return 0;
}

static int destroy(struct jx_view *v)
{
    struct remote_ctx *c = v->ctx;
    remote_log("faceclaw-remote: destroy %d\n", 0);
    cancel_tap_timer(c);
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
    default:
        return 0;
    }
}

static int generic(struct jx_view *v, unsigned msg) { (void)v; (void)msg; return 0; }

static const struct view_reg remote_reg = {
    .flags0 = 0, .flags1 = 0x02, .id = REMOTE_VIEW_ID,
    .ctx_size = sizeof(struct remote_ctx), .scene_id = VOICE_ASSISTANT_SCENE,
    .create_a = noop, .create_b = noop, .focus = noop_focus, .get_res_dsc = stock_voice_assistant_res_dsc,
    .inflate = inflate, .destroy = destroy, .lang_change = lang_change,
    .key = key, .event = generic,
};

int remote_view_proc(unsigned id, void *view_data, unsigned msg, void *msg_data)
{
    return stock_ui_view_creater(&remote_reg, id, view_data, msg, msg_data);
}
