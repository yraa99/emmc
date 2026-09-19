/*
 * src/main.c - REAL eMMC ISP Firmware for RP2040
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "tusb.h"
#include "pico/time.h"
#include "proto_emmc.h"

// 1. Ekspor fungsi eksternal agar tidak dibuang oleh compiler (-O3)
extern uint8_t app_debug_level(void);
extern void app_debug_log(uint8_t level, const char *scope, const char *msg);

// 2. Deklarasi fungsi asli dari proto_emmc.c
extern void proto_emmc_init(void);
extern bool emmc_read_block(uint32_t lba, bool hc_addressing, uint8_t out[512], char *msg, size_t msg_len);

// Variabel status addressing internal
static bool g_hc_addressing = false;

bool app_send_text(const char *text);


/* -------------------------------------------------------------------------
 * ISP / Signal Monitor
 * GPIO mapping: CMD=7, CLK=8, DAT0=9.
 * The monitor is deliberately isolated from the normal eMMC protocol path.
 * CLK uses RP2040 PWM so the requested frequency is generated continuously
 * while USB and the realtime status reporter remain responsive.
 * ------------------------------------------------------------------------- */
static bool g_signal_monitor_active = false;
static uint32_t g_signal_monitor_requested_hz = 400000u;
static uint32_t g_signal_monitor_actual_hz = 0u;
static uint32_t g_signal_monitor_last_status_ms = 0u;
static uint g_signal_monitor_slice = 0u;
static uint16_t g_signal_monitor_wrap = 0u;
static float g_signal_monitor_div = 1.0f;

static const char *signal_level_name(unsigned level) {
    return level ? "HIGH" : "LOW";
}

static void signal_monitor_stop(void) {
    if (g_signal_monitor_active) {
        pwm_set_enabled(g_signal_monitor_slice, false);
    }
    g_signal_monitor_active = false;
    g_signal_monitor_actual_hz = 0u;

    gpio_set_function(8, GPIO_FUNC_SIO);
    gpio_init(8);
    gpio_put(8, 0u);
    gpio_set_dir(8, GPIO_IN);
    gpio_disable_pulls(8);

    gpio_init(7);
    gpio_set_dir(7, GPIO_IN);
    gpio_disable_pulls(7);
    gpio_init(9);
    gpio_set_dir(9, GPIO_IN);
    gpio_disable_pulls(9);
}

static bool signal_monitor_start(uint32_t requested_hz) {
    if (requested_hz < 1000u) requested_hz = 1000u;
    if (requested_hz > 4000000u) requested_hz = 4000000u;

    signal_monitor_stop();

    /* Monitor/test mode: CMD and DAT0 are inputs; only CLK is generated. */
    gpio_set_function(7, GPIO_FUNC_SIO);
    gpio_init(7);
    gpio_set_dir(7, GPIO_IN);
    gpio_disable_pulls(7);
    gpio_set_function(9, GPIO_FUNC_SIO);
    gpio_init(9);
    gpio_set_dir(9, GPIO_IN);
    gpio_disable_pulls(9);

    gpio_set_function(8, GPIO_FUNC_PWM);
    g_signal_monitor_slice = pwm_gpio_to_slice_num(8);
    uint32_t sys_hz = clock_get_hz(clk_sys);
    if (sys_hz == 0u) sys_hz = 125000000u;

    /* Select a divider/wrap pair that fits the PWM counter and is as close as
       possible to the requested frequency. */
    double period_counts = (double)sys_hz / (double)requested_hz;
    uint32_t divider_int = 1u;
    if (period_counts > 65536.0) {
        divider_int = (uint32_t)((period_counts + 65535.0) / 65536.0);
        if (divider_int > 255u) divider_int = 255u;
    }
    uint32_t wrap = (uint32_t)((double)sys_hz / ((double)divider_int * (double)requested_hz) + 0.5);
    if (wrap < 2u) wrap = 2u;
    if (wrap > 65536u) wrap = 65536u;
    uint32_t top = wrap - 1u;

    pwm_config cfg = pwm_get_default_config();
    pwm_config_set_clkdiv(&cfg, (float)divider_int);
    pwm_config_set_wrap(&cfg, (uint16_t)top);
    pwm_config_set_phase_correct(&cfg, false);
    pwm_init(g_signal_monitor_slice, &cfg, false);
    pwm_set_gpio_level(8, (uint16_t)(top / 2u));
    pwm_set_enabled(g_signal_monitor_slice, true);

    g_signal_monitor_requested_hz = requested_hz;
    g_signal_monitor_wrap = (uint16_t)top;
    g_signal_monitor_div = (float)divider_int;
    g_signal_monitor_actual_hz = (uint32_t)((double)sys_hz / ((double)divider_int * (double)(top + 1u)) + 0.5);
    g_signal_monitor_active = true;
    g_signal_monitor_last_status_ms = 0u;
    return true;
}

