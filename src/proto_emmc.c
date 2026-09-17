#include "proto_emmc.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "app_transport.h"
#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "emmc_dat0_rx.pio.h"
#include "pico/stdlib.h"
#include "pico/time.h"
#include "tusb.h"

#define EMMC_CMD_PIN 7
#define EMMC_CLK_PIN 8
#define EMMC_DAT0_PIN 9

#define EMMC_MIN_SPEED_HZ 100000u
#define EMMC_MAX_SPEED_HZ 4000000u
#define EMMC_MIN_IDPOLL_MS 100u
#define EMMC_MAX_IDPOLL_MS 5000u
#define EMMC_CMD_TIMEOUT_BITS 512u
#define EMMC_CMD1_RETRIES 40u
#define EMMC_CMD1_RETRY_DELAY_MS 1u
#define EMMC_CMDX_RETRIES 4u
#define EMMC_CMD7_RETRIES 6u
#define EMMC_DATA_TIMEOUT_BITS 20000u
#define EMMC_DUMP_BLOCK_SIZE 512u
#define EMMC_DUMP_CHUNK_BYTES 256u
#define EMMC_MAX_DUMP_CHUNK_BYTES 256u
#define EMMC_DUMP_READ_RETRIES 6u
#define EMMC_DUMP_AUTO_RETRIES_DEFAULT 4u
#define EMMC_DUMP_VERIFY_RETRIES_DEFAULT 1u
#define EMMC_DUMP_VERIFY_RETRIES_MAX 8u
#define EMMC_DUMP_AUTO_RETRIES_MAX 32u
#define EMMC_DUMP_WS_INTERVAL_MS 0u
#define EMMC_DUMP_WS_DATA_BYTES 256u
#define EMMC_DUMP_BURST_CHUNKS 4u
#define EMMC_DUMP_TX_FAIL_LIMIT 40u
#define EMMC_DUMP_HEARTBEAT_MS 1000u
#define EMMC_DUMP_STALL_TIMEOUT_MS 4000u
#define EMMC_SCAN_HEARTBEAT_MS 1000u
#define EMMC_FIND_HEARTBEAT_MS 1000u
#define EMMC_PIO_RX_BYTES (EMMC_DUMP_BLOCK_SIZE + 2u)
#define EMMC_RESELECT_EVERY_BLOCKS 16u
#define EMMC_CMD17_R1_EXTRA_TRIES 3u
#define EMMC_DUMP_MIN_SPEED_HZ 100000u
#define EMMC_DUMP_INTER_BLOCK_IDLE_CLKS 8u
#define EMMC_CMD_RETRY_IDLE_CLKS_DEFAULT 8u
#define EMMC_READ_BLOCK_WATCHDOG_MS 6000u
#define EMMC_FULL_REPREPARE_MAX 2u
#define WS_BIN_MAGIC 0xB0u
#define WS_CH_EMMC_DUMP_DATA 0x04u
#define WS_CH_EMMC_DUMP_RUN 0x05u

