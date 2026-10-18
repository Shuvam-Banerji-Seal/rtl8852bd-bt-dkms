# rtl8852bd-bt-dkms

Bluetooth for the Realtek **RTL8852BD** (USB `0bda:b853`, `rom_version=3`), the
Bluetooth half of many RTL8852BE Wi-Fi/Bluetooth combo cards. Mainline Linux has no
firmware patch for this chip cut, so Bluetooth stays dead. This repository provides
a patched `btrtl` module, built by DKMS, that loads the "eco 4" patch Realtek ships
in its Windows driver.

The module is the kernel's own `drivers/bluetooth/btrtl.c` from **v7.2.11**,
unchanged except for the RTL8852BD download path (`upstream-base/` holds the
untouched upstream file, so `diff -u upstream-base/btrtl.c src/btrtl.c` shows the
whole change). It therefore matches the in-tree `btusb` exactly.

## Does this apply to you?

Both must be true:

```sh
lsusb | grep -i 0bda:b853
sudo dmesg | grep -i 'RTL: rom_version'      # must say version=3
```

The symptom without this driver: `dmesg` shows `didn't find patch for chip id 3`
and Bluetooth never comes up.

## Install (Arch Linux)

```sh
git clone https://github.com/Shuvam-Banerji-Seal/rtl8852bd-bt-dkms
cd rtl8852bd-bt-dkms/arch
makepkg -si
```

Install headers for each kernel you boot (`linux-headers`, `linux-zen-headers`,
`linux-lts-headers`). Pacman's DKMS hooks rebuild the module on every kernel
update; nothing else is needed.

### Firmware

The patch is proprietary Realtek code and is **not included**. Download your
laptop's Realtek Bluetooth driver for Windows from the vendor's support site (any
vendor's package that contains `rtl8852bd_mp_chip_new.dat` works), then:

```sh
sudo pacman -S innoextract
sudo rtl8852bd-bt-firmware ~/Downloads/<driver>.exe
sudo modprobe -r btusb btrtl && sudo modprobe btusb
```

### Verify

```sh
sudo dmesg | grep RTL8852BD
# RTL: RTL8852BD: using eco4 patch
# RTL: fw version 0x3c91950e
# RTL: RTL8852BD eco4 patch running (attempt 1)
```

`fw version 0x000b8852` would mean the controller is still on ROM code; the driver
then resets it and retries up to three times before giving up with an error.

### Other distributions

Untested, but it is the same steps the Arch package performs: copy `src/` to
`/usr/src/rtl8852bd-bt-2.0.0/`, replace `@PKGVER@` in its `dkms.conf` with `2.0.0`,
then `sudo dkms install rtl8852bd-bt/2.0.0`. Install the firmware with
`tools/rtl8852bd-bt-firmware` (it expects the extractor at
`/usr/lib/rtl8852bd-bt/extract-firmware.py`).

## Uninstall

```sh
sudo pacman -R rtl8852bd-bt-dkms
```

The in-kernel `btrtl` is used again after the next module reload or reboot.

## How it works

The RTL8852BD needs a patch that no `linux-firmware` container provides. Realtek's
`rtl8852bd_mp_chip_new.dat` (a `BTNIC003` container) holds it as three records,
each with its own RAM load address. `tools/extract-firmware.py` repacks them into
`rtl_bt/rtl8852bd_eco4.bin`:

```
"E4RD" | __le32 count | count × (__le32 load, __le32 len, data[len])
```

For each record, the driver writes the load address into `0x801200cc` (the address
the controller stores `0xfc20` fragments at) with the vendor write-memory command
`0xfc62`, then streams the record in 252-byte `0xfc20` fragments with plain indices.
An empty fragment with bit 7 set commits the patch. The driver then reads the local
version back: the ROM reports `lmp_subver 0x8852` and the running patch does not.

## Bluetooth audio dropouts

If music over Bluetooth has short gaps while Wi-Fi is connected, turn off Wi-Fi
power save. In 60-second A2DP captures, power save on gave stalls of 0.25-1.1 s
in 5 of 6 runs; power save off gave none in 4 runs. The cause is in the Wi-Fi
driver's coexistence logic, not in this module. Details and data:
[`docs/a2dp-analysis.md`](docs/a2dp-analysis.md).

```sh
sudo install -Dm644 -t /etc/NetworkManager/conf.d/ \
	/usr/share/rtl8852bd-bt/90-rtl8852bd-wifi-powersave-off.conf
sudo systemctl reload NetworkManager   # then reconnect Wi-Fi
```

## Upstream

`upstream/0001-Bluetooth-btrtl-Add-support-for-the-RTL8852BD.patch` is the same
change as a patch against mainline (`checkpatch.pl --strict` clean). It is an RFC:
it can only be merged once Realtek publishes the firmware in `linux-firmware`.
Recipients: linux-bluetooth@vger.kernel.org, Marcel Holtmann, Luiz Augusto von
Dentz.

## Credits

The eco 4 download sequence was reverse-engineered by
[mihaits/rtl8852bd-bt-linux](https://github.com/mihaits/rtl8852bd-bt-linux), which
this project builds on. `btrtl.c`/`btrtl.h` are from the Linux kernel (Copyright
2015 Endless Mobile, Inc.).

## License

GPL-2.0-or-later for the kernel sources (as upstream), GPL-2.0 for the scripts. No
Realtek firmware is distributed.
