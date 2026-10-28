#!/usr/bin/python3 -I
"""Unit tests for rtl8852bd-coexd (no hardware needed)."""
import importlib.machinery
import importlib.util
import os
import struct
import unittest

here = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader(
    "coexd", os.path.join(here, "rtl8852bd-coexd"))
spec = importlib.util.spec_from_loader("coexd", loader)
coexd = importlib.util.module_from_spec(spec)
loader.exec_module(coexd)

A2DP, HID, HID_INT = (coexd.PROFILE_A2DP, coexd.PROFILE_HID,
                      coexd.PROFILE_HID_INTERVAL)
EARBUDS, KEYBOARD = "CC:82:8C:5B:0E:53", "C0:7D:AC:D0:B1:6B"


class Report(unittest.TestCase):
    def test_no_links_clears(self):
        self.assertEqual(coexd.build_report({}, 0), bytes([0, 0]))

    def test_one_busy_link(self):
        # matches the command verified by hand: fc19 01 01 00 04 04
        self.assertEqual(coexd.build_report({1: A2DP}, A2DP),
                         bytes([1, 0x01, 0x00, 0x04, 0x04]))

    def test_one_idle_link(self):
        self.assertEqual(coexd.build_report({1: A2DP}, 0),
                         bytes([1, 0x01, 0x00, 0x04, 0x00]))

    def test_two_links_sorted(self):
        self.assertEqual(coexd.build_report({0x0102: A2DP, 3: A2DP}, A2DP),
                         bytes([2, 3, 0, 4, 0x02, 0x01, 4, 4]))

    def test_a2dp_and_le_hid(self):
        # matches the command verified by hand: fc19 02 01 00 04 10 00 12 02
        self.assertEqual(
            coexd.build_report({1: A2DP, 0x10: HID | HID_INT}, HID),
            bytes.fromhex("0201000410001202"))


def event(code, params):
    return bytes([coexd.HCI_EVENT_PKT, code, len(params)]) + params


ADDR = bytes(6)


class LinkEvents(unittest.TestCase):
    def test_le_connection_complete(self):
        params = (bytes([0x01, 0x00]) + struct.pack("<H", 0x0010) +
                  bytes([0x00, 0x01]) + ADDR + struct.pack("<HHH", 6, 0, 400) +
                  bytes([0]))
        self.assertEqual(coexd.parse_link_event(event(0x3e, params)),
                         ("le", 0x10, 6))

    def test_enhanced_connection_complete_v1_and_v2(self):
        body = (struct.pack("<H", 0x2010) + bytes([0x00, 0x01]) + ADDR * 3 +
                struct.pack("<HHH", 24, 0, 400) + bytes([0]))
        for sub, tail in ((0x0a, b""), (0x29, b"\xff\xff\xff")):
            params = bytes([sub, 0x00]) + body + tail
            # the flags in the top 4 bits of the handle are dropped
            self.assertEqual(coexd.parse_link_event(event(0x3e, params)),
                             ("le", 0x10, 24))

    def test_connection_update_complete(self):
        params = bytes([0x03, 0x00]) + struct.pack("<HHHH", 0x10, 80, 0, 400)
        self.assertEqual(coexd.parse_link_event(event(0x3e, params)),
                         ("le", 0x10, 80))

    def test_disconnection_complete(self):
        params = bytes([0x00]) + struct.pack("<H", 0x10) + bytes([0x13])
        self.assertEqual(coexd.parse_link_event(event(0x05, params)),
                         ("gone", 0x10, None))

    def test_ignores_failures_other_events_and_short_packets(self):
        failed = bytes([0x01, 0x3e]) + bytes(20)          # status 0x3e
        for pkt in (event(0x3e, failed),
                    event(0x05, bytes([0x0c, 0x10, 0x00, 0x13])),
                    event(0x3e, bytes([0x02, 0x00, 0x00])),   # adv report
                    event(0x0e, bytes(4)),
                    event(0x3e, bytes([0x01, 0x00, 0x10])),   # truncated
                    bytes([0x02, 0x00, 0x00]), b""):
            self.assertIsNone(coexd.parse_link_event(pkt), pkt.hex())


def mgmt(event, index, opcode, status, data=b""):
    return (struct.pack("<HHH", event, index, 3 + len(data)) +
            struct.pack("<HB", opcode, status) + data)