static void signal_monitor_send_status(void) {
    if (!g_signal_monitor_active) return;
    uint32_t now = to_ms_since_boot(get_absolute_time());
    if ((now - g_signal_monitor_last_status_ms) < 150u) return;
    g_signal_monitor_last_status_ms = now;

    static unsigned prev_cmd = 0u;
    static unsigned prev_dat0 = 0u;
    static bool prev_valid = false;
    unsigned cmd = gpio_get(7) ? 1u : 0u;
    unsigned clk = gpio_get(8) ? 1u : 0u;
    unsigned dat0 = gpio_get(9) ? 1u : 0u;
    const char *cmd_state = signal_level_name(cmd);
    const char *dat0_state = signal_level_name(dat0);
    if (prev_valid && cmd != prev_cmd) cmd_state = "TOGGLING";
    if (prev_valid && dat0 != prev_dat0) dat0_state = "TOGGLING";
    prev_cmd = cmd;
    prev_dat0 = dat0;
    prev_valid = true;
    const char *clk_state = "TOGGLING";
    char out[320];
    snprintf(out, sizeof(out),
             "{\"type\":\"signal.status\",\"cmd\":%u,\"clk\":%u,\"dat0\":%u,"
             "\"cmd_state\":\"%s\",\"clk_state\":\"%s\",\"dat0_state\":\"%s\","
             "\"frequency_hz\":%lu,\"requested_frequency_hz\":%lu}\n",
             cmd, clk, dat0, cmd_state, clk_state, dat0_state,
             (unsigned long)g_signal_monitor_actual_hz,
             (unsigned long)g_signal_monitor_requested_hz);
    app_send_text(out);
}

// Implementasi Debug Log yang dibutuhkan oleh proto_emmc.c
uint8_t app_debug_level(void) {
    // Level 2 exposes every CMD1 attempt and its raw response for link diagnosis.
    return 2;
}

void app_debug_log(uint8_t level, const char *scope, const char *msg) {
    if (level <= app_debug_level() && tud_cdc_connected()) {
        char buf[256];
        snprintf(buf, sizeof(buf), "[%s] %s\r\n", scope, msg);
        tud_cdc_write(buf, strlen(buf));
        tud_cdc_write_flush();
    }
}

// Fungsi pengiriman teks via USB CDC ke GUI Python
bool app_send_text(const char *text) {
    if (!text || !tud_cdc_connected()) return false;

    /*
     * tud_cdc_write() is bounded by the currently available CDC TX buffer.
     * Long JSON replies (notably the 512-byte EXT_CSD = 1024 hex chars)
     * must therefore be drained in chunks; otherwise IDENTIFY/GPT can look
     * successful in firmware while the GUI receives a truncated JSON frame.
     */
    size_t len = strlen(text);
    size_t sent = 0u;
    while (sent < len) {
        if (!tud_cdc_connected()) return false;
        uint32_t avail = tud_cdc_write_available();
        if (avail == 0u) {
            tud_task();
            sleep_us(50);
            continue;
        }
        size_t chunk = (size_t)avail;
        if (chunk > (len - sent)) chunk = len - sent;
        tud_cdc_write(text + sent, (uint32_t)chunk);
        tud_cdc_write_flush();
        sent += chunk;
        tud_task();
    }
    return true;
}

// Fungsi pengiriman data biner mentah sektor eMMC ke GUI Python (dengan jeda stabilisasi USB)
bool app_send_binary(const uint8_t *data, uint16_t len) {
    if (tud_cdc_connected()) {
        uint16_t sent = 0;
        while (sent < len) {
            uint16_t chunk = tud_cdc_write_available();
            if (chunk > 0) {
                if (chunk > (len - sent)) chunk = len - sent;
                tud_cdc_write(data + sent, chunk);
                tud_cdc_write_flush();
                sent += chunk;
                sleep_us(50);
            } else {
                tud_task();
            }
        }
        return true;
    }
    return false;
}

// Handler pemrosesan perintah dari GUI Python

