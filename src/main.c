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
#define GPT_BUILDPROP_MAX_CANDIDATES 8u
#define GPT_BUILDPROP_MAX_BLOCK 4096u
#define GPT_BUILDPROP_MAX_BYTES 32768u

typedef struct {
    char name[40];
    uint32_t start_lba;
    uint32_t sectors;
} buildprop_candidate_t;

static buildprop_candidate_t g_buildprop_candidates[GPT_BUILDPROP_MAX_CANDIDATES];
static uint32_t g_buildprop_candidate_count = 0u;
static bool gpt_has_super_partition = false;
static uint8_t g_ext4_block[GPT_BUILDPROP_MAX_BLOCK];
static uint8_t g_ext4_gdt[GPT_BUILDPROP_MAX_BLOCK];
static uint8_t g_ext4_sbraw[GPT_BUILDPROP_MAX_BLOCK];
static uint8_t g_ext4_root_inode[512];
static uint8_t g_ext4_file_inode[512];
static uint8_t g_buildprop_data[GPT_BUILDPROP_MAX_BYTES + 1u];

static uint16_t ext4_le16(const uint8_t *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint32_t ext4_le32(const uint8_t *p) {
    return ((uint32_t)p[0]) | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t ext4_le48(const uint8_t *p_lo, const uint8_t *p_hi) {
    return (uint64_t)ext4_le32(p_lo) | ((uint64_t)ext4_le16(p_hi) << 32);
}

static bool buildprop_name_candidate(const char *name) {
    char n[40];
    size_t i = 0u;
    if (!name) return false;
    while (name[i] && i + 1u < sizeof(n)) {
        char ch = name[i];
        if (ch >= 'A' && ch <= 'Z') ch = (char)(ch - 'A' + 'a');
        n[i++] = ch;
    }
    n[i] = 0;
    return strcmp(n, "system") == 0 || strcmp(n, "system_a") == 0 ||
           strcmp(n, "system_b") == 0 || strcmp(n, "system_ext") == 0 ||
           strcmp(n, "system_ext_a") == 0 || strcmp(n, "system_ext_b") == 0 ||
           strcmp(n, "vendor") == 0 || strcmp(n, "vendor_a") == 0 ||
           strcmp(n, "vendor_b") == 0 || strcmp(n, "product") == 0 ||
           strcmp(n, "product_a") == 0 || strcmp(n, "product_b") == 0 ||
           strcmp(n, "odm") == 0 || strcmp(n, "odm_a") == 0 ||
           strcmp(n, "odm_b") == 0;
}

static void buildprop_add_candidate(const char *name, uint64_t start, uint64_t sectors) {
    if (!buildprop_name_candidate(name) || g_buildprop_candidate_count >= GPT_BUILDPROP_MAX_CANDIDATES) return;
    if (start > UINT32_MAX || sectors == 0u || sectors > UINT32_MAX) return;
    buildprop_candidate_t *c = &g_buildprop_candidates[g_buildprop_candidate_count++];
    strncpy(c->name, name, sizeof(c->name) - 1u);
    c->name[sizeof(c->name) - 1u] = 0;
    c->start_lba = (uint32_t)start;
    c->sectors = (uint32_t)sectors;
}

static bool ext4_read_block(uint32_t part_start, uint32_t part_sectors, bool hc,
                            uint32_t fs_block, uint32_t block_size, uint8_t *out) {
    if (!out || block_size < 1024u || block_size > GPT_BUILDPROP_MAX_BLOCK ||
        (block_size % 512u) != 0u) return false;
    uint32_t sectors_per_block = block_size / 512u;
    uint64_t lba = (uint64_t)part_start + (uint64_t)fs_block * sectors_per_block;
    if (lba + sectors_per_block > (uint64_t)part_start + part_sectors || lba > UINT32_MAX) return false;
    char msg[96];
    for (uint32_t i = 0u; i < sectors_per_block; ++i) {
        if (!emmc_read_block((uint32_t)(lba + i), hc, out + i * 512u, msg, sizeof(msg))) return false;
    }
    return true;
}

static bool ext4_read_inode(uint32_t part_start, uint32_t part_sectors, bool hc,
                            uint32_t block_size, uint32_t inode_size,
                            uint32_t inodes_per_group, uint32_t desc_size,
                            uint32_t inode_no, uint8_t *inode_out, size_t inode_out_len) {
    if (!inode_out || inode_no == 0u || inode_size == 0u || inode_size > inode_out_len ||
        inodes_per_group == 0u) return false;
    uint32_t group = (inode_no - 1u) / inodes_per_group;
    uint32_t index = (inode_no - 1u) % inodes_per_group;
    uint32_t gdt_block = (block_size == 1024u) ? 2u : 1u;
    uint64_t gd_off_total = (uint64_t)group * desc_size;
    uint32_t gd_block = gdt_block + (uint32_t)(gd_off_total / block_size);
    uint32_t gd_off = (uint32_t)(gd_off_total % block_size);
    if (gd_off + 32u > block_size) return false;
    if (!ext4_read_block(part_start, part_sectors, hc, gd_block, block_size, g_ext4_gdt)) return false;
    const uint8_t *gd = &g_ext4_gdt[gd_off];
    uint64_t inode_table = ext4_le32(&gd[8]);
    if (desc_size >= 64u) inode_table |= (uint64_t)ext4_le32(&gd[40]) << 32;
    uint64_t byte_off = (uint64_t)index * inode_size;
    uint32_t fs_block = (uint32_t)(inode_table + byte_off / block_size);
    uint32_t in_block = (uint32_t)(byte_off % block_size);
    if (in_block + inode_size > block_size) return false;
    if (!ext4_read_block(part_start, part_sectors, hc, fs_block, block_size, g_ext4_block)) return false;
    memcpy(inode_out, g_ext4_block + in_block, inode_size);
    return true;
}

static bool ext4_find_root_file(uint32_t part_start, uint32_t part_sectors, bool hc,
                                uint32_t block_size, const uint8_t g_ext4_root_inode[512],
                                const char *wanted, uint32_t *out_inode) {
    uint64_t size = (uint64_t)ext4_le32(&g_ext4_root_inode[4]);
    bool extents = (ext4_le32(&g_ext4_root_inode[32]) & 0x80000u) != 0u;
    uint32_t blocks_needed = (uint32_t)((size + block_size - 1u) / block_size);
    if (blocks_needed > 32u) blocks_needed = 32u;
    if (extents) {
        const uint8_t *ib = &g_ext4_root_inode[40];
        if (ext4_le16(ib) != 0xF30Au || ext4_le16(&ib[6]) != 0u) return false;
        uint16_t entries = ext4_le16(&ib[2]);
        if (entries > 4u) entries = 4u;
        for (uint16_t eidx = 0u; eidx < entries && eidx < blocks_needed; ++eidx) {
            const uint8_t *e = &ib[12u + eidx * 12u];
            uint32_t logical = ext4_le32(e);
            uint16_t len = ext4_le16(&e[4]);
            if (len > 32768u) len = (uint16_t)(len - 32768u);
            uint64_t physical = ext4_le48(&e[8], &e[6]);
            for (uint16_t j = 0u; j < len && logical + j < blocks_needed; ++j) {
                if (!ext4_read_block(part_start, part_sectors, hc, (uint32_t)(physical + j), block_size, g_ext4_block)) return false;
                for (uint32_t off = 0u; off + 8u <= block_size; ) {
                    uint32_t ino = ext4_le32(&g_ext4_block[off]);
                    uint16_t rec = ext4_le16(&g_ext4_block[off + 4u]);
                    uint8_t nlen = g_ext4_block[off + 6u];
                    if (rec < 8u || off + rec > block_size) break;
                    if (ino && nlen == strlen(wanted) && memcmp(&g_ext4_block[off + 8u], wanted, nlen) == 0) {
                        *out_inode = ino;
                        return true;
                    }
                    off += rec;
                }
            }
        }
        return false;
    }

    if (blocks_needed > 12u) blocks_needed = 12u;
    for (uint32_t i = 0u; i < blocks_needed; ++i) {
        uint32_t phys = ext4_le32(&g_ext4_root_inode[40u + i * 4u]);
        if (!phys || !ext4_read_block(part_start, part_sectors, hc, phys, block_size, g_ext4_block)) continue;
        for (uint32_t off = 0u; off + 8u <= block_size; ) {
            uint32_t ino = ext4_le32(&g_ext4_block[off]);
            uint16_t rec = ext4_le16(&g_ext4_block[off + 4u]);
            uint8_t nlen = g_ext4_block[off + 6u];
            if (rec < 8u || off + rec > block_size) break;
            if (ino && nlen == strlen(wanted) && memcmp(&g_ext4_block[off + 8u], wanted, nlen) == 0) {
                *out_inode = ino;
                return true;
            }
            off += rec;
        }
    }
    return false;
}

static bool json_send_buildprop_chunk(const char *data, size_t len) {
    char out[900];
    char esc[700];
    size_t eo = 0u;
    for (size_t i = 0u; i < len && eo + 2u < sizeof(esc); ++i) {
        unsigned char ch = (unsigned char)data[i];
        if (ch == '\\' || ch == '"') {
            if (eo + 2u >= sizeof(esc)) break;
            esc[eo++] = '\\';
            esc[eo++] = (char)ch;
        } else if (ch == '\n') {
            if (eo + 2u >= sizeof(esc)) break;
            esc[eo++] = '\\'; esc[eo++] = 'n';
        } else if (ch == '\r') {
            if (eo + 2u >= sizeof(esc)) break;
            esc[eo++] = '\\'; esc[eo++] = 'r';
        } else if (ch == '\t') {
            if (eo + 2u >= sizeof(esc)) break;
            esc[eo++] = '\\'; esc[eo++] = 't';
        } else if (ch >= 0x20u && ch <= 0x7Eu) {
            esc[eo++] = (char)ch;
        } else {
            esc[eo++] = '?';
        }
    }
    esc[eo] = 0;
    snprintf(out, sizeof(out), "{\"type\":\"emmc.buildprop.chunk\",\"data\":\"%s\"}\n", esc);
    return app_send_text(out);
}

static bool ext4_read_buildprop(uint32_t part_start, uint32_t part_sectors, bool hc,
                                char *out_data, size_t out_len, size_t *out_size, char *msg, size_t msg_len) {
    /* Superblock starts at byte offset 1024 from the filesystem start. */
    memset(g_ext4_sbraw, 0, sizeof(g_ext4_sbraw));
    uint32_t sectors = (part_sectors >= 8u) ? 8u : part_sectors;
    char rmsg[96];
    for (uint32_t i = 0u; i < sectors; ++i) {
        if (!emmc_read_block(part_start + 2u + i, hc, g_ext4_sbraw + i * 512u, rmsg, sizeof(rmsg))) {
            snprintf(msg, msg_len, "filesystem superblock read failed"); return false;
        }
    }
    const uint8_t *s = &g_ext4_sbraw[0];
    uint16_t magic = ext4_le16(&s[56]);
    if (magic != 0xEF53u) { snprintf(msg, msg_len, "not EXT filesystem"); return false; }
    uint32_t log_bs = ext4_le32(&s[24]);
    if (log_bs > 2u) { snprintf(msg, msg_len, "unsupported EXT4 block size"); return false; }
    uint32_t block_size = 1024u << log_bs;
    uint32_t inodes_per_group = ext4_le32(&s[40]);
    uint32_t inode_size = ext4_le16(&s[88]);
    uint32_t incompat = ext4_le32(&s[96]);
    uint32_t desc_size = (incompat & 0x80u) ? ext4_le16(&s[254]) : 32u;
    if (desc_size < 32u || desc_size > 64u || inode_size < 128u || inode_size > 512u ||
        inodes_per_group == 0u) { snprintf(msg, msg_len, "invalid EXT4 geometry"); return false; }

    if (!ext4_read_inode(part_start, part_sectors, hc, block_size, inode_size,
                         inodes_per_group, desc_size, 2u, g_ext4_root_inode, sizeof(g_ext4_root_inode))) {
        snprintf(msg, msg_len, "root inode read failed"); return false;
    }
    uint32_t build_inode = 0u;
    if (!ext4_find_root_file(part_start, part_sectors, hc, block_size, g_ext4_root_inode, "build.prop", &build_inode)) {
        snprintf(msg, msg_len, "build.prop not found in filesystem root"); return false;
    }
    if (!ext4_read_inode(part_start, part_sectors, hc, block_size, inode_size,
                         inodes_per_group, desc_size, build_inode, g_ext4_file_inode, sizeof(g_ext4_file_inode))) {
        snprintf(msg, msg_len, "build.prop inode read failed"); return false;
    }
    uint64_t file_size = (uint64_t)ext4_le32(&g_ext4_file_inode[4]);
    if (file_size > GPT_BUILDPROP_MAX_BYTES) file_size = GPT_BUILDPROP_MAX_BYTES;
    if (file_size == 0u) { *out_size = 0u; return true; }

    bool extents = (ext4_le32(&g_ext4_file_inode[32]) & 0x80000u) != 0u;
    size_t produced = 0u;
    uint32_t blocks = (uint32_t)((file_size + block_size - 1u) / block_size);
    if (blocks > 32u) blocks = 32u;
    uint8_t g_ext4_block[GPT_BUILDPROP_MAX_BLOCK];

    if (extents) {
        const uint8_t *ib = &g_ext4_file_inode[40];
        if (ext4_le16(ib) != 0xF30Au || ext4_le16(&ib[6]) != 0u) {
            snprintf(msg, msg_len, "build.prop uses unsupported extent depth"); return false;
        }
        uint16_t entries = ext4_le16(&ib[2]);
        if (entries > 4u) entries = 4u;
        for (uint16_t eidx = 0u; eidx < entries && produced < file_size; ++eidx) {
            const uint8_t *e = &ib[12u + eidx * 12u];
            uint32_t logical = ext4_le32(e);
            uint16_t len = ext4_le16(&e[4]);
            if (len > 32768u) len = (uint16_t)(len - 32768u);
            uint64_t physical = ext4_le48(&e[8], &e[6]);
            if (logical >= blocks) continue;
            for (uint16_t j = 0u; j < len && logical + j < blocks && produced < file_size; ++j) {
                if (!ext4_read_block(part_start, part_sectors, hc, (uint32_t)(physical + j), block_size, g_ext4_block)) {
                    snprintf(msg, msg_len, "build.prop data read failed"); return false;
                }
                size_t take = block_size;
                if (take > file_size - produced) take = (size_t)(file_size - produced);
                if (produced + take > out_len) take = out_len - produced;
                memcpy(out_data + produced, g_ext4_block, take);
                produced += take;
            }
        }
    } else {
        for (uint32_t i = 0u; i < blocks && produced < file_size && i < 12u; ++i) {
            uint32_t phys = ext4_le32(&g_ext4_file_inode[40u + i * 4u]);
            if (!phys || !ext4_read_block(part_start, part_sectors, hc, phys, block_size, g_ext4_block)) {
                snprintf(msg, msg_len, "build.prop data block read failed"); return false;
            }
            size_t take = block_size;
            if (take > file_size - produced) take = (size_t)(file_size - produced);
            if (produced + take > out_len) take = out_len - produced;
            memcpy(out_data + produced, block, take);
            produced += take;
        }
    }
    *out_size = produced;
    if (produced == 0u) { snprintf(msg, msg_len, "build.prop data is empty or unsupported"); return false; }
    return true;
}

static int send_buildprop_for_candidate(const buildprop_candidate_t *candidate, bool hc) {
    char *data = (char *)g_buildprop_data;
    char msg[128];
    size_t size = 0u;
    char begin[160];
    snprintf(begin, sizeof(begin), "{\"type\":\"emmc.buildprop.begin\",\"partition\":\"%s\"}\n", candidate->name);
    if (!app_send_text(begin)) return -1;
    if (!ext4_read_buildprop(candidate->start_lba, candidate->sectors, hc, data, GPT_BUILDPROP_MAX_BYTES, &size, msg, sizeof(msg))) {
        char out[320];
        snprintf(out, sizeof(out), "{\"type\":\"emmc.buildprop.result\",\"ok\":false,\"partition\":\"%s\",\"msg\":\"%s\"}\n", candidate->name, msg);
        if (!app_send_text(out)) return -1;
        return 0;
    }
    data[size] = 0;
    size_t pos = 0u;
    while (pos < size) {
        size_t chunk = size - pos;
        if (chunk > 500u) chunk = 500u;
        if (!json_send_buildprop_chunk(data + pos, chunk)) return -1;
        pos += chunk;
    }
    char out[256];
    snprintf(out, sizeof(out), "{\"type\":\"emmc.buildprop.result\",\"ok\":true,\"partition\":\"%s\",\"bytes\":%lu}\n",
             candidate->name, (unsigned long)size);
    if (!app_send_text(out)) return -1;
    return 1;
}

static void scan_buildprop_after_gpt(bool hc) {
    bool found = false;
    app_send_text("{\"type\":\"emmc.buildprop.scan\",\"state\":\"start\"}\n");
    for (uint32_t i = 0u; i < g_buildprop_candidate_count; ++i) {
        int rc = send_buildprop_for_candidate(&g_buildprop_candidates[i], hc);
        if (rc < 0) return;
        if (rc > 0) { found = true; break; }
    }
    if (found) {
        app_send_text("{\"type\":\"emmc.buildprop.end\",\"ok\":true}\n");
    } else if (gpt_has_super_partition) {
        app_send_text("{\"type\":\"emmc.buildprop.end\",\"ok\":false,\"msg\":\"No physical Android partition found; GPT contains super with logical partitions not parsed by this firmware yet\"}\n");
    } else {
        app_send_text("{\"type\":\"emmc.buildprop.end\",\"ok\":false,\"msg\":\"No supported build.prop found in physical Android partitions\"}\n");
    }
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
    g_buildprop_candidate_count = 0u;
    gpt_has_super_partition = false;
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
        if (strcmp(name, "super") == 0) gpt_has_super_partition = true;
        buildprop_add_candidate(name, first, last - first + 1ull);
        valid_partitions++;
    }
    snprintf(out, sizeof(out),
             "{\"type\":\"emmc.gpt.end\",\"ok\":true,\"partitions\":%lu,\"entries_lba\":%llu}\n",
             (unsigned long)valid_partitions, (unsigned long long)entries_lba);
    if (!app_send_text(out)) return false;
    scan_buildprop_after_gpt(g_hc_addressing);
    return true;
}

bool app_handle_gpt(void) {
    signal_monitor_stop();
    proto_emmc_stop_all();
    uint16_t rca = 0u;
    bool hc = false;
    char msg[96] = {0};
    if (!emmc_prepare_card_for_data(&rca, &hc, msg, sizeof(msg))) {
        char out[192];
        snprintf(out, sizeof(out),
                 "{\"type\":\"emmc.gpt.result\",\"ok\":false,\"msg\":\"%s\"}\n",
                 msg[0] ? msg : "eMMC data preparation failed");
        app_send_text(out);
        return false;
    }
    g_hc_addressing = hc;
    return send_gpt_result();
}

static bool process_json_command(const char *cmd) {
    if (!cmd || cmd[0] != '{') return false;
    const char *p = strstr(cmd, "\"type\":\"");
    if (!p) return false;
    p += strlen("\"type\":\"");
    char type[64];
    size_t n = 0u;
    while (p[n] && p[n] != '"' && n + 1u < sizeof(type)) n++;
    if (p[n] != '"') return false;
    memcpy(type, p, n);
    type[n] = 0;
    if (strncmp(type, "emmc.", 5) != 0) return false;
    (void)proto_emmc_handle_text(type, cmd);
    return true;
}

static void process_command(char *cmd) {
    cmd[strcspn(cmd, "\r\n")] = 0;
    if (strlen(cmd) == 0) return;

    if (process_json_command(cmd)) return;

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
        /* Legacy command kept for backward compatibility. New GUI code uses
           the JSON emmc.gpt path above. */
        (void)app_handle_gpt();
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
