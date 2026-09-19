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
bool emmc_prepare_card_for_data(uint16_t *out_rca, bool *out_hc, char *msg, size_t msg_len);

#endif // PROTO_EMMC_H