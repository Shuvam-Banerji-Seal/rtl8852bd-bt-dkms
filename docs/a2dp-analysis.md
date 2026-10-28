# A2DP dropouts on the RTL8852BE combo card

Symptom: short gaps (roughly 0.1 s and longer) in Bluetooth audio while music
plays, with the RTL8852BD Bluetooth patch running and Wi-Fi connected on 2.4 GHz.

**Result:** the gaps come from Wi-Fi power save, not from the Bluetooth driver.
With power save on, every stall of 100 ms or more was observed; with power save
off, none were.

## Setup

- Lenovo laptop, RTL8852BE (Wi-Fi `rtw89_8852be`, fw 0.29.29.18; Bluetooth
  `0bda:b853` running eco4 patch 0x3c91950e), shared antenna (`ant_iso:10`).
- Kernel 7.2.11-arch1-1, PipeWire 1.6.9, WirePlumber 0.5.18, BlueZ 5.87.
- Headphones: EVM EnBar Pro, A2DP, SBC codec, 48 kHz.
- Wi-Fi: 2.4 GHz, channel 3/5 (40 MHz), RSSI about -41 dBm.

## Method

Each run captures 60 s of HCI traffic with `btmon` during continuous playback,
plus snapshots of rtw89's coexistence state
(`/sys/kernel/debug/ieee80211/*/rtw89/btc_info`). `tools/analysis/a2dp_gaps.py`
measures the interval between *Number of Completed Packets* events, i.e. when
the controller reports an A2DP packet as sent over the air. A stall here is a
period in which no audio reaches the headphones.

Two variables were varied in an interleaved matrix (two rounds, so slow drift
hits every condition equally), plus two earlier baseline runs:

- Wi-Fi power save on (default) / off (`iw dev wlp4s0 set power_save off`)
- KDE Connect running / stopped. Its Bluetooth backend restarts BR/EDR
  discovery every 20 s, so the radio spends 55-65 % of the time inquiring.

Scripts: `tools/analysis/capture.sh`, `a2dp_gaps.py`.

## Results

| run | power save | KDE Connect | packets / 60 s | p99 gap | worst gap | gaps ≥ 100 ms |
|---|---|---|---|---|---|---|
| base1 | on | on | 4313 | 57 ms | **801 ms** | 9 |
| base2 | on | on | 4501 | 53 ms | 95 ms | 0 |
| base-r1 | on | on | 4446 | 63 ms | **265 ms** | 5 |
| base-r2 | on | on | 4390 | 62 ms | **619 ms** | 5 |
| nokde-r1 | on | off | 4227 | 62 ms | **1140 ms** | 5 |
| nokde-r2 | on | off | 4389 | 53 ms | **537 ms** | 3 |
| psoff-r1 | off | on | 4505 | 60 ms | 83 ms | 0 |
| psoff-r2 | off | on | 4502 | 63 ms | 100 ms | 0 |
| both-r1 | off | off | 4503 | 55 ms | 93 ms | 0 |
| both-r2 | off | off | 4506 | 57 ms | 85 ms | 0 |

- Power save on: 5 of 6 runs had stalls of 100 ms or more (265-1140 ms worst).
  Power save off: 0 of 4. One-sided Fisher exact test: p ≈ 0.024.
- With power save off, the controller delivered a steady ~4505 packets per
  minute; with it on, up to 6 % fewer, which is the audio that was lost.
- KDE Connect's continuous inquiry did not change the worst-case gaps in either
  power-save setting. It does take airtime, but not enough to underrun the
  audio buffer.

## Why

rtw89's coexistence code (`drivers/net/wireless/realtek/rtw89/coex.c`,
`_run_coex()`) takes the "Wi-Fi off" branch whenever Wi-Fi is in low-power
state:

```c
if (wl->status.map.rf_off || dm->bt_only || wl->status.map.lps) {
	_action_wl_off(rtwdev, mode);
	goto exit;
}
```

In that branch no A2DP-aware TDMA policy is applied (`btc_info` shows
`action:WL_OFF`), yet Wi-Fi still wakes up to transmit and receive on the
shared antenna. The longest Wi-Fi slot recorded was 1275 ms
(`max_t[wl:1275]`), which matches the longest audio stalls. With power save
off, coexistence runs the `BT_A2DP` policy and the stalls disappear.