typedef struct {
  bool tristate_default;
  bool pullups_enabled;
  bool detect_enabled;
  bool idpoll_enabled;
  bool idpoll_monitor_between;
  uint32_t speed_hz;
  uint32_t idpoll_interval_ms;
  uint8_t retry_idle_clks;
  uint32_t last_detect_ms;
  uint32_t last_idpoll_ms;
  uint32_t tr_cmd;
  uint32_t tr_clk;
  uint32_t tr_dat0;
  uint32_t base_tr_cmd;
  uint32_t base_tr_clk;
  uint32_t base_tr_dat0;
  uint32_t half_period_cycles;
  uint8_t lv_cmd;
  uint8_t lv_clk;
  uint8_t lv_dat0;
  bool cmd_output;
  bool cmd_open_drain;
  uint32_t poll_count;
  bool dump_active;
  bool dump_hc_addressing;
  uint16_t dump_rca;
  uint32_t dump_start_lba;
  uint32_t dump_total_blocks;
  uint32_t dump_done_blocks;
  uint16_t dump_chunk_bytes;
  bool dump_double_read;
  bool dump_use_pio;
  uint8_t dump_verify_retries;
  uint8_t dump_auto_retries;
  uint8_t dump_block_retry_count;
  uint8_t dump_tx_fail_streak;
  bool dump_block_loaded;
  uint16_t dump_chunk_off;
  uint32_t dump_stat_read_attempts;
  uint32_t dump_stat_read_success;
  uint32_t dump_stat_cmd17_tries;
  uint32_t dump_stat_no_r1;
  uint32_t dump_stat_data_fail;
  uint32_t dump_stat_crc_fail;
  uint32_t dump_stat_resync_fail;
  uint32_t dump_stat_tx_busy;
  uint32_t dump_stat_block_normal;
  uint32_t dump_stat_block_all00;
  uint32_t dump_stat_block_allff;
  uint8_t dump_block_buf[EMMC_DUMP_BLOCK_SIZE];
  uint8_t dump_check_buf[EMMC_DUMP_BLOCK_SIZE];
  uint32_t last_dump_ms;
  uint32_t dump_last_progress_ms;
  uint32_t dump_last_status_ms;
  bool scan_active;
  uint32_t scan_start_lba;
  uint32_t scan_skip_blocks;
  uint32_t scan_total_blocks;
  uint32_t scan_done_blocks;
  uint32_t scan_nonempty_blocks;
  uint32_t scan_ranges_found;
  bool scan_in_range;
  bool scan_range_is_empty;
  uint32_t scan_range_start_lba;
  uint32_t scan_last_nonempty_lba;
  uint32_t scan_range_last_lba;
  uint32_t scan_last_status_ms;
  bool find_active;
  uint32_t find_start_lba;
  uint32_t find_max_blocks;
  uint32_t find_done_blocks;
  uint32_t find_last_status_ms;
} emmc_state_t;

static emmc_state_t g_emmc = {
    .tristate_default = true,
    .pullups_enabled = true,
    .detect_enabled = false,
    .idpoll_enabled = false,
    .idpoll_monitor_between = true,
    .speed_hz = 400000,
    .idpoll_interval_ms = 500,
    .retry_idle_clks = EMMC_CMD_RETRY_IDLE_CLKS_DEFAULT,
    .cmd_output = false,
    .cmd_open_drain = false,
    .dump_active = false,
    .dump_hc_addressing = false,
    .dump_rca = 1u,
    .dump_start_lba = 0u,
    .dump_total_blocks = 0u,
    .dump_done_blocks = 0u,
    .dump_chunk_bytes = EMMC_DUMP_CHUNK_BYTES,
    .dump_double_read = false,
    .dump_use_pio = true,
    .dump_verify_retries = EMMC_DUMP_VERIFY_RETRIES_DEFAULT,
    .dump_auto_retries = EMMC_DUMP_AUTO_RETRIES_DEFAULT,
    .dump_block_retry_count = 0u,
    .dump_tx_fail_streak = 0u,
    .dump_block_loaded = false,
    .dump_chunk_off = 0u,
    .dump_stat_read_attempts = 0u,
    .dump_stat_read_success = 0u,
    .dump_stat_cmd17_tries = 0u,
    .dump_stat_no_r1 = 0u,
    .dump_stat_data_fail = 0u,
    .dump_stat_crc_fail = 0u,
    .dump_stat_resync_fail = 0u,
    .dump_stat_tx_busy = 0u,
    .dump_stat_block_normal = 0u,
    .dump_stat_block_all00 = 0u,
    .dump_stat_block_allff = 0u,
    .last_dump_ms = 0u,
    .dump_last_progress_ms = 0u,
    .dump_last_status_ms = 0u,
    .scan_active = false,
    .scan_start_lba = 0u,
    .scan_skip_blocks = 0u,
    .scan_total_blocks = 0u,
    .scan_done_blocks = 0u,
    .scan_nonempty_blocks = 0u,
    .scan_ranges_found = 0u,
    .scan_in_range = false,
    .scan_range_is_empty = true,
    .scan_range_start_lba = 0u,
    .scan_last_nonempty_lba = 0u,
    .scan_range_last_lba = 0u,
    .scan_last_status_ms = 0u,
    .find_active = false,
    .find_start_lba = 0u,
    .find_max_blocks = 0u,
    .find_done_blocks = 0u,
    .find_last_status_ms = 0u,
};

