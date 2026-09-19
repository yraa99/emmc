#ifndef APP_TRANSPORT_H
#define APP_TRANSPORT_H

#include <stdbool.h>
#include <stdint.h>

/* USB CDC transport used by the active RP2040 eMMC firmware. */
bool app_send_text(const char *text);
bool app_send_binary(const uint8_t *data, uint16_t len);
uint8_t app_debug_level(void);
void app_debug_log(uint8_t level, const char *scope, const char *msg);

#endif
