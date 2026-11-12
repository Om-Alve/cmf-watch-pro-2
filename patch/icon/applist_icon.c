#include <stdint.h>

/* Replaces the Voice Assistant app-list icon (the row that opens the remote) in place.
 * The stock loader fills LVGL image descriptors that point into the resource manager's RAM
 * copy of the bitmap; the descriptor and its ownership are left untouched, only the pixels
 * are rewritten, and only when the format is exactly the one remote_icon_pixels was made for. */

#define VOICE_ASSISTANT_ICON_NODE 0x6538D2E9u
#define ICON_HEADER 0x0C018005u /* cf 5 (TRUE_COLOR_ALPHA), 96 x 96 */
#define ICON_BYTES (96 * 96 * 3)

struct img_dsc {
    uint32_t header;
    uint32_t data_size;
    uint8_t *data;
};

extern int stock_scene_load_images(void *scene, const uint32_t *ids, struct img_dsc *out, void *sizes, unsigned count);
extern const uint8_t remote_icon_pixels[ICON_BYTES];

int applist_load_images(void *scene, const uint32_t *ids, struct img_dsc *out, void *sizes, unsigned count)
{
    int ret = stock_scene_load_images(scene, ids, out, sizes, count);
    if (ret < 0 || !out)
        return ret;
    for (unsigned k = 0; k < count; k++) {
        if (ids[k] != VOICE_ASSISTANT_ICON_NODE)
            continue;
        struct img_dsc *img = &out[k];
        if (img->header != ICON_HEADER || img->data_size != ICON_BYTES || !img->data)
            break;
        uint8_t *dst = img->data;
        for (unsigned i = 0; i < ICON_BYTES; i++)
            dst[i] = remote_icon_pixels[i];
        break;
    }
    return ret;
}