static uint32_t now_ms(void) { return to_ms_since_boot(get_absolute_time()); }
static void snapshot_levels(void);
static void emmc_dbg(uint8_t level, const char *msg) {
  (void)app_debug_log(level, "emmc", msg);
  tud_task();
}
static void emmc_diag_stage(const char *stage) {
  char msg[160];
  snapshot_levels();
  snprintf(msg, sizeof(msg), "IDENTIFY_STAGE=%s CMD=%u CLK=%u DAT0=%u",
           stage ? stage : "?", (unsigned)g_emmc.lv_cmd,
           (unsigned)g_emmc.lv_clk, (unsigned)g_emmc.lv_dat0);
  emmc_dbg(1, msg);
}
static char g_emmc_data_err[96];
static void emmc_set_data_err(const char *msg) {
  if (!msg) msg = "";
  snprintf(g_emmc_data_err, sizeof(g_emmc_data_err), "%s", msg);
}
static void wr_le16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v & 0xFFu); p[1] = (uint8_t)((v >> 8) & 0xFFu); }
static void wr_le32(uint8_t *p, uint32_t v) {
  p[0] = (uint8_t)(v & 0xFFu);
  p[1] = (uint8_t)((v >> 8) & 0xFFu);
  p[2] = (uint8_t)((v >> 16) & 0xFFu);
  p[3] = (uint8_t)((v >> 24) & 0xFFu);
}

static bool starts_with(const char *s, const char *prefix) {
  size_t n = strlen(prefix);
  return strncmp(s, prefix, n) == 0;
}

