#include "remote.h"

extern int stock_hid_key(unsigned param);
extern int stock_hid_send_report(unsigned conn, unsigned type, unsigned char *buf, unsigned len);

#define REPORT_CONSUMER 2
#define KEY_PARAM_BASE 0x10
#define PRIME_PARAM 0x20

/* Text: the report byte is REWIND (bit 7) + the 7-bit ASCII code, so it never equals a
   remote key (single bits, or LAST + one other). */
#define TEXT_PARAM 0x80

#define REMOTE_KEYS 12

/* Report bit per remote key: bit0..7 = VOLUMEDOWN VOLUMEUP MUTE PLAYPAUSE PREVIOUSSONG
   NEXTSONG LAST REWIND; swipes are LAST + VOLUMEUP / MUTE / PREVIOUSSONG / NEXTSONG. */
static const unsigned char key_bits[REMOTE_KEYS] = {
    0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80,
    0x42, 0x44, 0x50, 0x60,
};

static int is_remote_key(unsigned param)
{
    return param >= KEY_PARAM_BASE && param < KEY_PARAM_BASE + REMOTE_KEYS;
}

static int is_text(unsigned param)
{
    return param > TEXT_PARAM && param <= 0xff;
}

static void send_press(unsigned conn, unsigned char report_id, unsigned char bits)
{
    unsigned char report[2] = {report_id, bits};
    remote_log("faceclaw-remote: hid report %x\n", (report[0] << 8) | report[1]);
    stock_hid_send_report(conn, 1, report, 2);
    report[1] = 0;
    stock_hid_send_report(conn, 1, report, 2);
}

void hid_press(unsigned conn, unsigned param)
{
    param &= 0xff;
    if (param == PRIME_PARAM)
        return;
    if (is_remote_key(param))
        send_press(conn, REPORT_CONSUMER, key_bits[param - KEY_PARAM_BASE]);
    else if (is_text(param))
        send_press(conn, REPORT_CONSUMER, (unsigned char)param);
    else
        send_press(conn, (unsigned char)param, 0x01);
}

void hid_press_after_connect(unsigned conn, unsigned param)
{
    param &= 0xff;
    if (param == PRIME_PARAM)
        return;
    if (is_remote_key(param)) {
        remote_log("faceclaw-remote: key %d dropped, link was reconnecting\n", param - KEY_PARAM_BASE);
        return;
    }
    if (is_text(param)) {
        remote_log("faceclaw-remote: text %x dropped, link was reconnecting\n", param & 0x7f);
        return;
    }
    send_press(conn, (unsigned char)param, 0x01);
}

void remote_key(enum remote_key key)
{
    remote_log("faceclaw-remote: key %d\n", key);
    stock_hid_key(KEY_PARAM_BASE + key);
}

void remote_text(char ch)
{
    remote_log("faceclaw-remote: text %x\n", ch & 0x7f);
    stock_hid_key(TEXT_PARAM | (ch & 0x7f));
}

void remote_prime(void)
{
    remote_log("faceclaw-remote: prime link %d\n", 0);
    stock_hid_key(PRIME_PARAM);
}
