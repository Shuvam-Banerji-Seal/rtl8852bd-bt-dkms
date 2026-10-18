#!/bin/bash
# capture.sh <outdir> <seconds> : HCI trace + coex snapshot + PipeWire errors
# run as root
set -u
out=$1 secs=${2:-60}
mkdir -p "$out"
btc=$(echo /sys/kernel/debug/ieee80211/*/rtw89/btc_info)
cat "$btc" > "$out/btc_before.txt"
iw dev wlp4s0 get power_save > "$out/wifi_ps.txt" 2>&1
timeout "$secs" btmon -w "$out/a2dp.snoop" >/dev/null 2>&1 &
mid=$((secs / 2))
sleep "$mid"; cat "$btc" > "$out/btc_mid.txt"
sleep $((secs - mid)); wait
cat "$btc" > "$out/btc_after.txt"
chown -R "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$out"
