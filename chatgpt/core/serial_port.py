import serial
import serial.tools.list_ports
import threading


class SerialPort:
    PICO_USB_VID = 0x2E8A
    PICO_KEYWORDS = ("raspberry pi pico", "raspberry pico", "rp2040", "pico")

    def __init__(self):
        self.ser = None
        self.running = False
        self.callback = None
        self.disconnect_callback = None
        self.port = None
        self._lock = threading.Lock()

    def list_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

    @classmethod
    def is_pico_port(cls, port):
        """Return True only for USB serial ports that identify as a Pico/RP2040."""
        vid = getattr(port, "vid", None)
        description = (getattr(port, "description", "") or "").lower()
        manufacturer = (getattr(port, "manufacturer", "") or "").lower()
        product = (getattr(port, "product", "") or "").lower()
        identity = " ".join((description, manufacturer, product))
        return vid == cls.PICO_USB_VID or any(keyword in identity for keyword in cls.PICO_KEYWORDS)

    @staticmethod
    def is_generic_usb_serial_port(port):
        """Recognize the generic name Windows may give to USB CDC devices."""
        description = (getattr(port, "description", "") or "").lower()
        return "usb serial" in description or "usb cdc" in description or "cdc serial" in description

    @classmethod
    def find_pico_port(cls, ports=None):
        """Find the first connected Pico USB CDC port, preferring its USB VID."""
        ports = list(ports) if ports is not None else list(serial.tools.list_ports.comports())
        pico_ports = [port for port in ports if cls.is_pico_port(port)]
        if not pico_ports:
            # Some Windows drivers hide the Pico VID/manufacturer and expose only
            # "USB Serial Device".  Use that fallback only when it is unambiguous.
            generic_usb_ports = [port for port in ports if cls.is_generic_usb_serial_port(port)]
            return generic_usb_ports[0] if len(generic_usb_ports) == 1 else None
        return next(
            (port for port in pico_ports if getattr(port, "vid", None) == cls.PICO_USB_VID),
            pico_ports[0],
        )

    def auto_detect(self):
        ports = list(serial.tools.list_ports.comports())
        pico_port = self.find_pico_port(ports)
        if pico_port:
            return pico_port.device
        # This firmware enumerates as a generic USB serial device on Windows.
        for p in ports:
            if "usb serial" in (p.description or "").lower():
                return p.device
        return None

    def connect(self, port, baud=115200):
        self.disconnect(silent=True)
        try:
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.1, write_timeout=1)
            self.port = port
            self.running = True
            threading.Thread(target=self.reader, daemon=True).start()
            return True
        except (serial.SerialException, OSError) as e:
            self.ser = None
            self.port = None
            if self.callback:
                self.callback(f"[SERIAL ERROR] {e}\n")
            return False

    def disconnect(self, silent=False):
        was_connected = self.ser is not None
        self.running = False
        with self._lock:
            ser = self.ser
            self.ser = None
            self.port = None
        if ser:
            try:
                ser.close()
            except Exception:
                pass
        if was_connected and not silent and self.disconnect_callback:
            self.disconnect_callback()

    def is_connected(self):
        return bool(self.ser and self.ser.is_open and self.running)

    def port_exists(self):
        if not self.port:
            return False
        return any(p.device == self.port for p in serial.tools.list_ports.comports())

    def send(self, data):
        if not self.is_connected():
            raise ConnectionError("RP2040 tidak terhubung")
        if isinstance(data, str):
            raw = data.encode()
        else:
            raw = data
        try:
            self.ser.write(raw)
            if self.callback:
                self.callback("[TX] " + raw.decode(errors="replace"))
        except (serial.SerialException, OSError) as e:
            self._handle_disconnect(e)
            raise

    def reader(self):
        # USB CDC carries both newline-delimited text and framed binary dump data.
        # readline() is unsafe for binary because arbitrary payload bytes can contain \n.
        buf = bytearray()
        BIN_MAGIC = 0xB0
        while self.running:
            try:
                ser = self.ser
                if not ser or not ser.is_open:
                    break
                chunk = ser.read(1024)
                if not chunk:
                    continue
                buf.extend(chunk)
                while buf:
                    # Binary eMMC frame: B0 | channel | offset(u32 LE) | count(u16 LE) | payload
                    if buf[0] == BIN_MAGIC:
                        if len(buf) < 8:
                            break
                        ch = buf[1]
                        if ch not in (0x04, 0x05):
                            # Unknown binary frame: pass one byte through as raw data to avoid deadlock.
                            raw = bytes([buf.pop(0)])
                            if self.callback:
                                self.callback(raw)
                            continue
                        count = int.from_bytes(buf[6:8], "little")
                        frame_len = 8 + count if ch == 0x04 else 9
                        if ch == 0x05 and len(buf) >= 9:
                            frame_len = 9
                        if len(buf) < frame_len:
                            break
                        frame = bytes(buf[:frame_len])
                        del buf[:frame_len]
                        if self.callback:
                            self.callback(frame)
                        continue

                    nl = buf.find(b"\n")
                    if nl < 0:
                        # Keep a partial text line, but cap pathological growth.
                        if len(buf) > 8192:
                            raw = bytes(buf[:4096])
                            del buf[:4096]
                            if self.callback:
                                self.callback("[RX] " + raw.decode(errors="replace"))
                        break
                    line = bytes(buf[:nl + 1])
                    del buf[:nl + 1]
                    if self.callback:
                        self.callback("[RX] " + line.decode(errors="replace"))
            except (serial.SerialException, OSError) as e:
                self._handle_disconnect(e)
                break
            except Exception as e:
                if self.callback:
                    self.callback(f"[SERIAL ERROR] {e}\n")

    def _handle_disconnect(self, error=None):
        self.running = False
        with self._lock:
            ser = self.ser
            self.ser = None
            self.port = None
        if ser:
            try:
                ser.close()
            except Exception:
                pass
        if self.callback and error:
            self.callback(f"[DISCONNECT] {error}\n")
        if self.disconnect_callback:
            self.disconnect_callback()

    def set_callback(self, func):
        self.callback = func

    def set_disconnect_callback(self, func):
        self.disconnect_callback = func
