class EMMC:
    def __init__(self, protocol):
        self.protocol = protocol

    def init(self):
        self.protocol.init()

    def identify(self):
        self.protocol.identify()

    def check_pins(self):
        self.protocol.check_pins()

    def version(self):
        self.protocol.version()

    def gpt(self):
        self.protocol.gpt()

    def isp_cmd_test(self, cycles=6):
        self.protocol.isp_cmd_test(cycles)

    def clk_test(self, frequency_hz=400000, duration_ms=1000):
        self.protocol.clk_test(frequency_hz, duration_ms)

    def pin_test_clk(self, level="HIGH"):
        self.protocol.pin_test_clk(level)

    def pin_test_cmd_dat0(self):
        self.protocol.pin_test_cmd_dat0()

    def pin_test_cmd(self, level="HIGH"):
        self.protocol.pin_test_cmd(level)

    def pin_test_dat0(self, level="HIGH"):
        self.protocol.pin_test_dat0(level)

    def isp_cmd1_test(self, retries=16, arg=0x40FF8000):
        self.protocol.isp_cmd1_test(retries, arg)

    def isp_sd_test(self, retries=24, arg=0x40FF8000):
        self.protocol.isp_sd_test(retries, arg)

    def signal_monitor_start(self, frequency_hz=400000):
        self.protocol.signal_monitor_start(frequency_hz)

    def signal_monitor_stop(self):
        self.protocol.signal_monitor_stop()

    def stop_tests(self):
        self.protocol.stop_tests()

    def cid(self):
        self.protocol.read_cid()

    def extcsd(self):
        self.protocol.read_extcsd()

    def layout(self):
        self.protocol.layout()

    def dump_start(self, start_lba, block_count, chunk_bytes=512, use_pio=True, auto_retries=3, partition=0):
        self.protocol.dump_start(start_lba, block_count, chunk_bytes, use_pio, auto_retries, partition)

    def dump_stop(self):
        self.protocol.dump_stop()

    def backup(self, start, count):
        self.protocol.read(start, count)

    def restore(self, start, count):
        self.protocol.write(start, count)

    def erase(self, start, count):
        self.protocol.erase(start, count)