class MgmtReplies(unittest.TestCase):
    def test_command_complete(self):
        pkt = mgmt(coexd.MGMT_EV_CMD_COMPLETE, 0, coexd.MGMT_OP_HCI_CMD_SYNC,
                   0, b"\x00")
        self.assertEqual(coexd.parse_mgmt_reply(pkt, 0), (0, b"\x00"))

    def test_command_status(self):
        pkt = mgmt(coexd.MGMT_EV_CMD_STATUS, 0, coexd.MGMT_OP_HCI_CMD_SYNC,
                   coexd.MGMT_STATUS_UNKNOWN_COMMAND)
        self.assertEqual(coexd.parse_mgmt_reply(pkt, 0),
                         (coexd.MGMT_STATUS_UNKNOWN_COMMAND, b""))

    def test_ignores_other_commands_indexes_and_events(self):
        op = coexd.MGMT_OP_HCI_CMD_SYNC
        for pkt in (mgmt(coexd.MGMT_EV_CMD_COMPLETE, 0, 0x0004, 0),
                    mgmt(coexd.MGMT_EV_CMD_COMPLETE, 1, op, 0, b"\x00"),
                    mgmt(0x0012, 0, op, 0),           # an unrelated event
                    b"\x01\x00"):
            self.assertIsNone(coexd.parse_mgmt_reply(pkt, 0), pkt.hex())


class Paths(unittest.TestCase):
    def test_transport_path(self):
        self.assertEqual(
            coexd.parse_transport_path(
                "/org/bluez/hci1/dev_C7_0E_57_83_5F_8C/sep1/fd0"),
            (1, "C7:0E:57:83:5F:8C"))

    def test_rejects_other_paths(self):
        for p in ("/org/bluez/hci0", "/org/bluez/hciX/dev_AA/fd0",
                  "/foo/bar/hci0/dev_AA"):
            self.assertIsNone(coexd.parse_transport_path(p))

    def test_adapter_path(self):
        self.assertEqual(coexd.parse_adapter_path("/org/bluez/hci2"), 2)
        for p in ("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF", "/org/bluez",
                  "/org/bluez/hciX"):
            self.assertIsNone(coexd.parse_adapter_path(p))


class Sync(unittest.TestCase):
    """The report sync() builds from transports, connections and intervals."""

    def setUp(self):
        self.sent = []
        self.conns = [(1, EARBUDS, coexd.ACL_LINK),
                      (0x10, KEYBOARD, coexd.LE_LINK)]
        self.hid_devices = {KEYBOARD}
        saved = (coexd.conn_list, coexd.send_report, coexd.log)
        self.addCleanup(self.restore, saved)
        coexd.conn_list = lambda index: self.conns
        coexd.send_report = lambda index, report: (
            self.sent.append(report) or (0, "status 0x00"))
        coexd.log = lambda msg: None
        self.coex = coexd.Coex(bus=None, glib=None)
        self.coex.offers_hid = lambda index, address: \
            address in self.hid_devices

    @staticmethod
    def restore(saved):
        coexd.conn_list, coexd.send_report, coexd.log = saved

    def add_transport(self, busy):
        self.coex.transports["/org/bluez/hci0/dev_CC_82_8C_5B_0E_53/sep1/fd0"] \
            = {"index": 0, "address": EARBUDS, "busy": busy}

    def test_idle_earbuds_and_keyboard_of_unknown_interval(self):
        self.add_transport(busy=False)
        self.coex.sync(0)
        self.assertEqual(self.sent, [bytes.fromhex("0201000410001202")])

    def test_streaming_earbuds(self):
        self.add_transport(busy=True)
        self.coex.sync(0)
        self.assertEqual(self.sent, [bytes.fromhex("0201000410001206")])

    def test_slow_le_link_is_hid_but_not_busy(self):
        self.coex.intervals[(0, 0x10)] = coexd.SHORT_INTERVAL
        self.coex.sync(0)
        self.assertEqual(self.sent, [bytes.fromhex("011000" "02" "00")])

    def test_known_fast_interval_wins_over_missing_hid_service(self):
        self.hid_devices.clear()
        self.coex.intervals[(0, 0x10)] = 6           # 7.5 ms
        self.coex.sync(0)
        self.assertEqual(self.sent, [bytes.fromhex("011000" "12" "02")])

    def test_non_hid_le_link_of_unknown_interval_is_idle(self):
        self.hid_devices.clear()
        self.coex.sync(0)
        self.assertEqual(self.sent, [bytes.fromhex("011000" "02" "00")])

    def test_transport_without_acl_link_is_dropped(self):
        self.conns = []
        self.add_transport(busy=True)
        self.coex.sync(0)
        self.assertEqual(self.sent, [bytes([0, 0])])

    def test_unchanged_report_is_not_resent_unless_forced(self):
        self.coex.sync(0)
        self.coex.sync(0)
        self.assertEqual(len(self.sent), 1)
        self.coex.reassert()                         # HID busy -> resend
        self.assertEqual(len(self.sent), 2)

    def test_idle_report_is_not_reasserted(self):
        self.conns = []
        self.coex.sync(0)
        self.coex.reassert()
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
