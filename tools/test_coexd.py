#!/usr/bin/python3 -I
"""Unit tests for rtl8852bd-coexd (no hardware needed)."""
import importlib.machinery
import importlib.util
import os
import unittest

here = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader(
    "coexd", os.path.join(here, "rtl8852bd-coexd"))
spec = importlib.util.spec_from_loader("coexd", loader)
coexd = importlib.util.module_from_spec(spec)
loader.exec_module(coexd)


class Report(unittest.TestCase):
    def test_no_links_clears(self):
        self.assertEqual(coexd.build_report({}), bytes([0, 0]))

    def test_one_busy_link(self):
        # matches the command verified by hand: fc19 01 01 00 04 04
        self.assertEqual(coexd.build_report({1: True}),
                         bytes([1, 0x01, 0x00, 0x04, 0x04]))

    def test_one_idle_link(self):
        self.assertEqual(coexd.build_report({1: False}),
                         bytes([1, 0x01, 0x00, 0x04, 0x00]))

    def test_two_links_sorted_any_busy(self):
        self.assertEqual(coexd.build_report({0x0102: False, 3: True}),
                         bytes([2, 3, 0, 4, 0x02, 0x01, 4, 4]))


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


if __name__ == "__main__":
    unittest.main()