static uint32_t clamp_u32(uint32_t v, uint32_t lo, uint32_t hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

static uint8_t clamp_retry_idle_clks(uint32_t v) {
  if (v == 0u || v == 1u || v == 4u || v == 8u) return (uint8_t)v;
  if (v <= 1u) return 1u;
  if (v <= 4u) return 4u;
  return 8u;
}

static bool json_extract_u32(const char *json, const char *key, uint32_t *out) {
  char pattern[40];
  const char *p;
  unsigned v;
  snprintf(pattern, sizeof(pattern), "\"%s\":", key);
  p = strstr(json, pattern);
  if (!p) return false;
  p += strlen(pattern);
  if (sscanf(p, "%u", &v) != 1) return false;
  *out = v;
  return true;
}

static inline void emmc_delay_half(void) {
  if (g_emmc.half_period_cycles > 0u) busy_wait_at_least_cycles(g_emmc.half_period_cycles);
  tight_loop_contents();
}

static void emmc_update_timing(void) {
  uint32_t speed = g_emmc.speed_hz;
  uint32_t sys_hz;
  uint32_t cycles;
  if (speed == 0u) speed = EMMC_MIN_SPEED_HZ;
  sys_hz = clock_get_hz(clk_sys);
  if (sys_hz == 0u) sys_hz = 125000000u;
  cycles = (sys_hz + speed) / (speed * 2u);
  if (cycles == 0u) cycles = 1u;
  g_emmc.half_period_cycles = cycles;
}

static bool json_extract_bool(const char *json, const char *key, bool *out) {
  char pattern[40];
  const char *p;
  snprintf(pattern, sizeof(pattern), "\"%s\":", key);
  p = strstr(json, pattern);
  if (!p) return false;
  p += strlen(pattern);
  if (strncmp(p, "true", 4) == 0) { *out = true; return true; }
  if (strncmp(p, "false", 5) == 0) { *out = false; return true; }
  return false;
}

static volatile bool g_led_busy = false;
static volatile bool g_led_state = true;
static repeating_timer_t g_led_timer;
static bool status_led_timer_cb(repeating_timer_t *timer) {
  (void)timer;
  if (g_led_busy) {
    g_led_state = !g_led_state;
    gpio_put(PICO_DEFAULT_LED_PIN, g_led_state ? 1u : 0u);
  } else {
    g_led_state = true;
    gpio_put(PICO_DEFAULT_LED_PIN, 1u);
  }
  return true;
}
static void status_led_init(void) {
  gpio_init(PICO_DEFAULT_LED_PIN);
  gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
  g_led_state = true;
  g_led_busy = false;
  gpio_put(PICO_DEFAULT_LED_PIN, 1u);
  add_repeating_timer_ms(-100, status_led_timer_cb, NULL, &g_led_timer);
}
static void status_led_set_busy(bool busy) {
  g_led_busy = busy;
  if (!busy) {
    g_led_state = true;
    gpio_put(PICO_DEFAULT_LED_PIN, 1u);
  }
}

static void pin_input(uint pin) {
  gpio_init(pin);
  gpio_set_dir(pin, GPIO_IN);
  gpio_disable_pulls(pin);
  if (g_emmc.pullups_enabled) gpio_pull_up(pin);
}
static void pin_output(uint pin, bool value) {
  gpio_init(pin);
  gpio_put(pin, value ? 1u : 0u);
  gpio_set_dir(pin, GPIO_OUT);
}
static void emmc_apply_safe_io(void) {
  pin_input(EMMC_CMD_PIN);
  pin_input(EMMC_CLK_PIN);
  pin_input(EMMC_DAT0_PIN);
  g_emmc.cmd_output = false;
}
static void emmc_bus_prepare(void) {
  pin_output(EMMC_CLK_PIN, true);
  pin_input(EMMC_CMD_PIN);
  g_emmc.cmd_output = false;
  pin_input(EMMC_DAT0_PIN);
}

static inline void emmc_cmd_set_output(bool level) {
  if (g_emmc.cmd_open_drain) {
    if (level) {
      if (g_emmc.cmd_output) {
        gpio_set_dir(EMMC_CMD_PIN, GPIO_IN);
        g_emmc.cmd_output = false;
      }
      gpio_disable_pulls(EMMC_CMD_PIN);
      if (g_emmc.pullups_enabled) gpio_pull_up(EMMC_CMD_PIN);
      return;
    }
    if (!g_emmc.cmd_output) {
      gpio_put(EMMC_CMD_PIN, 0u);
      gpio_set_dir(EMMC_CMD_PIN, GPIO_OUT);
      g_emmc.cmd_output = true;
    } else {
      gpio_put(EMMC_CMD_PIN, 0u);
    }
    return;
  }
  if (!g_emmc.cmd_output) {
    gpio_put(EMMC_CMD_PIN, level ? 1u : 0u);
    gpio_set_dir(EMMC_CMD_PIN, GPIO_OUT);
    g_emmc.cmd_output = true;
  } else {
    gpio_put(EMMC_CMD_PIN, level ? 1u : 0u);
  }
}

static inline void emmc_cmd_set_input(void) {
  if (g_emmc.cmd_output) {
    gpio_set_dir(EMMC_CMD_PIN, GPIO_IN);
    g_emmc.cmd_output = false;
  }
  gpio_disable_pulls(EMMC_CMD_PIN);
  if (g_emmc.pullups_enabled) gpio_pull_up(EMMC_CMD_PIN);
}

/* Clock one output bit: CMD is valid while CLK is low and is sampled on rising edge. */
static inline void emmc_clock_bit_out(uint8_t bit) {
  gpio_put(EMMC_CLK_PIN, 0u);
  emmc_delay_half();
  emmc_cmd_set_output(bit ? true : false);
  emmc_delay_half();
  gpio_put(EMMC_CLK_PIN, 1u);
  emmc_delay_half();
}

/* Clock one response bit: sample CMD immediately after the rising edge. */
static inline uint8_t emmc_clock_bit_in_cmd(void) {
  gpio_put(EMMC_CLK_PIN, 0u);
  emmc_delay_half();
  gpio_put(EMMC_CLK_PIN, 1u);
  uint8_t bit = (uint8_t)gpio_get(EMMC_CMD_PIN);
  emmc_delay_half();
  return bit;
}

static inline uint8_t emmc_clock_bit_in_dat0(void) {
  gpio_put(EMMC_CLK_PIN, 0u);
  emmc_delay_half();
  gpio_put(EMMC_CLK_PIN, 1u);
  uint8_t bit = (uint8_t)gpio_get(EMMC_DAT0_PIN);
  emmc_delay_half();
  return bit;
}

static uint8_t crc7_bytes(const uint8_t *data, size_t len) {
  uint8_t crc = 0;
  size_t i;
  for (i = 0; i < len; i++) {
    uint8_t d = data[i];
    uint8_t b;
    for (b = 0; b < 8; b++) {
      crc <<= 1u;
      if (((d ^ crc) & 0x80u) != 0u) crc ^= 0x09u;
      d <<= 1u;
    }
  }
  return (uint8_t)(crc & 0x7Fu);
}

static void bitbuf_set(uint8_t *buf, uint16_t bit_index, uint8_t bit) {
  uint16_t byte_index = (uint16_t)(bit_index >> 3);
  uint8_t mask = (uint8_t)(1u << (7u - (bit_index & 7u)));
  if (bit) buf[byte_index] |= mask;
}
static uint8_t bitbuf_get(const uint8_t *buf, uint16_t bit_index) {
  uint16_t byte_index = (uint16_t)(bit_index >> 3);
  uint8_t mask = (uint8_t)(1u << (7u - (bit_index & 7u)));
  return (buf[byte_index] & mask) ? 1u : 0u;
}
static uint32_t bitbuf_get_u32(const uint8_t *buf, uint16_t start_bit, uint8_t count) {
  uint32_t v = 0;
  uint8_t i;
  for (i = 0; i < count; i++) v = (uint32_t)((v << 1u) | bitbuf_get(buf, (uint16_t)(start_bit + i)));
  return v;
}

static bool emmc_validate_r3(const uint8_t *r3) {
  if (!r3) return false;
  if (bitbuf_get(r3, 0u) != 0u) return false;
  if (bitbuf_get(r3, 1u) != 0u) return false;
  if (bitbuf_get_u32(r3, 2u, 6u) != 1u) return false;
  if (bitbuf_get_u32(r3, 40u, 7u) != 0x7Fu) return false;
  if (bitbuf_get(r3, 47u) != 1u) return false;
  return true;
}

static uint32_t rd_le32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8u) | ((uint32_t)p[2] << 16u) | ((uint32_t)p[3] << 24u);
}
static uint32_t rd_le24(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8u) | ((uint32_t)p[2] << 16u);
}
static uint8_t bitrev8(uint8_t x) {
  x = (uint8_t)(((x & 0xF0u) >> 4u) | ((x & 0x0Fu) << 4u));
  x = (uint8_t)(((x & 0xCCu) >> 2u) | ((x & 0x33u) << 2u));
  x = (uint8_t)(((x & 0xAAu) >> 1u) | ((x & 0x55u) << 1u));
  return x;
}
static uint16_t crc16_ccitt_bytes(const uint8_t *data, size_t len) {
  uint16_t crc = 0u;
  size_t i;
  if (!data) return 0u;
  for (i = 0; i < len; i++) {
    uint8_t bit;
    crc ^= (uint16_t)((uint16_t)data[i] << 8u);
    for (bit = 0; bit < 8u; bit++) {
      if (crc & 0x8000u) crc = (uint16_t)((crc << 1u) ^ 0x1021u);
      else crc <<= 1u;
    }
  }
  return crc;
}

