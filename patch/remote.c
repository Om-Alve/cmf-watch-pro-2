#include "remote.h"

extern void stock_log_1(unsigned ids, const char *fmt, unsigned arg);

void remote_log(const char *fmt, unsigned arg)
{
    stock_log_1(0x05550031u | ((0x101df57cu - 0x101df314u) << 5 & 0xff00u), fmt, arg);
}

void remote_on_boot(void)
{
    remote_log("faceclaw-remote: cave alive %d\n", 1234);
}
