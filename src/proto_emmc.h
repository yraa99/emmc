#ifndef PROTO_EMMC_H
#define PROTO_EMMC_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

// --- KONFIGURASI PIN KUSTOM ---
#define EMMC_CMD_PIN  7
#define EMMC_CLK_PIN  8
#define EMMC_DAT0_PIN 9
// ------------------------------

// Fungsi antarmuka utama protokol eMMC
void proto_emmc_poll(void);
bool proto_emmc_handle_text(const char *type, const char *json);
void proto_emmc_stop_all(void);

#endif // PROTO_EMMC_H