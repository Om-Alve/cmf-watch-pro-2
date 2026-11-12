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

struct remote_ctx {
    lv_obj_t *scr;
    lv_obj_t *root;
    lv_obj_t *title;
    lv_obj_t *status;
    lv_timer_t *tap_timer;
    uint8_t font_loaded;
    uint8_t pending_tap;
    uint8_t second_press;
    uint8_t crown_down;
    uint32_t font[16];
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

#define VOICE_ASSISTANT_VIEW_ID 0xcf

static void show(struct remote_ctx *c, const char *text)
{
    if (c->status)
        lv_label_set_text(c->status, text);
}

static void send(struct remote_ctx *c, enum remote_key key, const char *label)
{
    show(c, label);
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
        send(c, KEY_PLAYPAUSE, "Select");
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
            send(c, KEY_REWIND, "Back");
        } else {
            c->pending_tap = 1;
            c->tap_timer = lv_timer_create(tap_timeout, 300, c);
        }
        break;
    case LV_EVENT_LONG_PRESSED:
        if (c->second_press) {
            c->second_press = 0;
            c->pending_tap = 0;
            send(c, KEY_PREVIOUSSONG, "App menu");
        } else {
            send(c, KEY_NEXTSONG, "Menu");
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
        send(c, KEY_LAST, "Scroll down");
    else
        send(c, KEY_VOLUMEUP, "Scroll up");
}

static int noop(struct jx_view *v) { (void)v; return 0; }
static int noop_focus(struct jx_view *v, int f) { (void)v; (void)f; return 0; }

static int inflate(struct jx_view *v)
{
    struct remote_ctx *c = v->ctx;
    remote_log("faceclaw-remote: inflate ctx %x\n", (unsigned)c);
    if (!c->font_loaded && stock_font_load(c->font, "/NAND:A/font32M.font") >= 0)
        c->font_loaded = 1;
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

    c->title = lv_label_create(c->root);
    if (c->font_loaded)
        lv_obj_set_style_text_font(c->title, (const lv_font_t *)c->font, LV_PART_MAIN);
    lv_obj_set_style_text_color(c->title, LV_COLOR_HEX(0xFB471F), LV_PART_MAIN);
    lv_label_set_text(c->title, "Faceclaw");
    lv_obj_align(c->title, LV_ALIGN_TOP_MID, 0, 90);

    c->status = lv_label_create(c->root);
    if (c->font_loaded)
        lv_obj_set_style_text_font(c->status, (const lv_font_t *)c->font, LV_PART_MAIN);
    lv_obj_set_style_text_color(c->status, LV_COLOR_HEX(0xFFFFFF), LV_PART_MAIN);
    lv_obj_set_width(c->status, 380);
    lv_obj_set_style_text_align(c->status, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_label_set_text(c->status, "Ready");
    lv_obj_align(c->status, LV_ALIGN_CENTER, 0, 20);
    remote_prime();
    return 0;
}

static int destroy(struct jx_view *v)
{
    struct remote_ctx *c = v->ctx;
    remote_log("faceclaw-remote: destroy %d\n", 0);
    cancel_tap_timer(c);
    if (c->root) {
        lv_obj_del(c->root);
        c->root = 0;
        c->status = 0;
    }
    if (c->font_loaded) {
        stock_font_unload(c->font);
        c->font_loaded = 0;
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
            send(c, KEY_MUTE, "Voice");
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