static uint64_t gpt_le64(const uint8_t *p) {
    return ((uint64_t)p[0]) | ((uint64_t)p[1] << 8) | ((uint64_t)p[2] << 16) | ((uint64_t)p[3] << 24) |
           ((uint64_t)p[4] << 32) | ((uint64_t)p[5] << 40) | ((uint64_t)p[6] << 48) | ((uint64_t)p[7] << 56);
}

static uint32_t gpt_le32(const uint8_t *p) {
    return ((uint32_t)p[0]) | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void gpt_utf16_name(const uint8_t *src, char *dst, size_t dst_len) {
    size_t o = 0;
    for (size_t i = 0; i < 36 && o + 1 < dst_len; ++i) {
        uint16_t c = (uint16_t)src[i * 2] | ((uint16_t)src[i * 2 + 1] << 8);
        if (c == 0) break;
        if (c == '"' || c == '\\') dst[o++] = '_';
        else if (c >= 0x20 && c <= 0x7e) dst[o++] = (char)c;
        else dst[o++] = '_';
    }
    dst[o] = '\0';
}

static bool send_gpt_result(void) {
    uint8_t hdr[512];
    char msg[96];
    if (!emmc_read_block(1u, g_hc_addressing, hdr, msg, sizeof(msg))) {
        char out[192];
        snprintf(out, sizeof(out), "{\"type\":\"emmc.gpt.result\",\"ok\":false,\"msg\":\"%s\"}\n", msg);
        return app_send_text(out);
    }
    if (memcmp(hdr, "EFI PART", 8) != 0) {
        return app_send_text("{\"type\":\"emmc.gpt.result\",\"ok\":false,\"msg\":\"GPT signature not found\"}\n");
    }

    uint32_t header_size = gpt_le32(&hdr[12]);
    uint64_t first_usable = gpt_le64(&hdr[40]);
    uint64_t last_usable = gpt_le64(&hdr[48]);
    uint64_t entries_lba = gpt_le64(&hdr[72]);
    uint32_t entry_count = gpt_le32(&hdr[80]);
    uint32_t entry_size = gpt_le32(&hdr[84]);
    uint32_t valid_partitions = 0u;
    if (header_size < 92u || header_size > 512u || entry_size < 128u || entry_size > 512u || entry_count == 0u) {
        return app_send_text("{\"type\":\"emmc.gpt.result\",\"ok\":false,\"msg\":\"Invalid GPT header\"}\n");
    }
    if (entry_count > 128u) entry_count = 128u;

    char out[320];
    snprintf(out, sizeof(out), "{\"type\":\"emmc.gpt.begin\",\"ok\":true,\"first_usable\":%llu,\"last_usable\":%llu,\"entries\":%lu,\"entry_size\":%lu}\n",
             (unsigned long long)first_usable, (unsigned long long)last_usable,
             (unsigned long)entry_count, (unsigned long)entry_size);
    if (!app_send_text(out)) return false;

    uint8_t sector[512];
    uint64_t current_lba = UINT64_MAX;
    for (uint32_t i = 0; i < entry_count; ++i) {
        uint64_t byte_off = (uint64_t)i * entry_size;
        uint64_t lba = entries_lba + byte_off / 512u;
        uint32_t off = (uint32_t)(byte_off % 512u);
        if (lba != current_lba) {
            if (!emmc_read_block((uint32_t)lba, g_hc_addressing, sector, msg, sizeof(msg))) {
                snprintf(out, sizeof(out), "{\"type\":\"emmc.gpt.result\",\"ok\":false,\"msg\":\"GPT entry read failed: %s\"}\n", msg);
                app_send_text(out);
                return false;
            }
            current_lba = lba;
        }
        uint8_t entry_buf[512];
        const uint8_t *e;
        if (off + entry_size <= 512u) {
            e = &sector[off];
        } else {
            uint8_t next_sector[512];
            if (!emmc_read_block((uint32_t)(lba + 1u), g_hc_addressing, next_sector, msg, sizeof(msg))) {
                snprintf(out, sizeof(out), "{\"type\":\"emmc.gpt.result\",\"ok\":false,\"msg\":\"GPT entry continuation read failed: %s\"}\n", msg);
                app_send_text(out);
                return false;
            }
            uint32_t first_part = 512u - off;
            memcpy(entry_buf, &sector[off], first_part);
            memcpy(entry_buf + first_part, next_sector, entry_size - first_part);
            e = entry_buf;
        }
        bool empty = true;
        for (int b = 0; b < 16; ++b) if (e[b] != 0) { empty = false; break; }
        if (empty) continue;
        uint64_t first = gpt_le64(&e[32]);
        uint64_t last = gpt_le64(&e[40]);
        if (last < first) continue;
        char name[80];
        gpt_utf16_name(&e[56], name, sizeof(name));
        snprintf(out, sizeof(out), "{\"type\":\"emmc.gpt.partition\",\"index\":%lu,\"name\":\"%s\",\"start_lba\":%llu,\"end_lba\":%llu,\"sectors\":%llu}\n",
                   (unsigned long)i, name, (unsigned long long)first, (unsigned long long)last,
                   (unsigned long long)(last - first + 1ull));
        if (!app_send_text(out)) return false;
        valid_partitions++;
    }
    snprintf(out, sizeof(out),
             "{\"type\":\"emmc.gpt.end\",\"ok\":true,\"partitions\":%lu,\"entries_lba\":%llu}\n",
             (unsigned long)valid_partitions, (unsigned long long)entries_lba);
    return app_send_text(out);
}

static void process_command(char *cmd) {
    cmd[strcspn(cmd, "\r\n")] = 0;
    if (strlen(cmd) == 0) return;

    if (strcmp(cmd, "INIT") == 0) {
        // If the diagnostic PWM monitor was running, release GPIO8 before
        // handing GPIO7/8/9 back to the eMMC bit-bang driver.
        signal_monitor_stop();
        app_debug_log(1, "EMMC", "Initializing eMMC Hardware...");
        proto_emmc_init();
        app_send_text("OK INIT\n");
        return;
    }

    if (strncmp(cmd, "SIGNAL_MONITOR_START", 20) == 0 && (cmd[20] == 0 || cmd[20] == ' ')) {
        unsigned frequency_hz = 400000u;
        (void)sscanf(cmd + 20, "%u", &frequency_hz);
        if (signal_monitor_start(frequency_hz)) {
            char out[192];
            snprintf(out, sizeof(out),
                     "{\"type\":\"signal.started\",\"ok\":true,\"frequency_hz\":%lu,\"requested_frequency_hz\":%lu}\n",
                     (unsigned long)g_signal_monitor_actual_hz,
                     (unsigned long)g_signal_monitor_requested_hz);
            app_send_text(out);
        } else {
            app_send_text("{\"type\":\"signal.started\",\"ok\":false}\n");
        }
        return;
    }

    if (strcmp(cmd, "SIGNAL_MONITOR_STOP") == 0) {
        signal_monitor_stop();
        app_send_text("{\"type\":\"signal.stopped\",\"ok\":true}\n");
        return;
    }

    if (strcmp(cmd, "CHECK_PINS") == 0) {
        gpio_init(7); gpio_set_dir(7, GPIO_IN); gpio_pull_up(7);
        gpio_init(8); gpio_set_dir(8, GPIO_IN); gpio_pull_up(8);
        gpio_init(9); gpio_set_dir(9, GPIO_IN); gpio_pull_up(9);
        sleep_ms(10);
        char pin_status[96];
        snprintf(pin_status, sizeof(pin_status), "CMD:%s,CLK:%s,DAT0:%s\n",
                 gpio_get(7) ? "OK" : "LOW",
                 gpio_get(8) ? "OK" : "LOW",
                 gpio_get(9) ? "OK" : "LOW");
        app_send_text(pin_status);
        return;
    }

    /* Static pin tests for hardware path verification.
       CLK/CMD/DAT0: PIN_TEST <PIN> HIGH|LOW
       These tests must be run with eMMC disconnected. */
    if (strncmp(cmd, "PIN_TEST", 8) == 0 && (cmd[8] == 0 || cmd[8] == ' ')) {
        char pin_name[16] = {0};
        char level[16] = {0};

        if (sscanf(cmd + 8, "%15s %15s", pin_name, level) == 2) {
            bool high = (strcmp(level, "HIGH") == 0 || strcmp(level, "high") == 0);
            bool low  = (strcmp(level, "LOW") == 0 || strcmp(level, "low") == 0);
            uint gpio = 0;
            const char *canonical = NULL;

            if (strcmp(pin_name, "CLK") == 0 || strcmp(pin_name, "clk") == 0) {
                gpio = 8;
                canonical = "CLK";
            } else if (strcmp(pin_name, "CMD") == 0 || strcmp(pin_name, "cmd") == 0) {
                gpio = 7;
                canonical = "CMD";
            } else if (strcmp(pin_name, "DAT0") == 0 || strcmp(pin_name, "dat0") == 0) {
                gpio = 9;
                canonical = "DAT0";
            }

            if (canonical != NULL && (high || low)) {
                /* Force the RP2040 pin back to plain SIO GPIO.
                   This is important because the eMMC driver may previously
                   have used SPI/PIO/DMA on GPIO7/8/9. */
                gpio_set_function(gpio, GPIO_FUNC_SIO);
                gpio_init(gpio);
                gpio_disable_pulls(gpio);

                /* Set the output latch BEFORE enabling the output driver.
                   This avoids a wrong transient level during the test. */
                gpio_put(gpio, high ? 1u : 0u);
                gpio_set_dir(gpio, GPIO_OUT);
                sleep_us(100);

                /* Read back the actual RP2040 GPIO level so the GUI/log can
                   distinguish a firmware GPIO problem from a TXS/eMMC path. */
                unsigned readback = gpio_get(gpio) ? 1u : 0u;

                char out[256];
                snprintf(out, sizeof(out),
                         "{\"type\":\"emmc.pin_test.result\",\"ok\":%s,\"pin\":\"%s\",\"gpio\":%u,\"level\":\"%s\",\"readback\":%u}\n",
                         (readback == (high ? 1u : 0u)) ? "true" : "false",
                         canonical, gpio, high ? "HIGH" : "LOW", readback);
                app_send_text(out);
                return;
            }
        }

        app_send_text("{\"type\":\"emmc.pin_test.result\",\"ok\":false,\"msg\":\"Usage: PIN_TEST CLK|CMD|DAT0 HIGH|LOW\"}\n");
        return;
    }

    if (strcmp(cmd, "GPT") == 0) {
        /* GPT is owned by the eMMC protocol layer so it always performs a
           fresh card preparation before reading LBA1/partition entries. */
        signal_monitor_stop();
        proto_emmc_handle_text("emmc.gpt", "{\"type\":\"emmc.gpt\"}");
        return;
    }

    if (strcmp(cmd, "READ_EXTCSD") == 0 || strcmp(cmd, "EXTCSD") == 0) {
        proto_emmc_handle_text("emmc.layout.read", "{\"type\":\"emmc.layout.read\"}");
        return;
    }

    if (strcmp(cmd, "VERSION") == 0 || strcmp(cmd, "FW_VERSION") == 0) {
        app_send_text("{\"type\":\"firmware.info\",\"name\":\"eMMC Service Tool\",\"version\":\"IDENTIFY_CMD1_1V8_DEBUG\",\"build\":\"2026-09-18\"}\n");
        return;
    }

    if (strcmp(cmd, "IDENTIFY") == 0 || strcmp(cmd, "READ_CID") == 0) {
        signal_monitor_stop();
        proto_emmc_handle_text("emmc.identify", "{\"type\":\"emmc.identify\"}");
        return;
    }

    if (strncmp(cmd, "CMD_TEST", 8) == 0 && (cmd[8] == 0 || cmd[8] == ' ')) {
        signal_monitor_stop();
        unsigned cycles = 6;
        (void)sscanf(cmd + 8, "%u", &cycles);
        char json[96];
        snprintf(json, sizeof(json), "{\"type\":\"emmc.cmd_test\",\"cycles\":%u}", cycles);
        proto_emmc_handle_text("emmc.cmd_test", json);
        return;
    }

    if (strncmp(cmd, "CMD1_TEST", 9) == 0 && (cmd[9] == 0 || cmd[9] == ' ')) {
        signal_monitor_stop();
        unsigned retries = 16, arg = 0x40FF8000u;
        (void)sscanf(cmd + 9, "%u %u", &retries, &arg);
        char json[128];
        snprintf(json, sizeof(json), "{\"type\":\"emmc.cmd1_test\",\"retries\":%u,\"arg\":%u}", retries, arg);
        proto_emmc_handle_text("emmc.cmd1_test", json);
        return;
    }

    if (strncmp(cmd, "SD_TEST", 7) == 0 && (cmd[7] == 0 || cmd[7] == ' ')) {
        signal_monitor_stop();
        unsigned retries = 24, arg = 0x40FF8000u;
        (void)sscanf(cmd + 7, "%u %u", &retries, &arg);
        char json[128];
        snprintf(json, sizeof(json), "{\"type\":\"emmc.sd_test\",\"retries\":%u,\"arg\":%u}", retries, arg);
        proto_emmc_handle_text("emmc.sd_test", json);
        return;
    }

    if (strncmp(cmd, "CLK_TEST", 8) == 0 && (cmd[8] == 0 || cmd[8] == ' ')) {
        signal_monitor_stop();
        unsigned frequency_hz = 400000u;
        unsigned duration_ms = 1000u;
        (void)sscanf(cmd + 8, "%u %u", &frequency_hz, &duration_ms);
        if (frequency_hz < 1000u) frequency_hz = 1000u;
        if (frequency_hz > 4000000u) frequency_hz = 4000000u;
        if (duration_ms < 100u) duration_ms = 100u;
        if (duration_ms > 5000u) duration_ms = 5000u;

        // Isolated CLK waveform test: CMD/DAT0 are released as inputs,
        // CLK is driven push-pull with a stable 50% duty cycle.
        gpio_init(7);
        gpio_set_dir(7, GPIO_IN);
        gpio_disable_pulls(7);
        gpio_init(9);
        gpio_set_dir(9, GPIO_IN);
        gpio_disable_pulls(9);
        gpio_init(8);
        gpio_put(8, 0);
        gpio_set_dir(8, GPIO_OUT);

        uint32_t sys_hz = clock_get_hz(clk_sys);
        if (sys_hz == 0u) sys_hz = 125000000u;
        uint32_t half_cycles = (sys_hz + frequency_hz) / (frequency_hz * 2u);
        if (half_cycles == 0u) half_cycles = 1u;
        uint32_t cycles = frequency_hz * (duration_ms / 1000u);
        uint64_t half_count = ((uint64_t)frequency_hz * (uint64_t)duration_ms) / 1000ull * 2ull;
        if (half_count < 2ull) half_count = 2ull;

        char out[160];
        snprintf(out, sizeof(out), "{\"type\":\"emmc.clk_test.begin\",\"ok\":true,\"frequency_hz\":%u,\"duration_ms\":%u,\"half_cycles\":%lu}\n",
                 frequency_hz, duration_ms, (unsigned long)half_cycles);
        app_send_text(out);

        for (uint64_t i = 0; i < half_count; ++i) {
            gpio_put(8, (i & 1ull) ? 1u : 0u);
            busy_wait_at_least_cycles(half_cycles);
        }
        gpio_put(8, 0);
        gpio_set_dir(8, GPIO_IN);
        gpio_disable_pulls(8);

        snprintf(out, sizeof(out), "{\"type\":\"emmc.clk_test.result\",\"ok\":true,\"frequency_hz\":%u,\"duration_ms\":%u,\"toggles\":%llu}\n",
                 frequency_hz, duration_ms, (unsigned long long)half_count);
        app_send_text(out);
        return;
    }

    if (strcmp(cmd, "STOP") == 0) {
        signal_monitor_stop();
        proto_emmc_stop_all();
        app_send_text("OK STOP\n");
        return;
    }

    if (strncmp(cmd, "READ ", 5) == 0) {
        uint32_t start_lba = 0, count = 0;
        if (sscanf(cmd + 5, "%lu %lu", &start_lba, &count) == 2) {
            uint8_t sector_buffer[512];
            char err_msg[96];
            for (uint32_t i = 0; i < count; i++) {
                if (emmc_read_block(start_lba + i, g_hc_addressing, sector_buffer, err_msg, sizeof(err_msg)))
                    app_send_binary(sector_buffer, 512);
                else {
                    memset(sector_buffer, 0x00, 512);
                    app_send_binary(sector_buffer, 512);
                }
            }
        }
        return;
    }

    app_send_text("ERROR UNKNOWN COMMAND\n");
}

// Pembaca stream serial USB CDC secara berkala
static void handle_usb_serial(void) {
    static char rx_buffer[128];
    static uint8_t rx_index = 0;
    
    if (tud_cdc_available()) {
        char c;
        if (tud_cdc_read(&c, 1) > 0) {
            if (c == '\n' || c == '\r') {
                rx_buffer[rx_index] = '\0';
                if (rx_index > 0) {
                    process_command(rx_buffer);
                    rx_index = 0;
                }
            } else if (rx_index < sizeof(rx_buffer) - 1) {
                rx_buffer[rx_index++] = c;
            }
        }
    }
}

int main(void) {
    stdio_init_all();
    tusb_init();
    // Initialize eMMC GPIOs to safe input state and turn onboard LED ON (standby).
    proto_emmc_init();
    
    while (1) {
        tud_task();
        handle_usb_serial();
        signal_monitor_send_status();
        proto_emmc_poll();
    }
    return 0;
}
