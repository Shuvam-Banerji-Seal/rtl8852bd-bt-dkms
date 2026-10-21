#!/usr/bin/env python3
"""Send one raw HCI command and print its Command Complete/Status event.

usage: hcicmd.py <hex opcode> [hex param bytes...]   (needs CAP_NET_RAW)
The adapter index comes from $HCI_DEV (default 0).
"""
import os
import select
import socket
import struct
import sys

SOL_HCI, HCI_FILTER = 0, 2
EVT_CMD_COMPLETE, EVT_CMD_STATUS = 0x0e, 0x0f

opcode = int(sys.argv[1], 16)
params = bytes(int(b, 16) for b in sys.argv[2:])

s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
s.bind((int(os.environ.get("HCI_DEV", "0")),))
# filter: event packets only, Command Complete + Command Status, any opcode
type_mask = 1 << 4
event_mask = (1 << EVT_CMD_COMPLETE) | (1 << EVT_CMD_STATUS)
s.setsockopt(SOL_HCI, HCI_FILTER,
             struct.pack('<IIIH', type_mask, event_mask, 0, 0) + b'\0\0')
s.send(struct.pack('<BHB', 1, opcode, len(params)) + params)

while True:
    r, _, _ = select.select([s], [], [], 2.0)
    if not r:
        sys.exit('timeout waiting for reply')
    pkt = s.recv(260)
    evt = pkt[1]
    if evt == EVT_CMD_COMPLETE and struct.unpack_from('<H', pkt, 4)[0] == opcode:
        print(f'complete opcode=0x{opcode:04x} return={pkt[6:].hex(" ")}')
        break
    if evt == EVT_CMD_STATUS and struct.unpack_from('<H', pkt, 5)[0] == opcode:
        print(f'status opcode=0x{opcode:04x} status=0x{pkt[3]:02x}')
        break
