#!/usr/bin/env python3
"""
Build rtl8852bd_eco4.bin from Realtek's rtl8852bd_mp_chip_new.dat.

The .dat is Realtek's proprietary "BTNIC003" container shipped inside the Windows
driver. This script repacks its firmware records into the small container that the
patched btrtl module reads. No firmware is redistributed -- you supply the .dat.

Usage:
    ./extract-firmware.py rtl8852bd_mp_chip_new.dat -o rtl8852bd_eco4.bin
"""
import argparse, hashlib, struct, sys

BTNIC_MAGIC = b"BTNIC003"
OUT_MAGIC   = b"E4RD"
HDR_LEN     = 0x29          # record header; blob starts immediately after
LOAD_MIN, LOAD_MAX = 0x80100000, 0x80ffffff

def _u32(d, off):
    return struct.unpack_from("<I", d, off)[0]

def _header_at(d, p):
    """Return (load, blob_len, index) if a valid record header sits at p, else None."""
    if p + HDR_LEN > len(d):
        return None
    load  = _u32(d, p + 0x08)
    field = _u32(d, p + 0x20)
    blob_len, index = field >> 8, field & 0xff
    if not (LOAD_MIN <= load <= LOAD_MAX):
        return None
    if blob_len == 0 or p + HDR_LEN + blob_len > len(d):
        return None
    return load, blob_len, index

def parse_dat(d):
    """Yield (index, load, blob) per record, in file order.

    Records are separated by a small trailer plus zero padding, so rather than
    assume a fixed layout we scan forward for the next structurally valid header.
    """
    if not d.startswith(BTNIC_MAGIC):
        sys.exit("error: not a BTNIC003 container (bad magic) -- wrong .dat file?")

    records, p = [], 0x200      # container header area is padded to 0x200
    while p < len(d):
        hdr = _header_at(d, p)
        if hdr is None:
            p += 1
            continue
        load, blob_len, index = hdr
        start = p + HDR_LEN
        records.append((index, load, d[start:start + blob_len]))
        p = start + blob_len
    return records

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dat", help="path to rtl8852bd_mp_chip_new.dat")
    ap.add_argument("-o", "--output", default="rtl8852bd_eco4.bin")
    args = ap.parse_args()

    try:
        with open(args.dat, "rb") as f:
            data = f.read()
    except OSError as e:
        sys.exit(f"error: cannot read {args.dat}: {e}")

    recs = parse_dat(data)
    if not recs:
        sys.exit("error: no firmware records found in the .dat")
    # the BTNIC003 header appears to carry the record count at 0x14; only warn,
    # since that field's meaning comes from observation, not documentation
    hdr_count = _u32(data, 0x14)
    if hdr_count != len(recs):
        print(f"warning: header says {hdr_count} records, found {len(recs)}",
              file=sys.stderr)

    out = bytearray(OUT_MAGIC + struct.pack("<I", len(recs)))
    for index, load, blob in recs:
        print(f"  record {index}: load=0x{load:08x} len={len(blob)}")
        out += struct.pack("<II", load, len(blob)) + blob

    try:
        with open(args.output, "wb") as f:
            f.write(out)
    except OSError as e:
        sys.exit(f"error: cannot write {args.output}: {e}")
    print(f"wrote {args.output}: {len(recs)} records, {len(out)} bytes, "
          f"sha256 {hashlib.sha256(out).hexdigest()}")

if __name__ == "__main__":
    main()
