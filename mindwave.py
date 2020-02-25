import select, serial, threading

# Byte codes
CONNECT              = b'\xc0'
DISCONNECT           = b'\xc1'
AUTOCONNECT          = b'\xc2'
SYNC                 = b'\xaa'
EXCODE               = b'\x55'
POOR_SIGNAL          = b'\x02'
ATTENTION            = b'\x04'
MEDITATION           = b'\x05'
BLINK                = b'\x16'
HEADSET_CONNECTED    = b'\xd0'
HEADSET_NOT_FOUND    = b'\xd1'
HEADSET_DISCONNECTED = b'\xd2'
REQUEST_DENIED       = b'\xd3'
STANDBY_SCAN         = b'\xd4'
RAW_VALUE            = b'\x80'

# Status codes
STATUS_CONNECTED     = 'connected'
STATUS_SCANNING      = 'scanning'
STATUS_STANDBY       = 'standby'

class Headset(object):
    """
    A MindWave Headset
    """

    class DongleListener(threading.Thread):
        """
        Serial listener for dongle device.
        """
        def __init__(self, headset, *args, **kwargs):
            """Set up the listener device."""
            self.headset = headset
            super(Headset.DongleListener, self).__init__(*args, **kwargs)

        def run(self):
            """Run the listener thread."""
            s = self.headset.dongle

            # Re-apply settings to ensure packet stream
            s.write(DISCONNECT)
            d = s.getSettingsDict()
            for i in range(2):
                d['rtscts'] = not d['rtscts']
                s.applySettingsDict(d)

            while True:
                # Begin listening for packets
                try:
                    if s.read () == SYNC and s.read () == SYNC:
                        # Packet found, determine plength
                        while True:
                            plength = int.from_bytes(s.read(), "big")
                            if plength != 170:
                                break
                        if plength > 170:
                            continue

                        # Read in the payload
                        payload = s.read(plength)

                        # Verify its checksum
                        val = sum(b for b in payload[:-1])
                        val &= 0xff
                        val = ~val & 0xff
                        chksum = s.read()

                        #if val == chksum:
                        if True: # ignore bad checksums
                            self.parse_payload(payload)
                except (select.error, OSError):
                    break
                except serial.SerialException:
                    s.close()
                    break

        def parse_payload(self, payload):
            """Parse the payload to determine an action."""
            while payload:
                # Parse data row
                excode = 0
                try:
                    code, payload = bytes([payload[0]]), payload[1:]
                except IndexError:
                    pass
                while code == EXCODE:
                    # Count excode bytes
                    excode += 1
                    try:
                        code, payload = bytes([payload[0]]), payload[1:]
                    except IndexError:
                        pass
                if int.from_bytes(code, "big") < 0x80:
                    # This is a single-byte code
                    try:
                        value, payload = payload[0], payload[1:]
                    except IndexError:
                        pass
                    if code == POOR_SIGNAL:
                        # Poor signal
                        old_poor_signal = self.headset.poor_signal
                        self.headset.poor_signal = value
                        if self.headset.poor_signal > 0:
                            if old_poor_signal == 0:
                                if self.headset.handlers ['poor_signal'] is not None:
                                    self.headset.handlers ['poor_signal'] (self.headset, self.headset.poor_signal)
                        else:
                            if old_poor_signal > 0:
                                if self.headset.handlers ['good_signal'] is not None:
                                    self.headset.handlers ['good_signal'] (self.headset, self.headset.poor_signal)
                    elif code == ATTENTION:
                        # Attention level
                        self.headset.attention = value
                        if self.headset.handlers ['attention'] is not None:
                            self.headset.handlers ['attention'] (self.headset, self.headset.attention)
                    elif code == MEDITATION:
                        # Meditation level
                        self.headset.meditation = value
                        if self.headset.handlers ['meditation'] is not None:
                            self.headset.handlers ['meditation'] (self.headset, self.headset.meditation)
                    elif code == BLINK:
                        # Blink strength
                        self.headset.blink = value
                        if self.headset.handlers ['blink'] is not None:
                            self.headset.handlers ['blink'] (self.headset, self.headset.blink)
                else:
                    # This is a multi-byte code
                    try:
                        vlength, payload = payload[0], payload[1:]
                    except IndexError:
                        continue
                    value, payload = payload[:vlength], payload[vlength:]

                    # Multi-byte EEG and Raw Wave codes not included
                    # Raw Value added due to Mindset Communications Protocol

                    # FIX: accessing value crashes elseway
                    if code == RAW_VALUE and len(value) >= 2:
                        raw=value[0]*256+value[1]
                        if (raw>=32768):
                            raw=raw-65536
                        self.headset.raw_value = raw
                        if self.headset.handlers ['raw_value'] is not None:
                            self.headset.handlers ['raw_value'] (self.headset, self.headset.raw_value)
                    if code == HEADSET_CONNECTED:
                        # Headset connect success
                        run_handlers = self.headset.status != STATUS_CONNECTED
                        self.headset.status = STATUS_CONNECTED
                        self.headset.headset_id = value.hex()
                        if run_handlers:
                            if self.headset.handlers ['headset_connected'] is not None:
                                self.headset.handlers ['headset_connected'] (self.headset)
                    elif code == HEADSET_NOT_FOUND:
                        # Headset not found
                        if self.headset.handlers ['headset_notfound'] is not None:
                            self.headset.handlers ['headset_notfound'] (self.headset, value.hex () if vlength > 0 else None)
                    elif code == HEADSET_DISCONNECTED:
                        # Headset disconnected
                        headset_id = value.hex()
                        if self.headset.handlers ['headset_disconnected'] is not None:
                            self.headset.handlers ['headset_disconnected'] (self.headset, headset_id)
                    elif code == REQUEST_DENIED:
                        # Request denied
                        if self.headset.handlers ['request_denied'] is not None:
                            self.headset.handlers ['request_denied'] (self.headset)
                    elif code == STANDBY_SCAN:
                        # Standby/Scan mode
                        try:
                            byte = value[0]
                        except IndexError:
                            byte = None
                        if byte:
                            run_handlers = (self.headset.status !=
                                            STATUS_SCANNING)
                            self.headset.status = STATUS_SCANNING
                            if run_handlers:
                                if self.headset.handlers ['scanning'] is not None:
                                    self.headset.handlers ['scanning'] (self.headset)
                        else:
                            run_handlers = (self.headset.status !=
                                            STATUS_STANDBY)
                            self.headset.status = STATUS_STANDBY
                            if run_handlers:
                                if self.headset.handlers ['standby'] is not None:
                                    self.headset.handlers ['standby'] (self.headset)


    def __init__(self, device, headset_id=None, open_serial=True):
        """Initialize the  headset."""
        # Initialize headset values
        self.dongle = None
        self.listener = None
        self.device = device
        self.headset_id = headset_id
        self.poor_signal = 255
        self.attention = 0
        self.meditation = 0
        self.blink = 0
        self.raw_value = 0
        self.status = None

        # Create event handler lists
        self.handlers = dict ()
        self.handlers ['poor_signal'] = None
        self.handlers ['good_signal'] = None
        self.handlers ['attention']   = None
        self.handlers ['meditation']  = None
        self.handlers ['blink']       = None
        self.handlers ['raw_value']   = None
        self.handlers ['headset_connected']    = None
        self.handlers ['headset_notfound']     = None
        self.handlers ['headset_disconnected'] = None
        self.handlers ['request_denied']       = None
        self.handlers ['scanning']             = None
        self.handlers ['standby']              = None

        # Open the socket
        if open_serial:
            self.serial_open()

    def set_callback (self, event_name, func):
        self.handlers [event_name] = func

    def connect(self, headset_id=None):
        """Connect to the specified headset id."""
        if headset_id:
            self.headset_id = headset_id
        else:
            headset_id = self.headset_id
            if not headset_id:
                self.autoconnect()
                return
        self.dongle.write((CONNECT + bytes.fromhex(headset_id)))

    def autoconnect(self):
        """Automatically connect device to headset."""
        self.dongle.write(AUTOCONNECT)

    def disconnect(self):
        """Disconnect the device from the headset."""
        self.dongle.write(DISCONNECT)

    def serial_open(self):
        """Open the serial connection and begin listening for data."""
        # Establish serial connection to the dongle
        if not self.dongle or not self.dongle.isOpen():
            self.dongle = serial.Serial(self.device, 115200)

        # Begin listening to the serial device
        if not self.listener or not self.listener.isAlive():
            self.listener = self.DongleListener(self)
            self.listener.daemon = True
            self.listener.start()

    def serial_close(self):
        """Close the serial connection."""
        self.dongle.close()