static bool emmc_read_response_bits(uint16_t total_bits, uint8_t *out, size_t out_size) {
  uint16_t scan;
  size_t needed = (size_t)((total_bits + 7u) >> 3u);
  if (!out || out_size < needed || total_bits == 0u) return false;
  memset(out, 0, out_size);

  /* Wait for the response start bit.  CMD is released before this function. */
  for (scan = 0; scan < EMMC_CMD_TIMEOUT_BITS; scan++) {
    if (emmc_clock_bit_in_cmd() == 0u) break;
  }
  if (scan >= EMMC_CMD_TIMEOUT_BITS) return false;
  bitbuf_set(out, 0u, 0u);

  for (uint16_t bit = 1u; bit < total_bits; bit++) {
    bitbuf_set(out, bit, emmc_clock_bit_in_cmd());
  }
  return true;
}

static bool emmc_send_cmd_raw(uint8_t cmd, uint32_t arg, uint16_t resp_bits, uint8_t *resp, size_t resp_size) {
  uint8_t frame[6];
  uint8_t i;
  emmc_cmd_set_output(true);
  frame[0] = (uint8_t)(0x40u | (cmd & 0x3Fu));
  frame[1] = (uint8_t)(arg >> 24u);
  frame[2] = (uint8_t)(arg >> 16u);
  frame[3] = (uint8_t)(arg >> 8u);
  frame[4] = (uint8_t)arg;
  frame[5] = (uint8_t)((crc7_bytes(frame, 5) << 1u) | 1u);
  for (i = 0; i < 6; i++) {
    for (uint8_t bit = 0; bit < 8; bit++) {
      emmc_clock_bit_out((uint8_t)((frame[i] >> (7u - bit)) & 1u));
    }
  }
  emmc_cmd_set_input();
  if (resp_bits == 0u) return true;
  return emmc_read_response_bits(resp_bits, resp, resp_size);
}