A side observation: the Bluetooth firmware's status report to Wi-Fi
(`bt_info`) shows `a2dp=0, acl_busy=0` even while streaming. Realtek's vendor
Linux driver reports active profiles to the firmware with vendor command
`0xfc19`; sending that report by hand was accepted (status 0) but did not
change `bt_info` on this firmware, so it is not the fix here.

## Second cause: Bluetooth reported as idle

With power save off, audio was clean while Wi-Fi was quiet, but it still broke
up when Wi-Fi downloaded heavily on 2.4 GHz. `btc_info` showed why: the Bluetooth
firmware's status (`bt_info`) said `connect=1, acl_busy=0, a2dp=0` while
streaming, so rtw89 ran its `BT_IDLE` policy and gave Wi-Fi most of the airtime
(`avg_t[wl:39/bt:10]`).

Realtek's vendor drivers tell the firmware which links carry which profiles with
vendor command `0xfc19`
(`u8 count, count × (le16 handle, u8 profile bits), u8 busy bits`; A2DP is bit 2).
Sending `fc19 01 01 00 04 04` for the A2DP link made the firmware report
`bt_info` `0x49` (connected, ACL busy, A2DP) and rtw89 switched to `BT_A2DP`.
`tools/rtl8852bd-coexd` sends this automatically from BlueZ's transport state.

A/B test, BSNL 2.4 GHz, 60 s per run, 4 parallel downloads saturating Wi-Fi:

| coexd | Wi-Fi | audio packets | worst gap | gaps ≥ 100 ms | coex policy |
|---|---|---|---|---|---|
| on (r1) | 21 Mbit/s | 4503 | 93 ms | 0 | BT_A2DP |
| off (r1) | 41 Mbit/s | 2157 | 156 ms | 27 | BT_IDLE |
| on (r2) | 20 Mbit/s | 3315* | 103 ms | 1 | BT_A2DP |
| off (r2) | 31 Mbit/s | 2146 | 153 ms | 36 | BT_IDLE |

\* the user was seeking in a video during this run, which pauses the stream.

The policy shares airtime fairly, so Wi-Fi throughput roughly halves while music
plays; one shared antenna on one band cannot give both full rate. On 5 GHz the
two do not share the band: 30 Mbit/s of downloads ran alongside full-rate audio
(4500 packets, worst gap 73 ms).

## BLE input devices

The same report covers input devices. Realtek's `rtk_coex.h` defines the
per-link bits (`sco 0, hid 1, a2dp 2, pan 3, hid_interval 4, hogp 5, voice 6,
sink 7`), and `rtk_coex.c` reports every LE link as HID ("for coex, le is the
same as hid"). A connection interval under 60 units (75 ms) adds `hid_interval`
on the link and marks HID busy in the status byte; the `hogp` bit is never set.

With a BLE keyboard (handle `0x0010`, interval 11.25 ms) and idle earbuds
(handle `0x0001`), sending `fc19 02 01 00 04 10 00 12 02` changed `btc_info` from
`profile:None` to `profile:HID`, and `bt_info` from `0x01` to `0x29` (connected,
ACL busy, HID). `rtl8852bd-coexd` now sends this. Checked with Wi-Fi on 5 GHz;
how much it helps input latency under 2.4 GHz load is not measured.

## Fix

Disable Wi-Fi power save, and run `rtl8852bd-coexd`
(`sudo systemctl enable --now rtl8852bd-coexd`). Prefer 5 GHz Wi-Fi where
available.

### Wi-Fi power save

With NetworkManager:

```sh
sudo install -Dm644 extras/90-rtl8852bd-wifi-powersave-off.conf \
	/etc/NetworkManager/conf.d/90-rtl8852bd-wifi-powersave-off.conf
sudo systemctl reload NetworkManager
nmcli connection down <ssid> && nmcli connection up <ssid>   # or reconnect
iw dev wlp4s0 get power_save                                  # Power save: off
```

The cost is somewhat higher Wi-Fi idle power use.

## Limits

- Ten one-minute runs on one laptop, one access point, one headset (SBC). The
  power-save effect is consistent across them, but other codecs, 5 GHz Wi-Fi,
  or heavy Wi-Fi traffic were not tested.
- Stalls are measured at the HCI level (controller completions), not at the
  headphones' DAC; a stall shorter than the headset's jitter buffer may not
  be audible.
