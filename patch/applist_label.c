#include <stdint.h>
#include "remote.h"

#define VOICE_ASSISTANT_LABEL_NODE 0xDFC8EA0Fu

struct text_record {
    char *text;
    uint32_t extra;
};

extern int stock_scene_load_texts(void *scene, const uint32_t *ids, struct text_record *out, unsigned count);

static const char remote_label[] = "Faceclaw";

int applist_load_texts(void *scene, const uint32_t *ids, struct text_record *out, unsigned count)
{
    int ret = stock_scene_load_texts(scene, ids, out, count);
    if (ret < 0)
        return ret;
    for (unsigned k = 0; k < count; k++) {
        char *text = out[k].text;
        if (ids[k] != VOICE_ASSISTANT_LABEL_NODE || !text)
            continue;
        unsigned len = 0;
        while (text[len])
            len++;
        if (len + 1 < sizeof(remote_label))
            break;
        for (unsigned i = 0; i < sizeof(remote_label); i++)
            text[i] = remote_label[i];
        break;
    }
    return ret;
}