static void emmc_send_idle_clocks(uint32_t count) {
  emmc_cmd_set_output(true);
  for (uint32_t i = 0; i < count; i++) emmc_clock_bit_out(1u);
  emmc_cmd_set_input();
}
static inline void emmc_send_retry_idle(void) {
  if (g_emmc.dump_active && !g_emmc.dump_use_pio) return;
  if (g_emmc.retry_idle_clks == 0u) return;
  emmc_send_idle_clocks((uint32_t)g_emmc.retry_idle_clks);
}

typedef struct {
  bool ok;
  uint32_t ocr;
  uint16_t rca;
  uint8_t cid[15];
  uint8_t csd[15];
  char msg[96];
} emmc_id_data_t;

static void hex_bytes(const uint8_t *buf, size_t len, char *out, size_t out_len) {
  static const char hex[] = "0123456789ABCDEF";
  size_t p = 0;
  if (!out || out_len == 0u) return;
  for (size_t i = 0; i < len && (p + 2u) < out_len; i++) {
    out[p++] = hex[(buf[i] >> 4) & 0x0Fu];
    out[p++] = hex[buf[i] & 0x0Fu];
  }
  out[p] = 0;
}

static void r2_extract_payload_120(const uint8_t *r2_136, uint8_t out15[15]) {
  memset(out15, 0, 15);
  for (uint16_t i = 0; i < 120u; i++) bitbuf_set(out15, i, bitbuf_get(r2_136, (uint16_t)(2u + i)));
}

static void snapshot_levels(void) {
  g_emmc.lv_cmd = (uint8_t)gpio_get(EMMC_CMD_PIN);
  g_emmc.lv_clk = (uint8_t)gpio_get(EMMC_CLK_PIN);
  g_emmc.lv_dat0 = (uint8_t)gpio_get(EMMC_DAT0_PIN);
}

/* The remainder of the original source is intentionally retained by restoring main first. */
