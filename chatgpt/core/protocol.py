class Protocol:
    def __init__(self, serial):
        self.serial = serial

    def send_command(self, cmd):
        self.serial.send(cmd.rstrip("\r\n") + "\n")

    def init(self):
        self.send_command("INIT")

    def identify(self):
        self.send_command("IDENTIFY")

    def check_pins(self):
        self.send_command("CHECK_PINS")

    def version(self):
        self.send_command("VERSION")

    def gpt(self):
        import json
        self.send_command(json.dumps({"type": "emmc.gpt"}, separators=(",", ":")))

    def isp_cmd_test(self, cycles=6):
        self.send_command(f"CMD_TEST {cycles}")

    def clk_test(self, frequency_hz=400000, duration_ms=1000):
        self.send_command(f"CLK_TEST {frequency_hz} {duration_ms}")

    # Static hardware pin tests: CMD=GPIO7, CLK=GPIO8, DAT0=GPIO9.
    def pin_test_clk(self, level="HIGH"):
        level = str(level).upper()
        if level not in ("HIGH", "LOW"):
            raise ValueError("CLK pin level must be HIGH or LOW")
        self.send_command(f"PIN_TEST CLK {level}")

    def pin_test_cmd_dat0(self):
        self.send_command("PIN_TEST CMD_DAT0")

    def pin_test_cmd(self, level="HIGH"):
        level = str(level).upper()
        if level not in ("HIGH", "LOW"):
            raise ValueError("CMD pin level must be HIGH or LOW")
        self.send_command(f"PIN_TEST CMD {level}")

    def pin_test_dat0(self, level="HIGH"):
        level = str(level).upper()
        if level not in ("HIGH", "LOW"):
            raise ValueError("DAT0 pin level must be HIGH or LOW")
        self.send_command(f"PIN_TEST DAT0 {level}")

    def isp_cmd1_test(self, retries=16, arg=0x40FF8000):
        self.send_command(f"CMD1_TEST {retries} {arg}")

    def isp_sd_test(self, retries=24, arg=0x40FF8000):
        self.send_command(f"SD_TEST {retries} {arg}")

    def signal_monitor_start(self, frequency_hz=400000):
        self.send_command(f"SIGNAL_MONITOR_START {int(frequency_hz)}")

    def signal_monitor_stop(self):
        self.send_command("SIGNAL_MONITOR_STOP")

    def stop_tests(self):
        self.send_command("STOP")

    def read_cid(self):
        self.send_command("READ_CID")

    def read_extcsd(self):
        self.send_command("READ_EXTCSD")

    def layout(self):
        self.send_command("READ_EXTCSD")

    def dump_start(self, start_lba, block_count, chunk_bytes=512, use_pio=True, auto_retries=3):
        payload = {
            "type": "emmc.dump.start",
            "start_lba": int(start_lba),
            "block_count": int(block_count),
            "chunk_bytes": int(chunk_bytes),
            "use_pio": bool(use_pio),
            "auto_retries": int(auto_retries),
        }
        import json
        self.send_command(json.dumps(payload, separators=(",", ":")))

    def dump_stop(self):
        import json
        self.send_command(json.dumps({"type": "emmc.dump.stop"}, separators=(",", ":")))

    def read(self, start, count):
        self.send_command(f"READ {start} {count}")

    def write(self, start, count):
        self.send_command(f"WRITE {start} {count}")

    def erase(self, start, count):
        self.send_command(f"ERASE {start} {count}")
