#!/usr/bin/env python3
"""Find A2DP stalls in a decoded btmon trace (btmon -r file | this).

Reports gaps between ACL TX packets, gaps between Number of Completed Packets
events, per-packet completion latency, and which radio activities (inquiry,
paging) overlap each stall.
"""
import re
import statistics
import sys

GAP_MS = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
hdr = re.compile(r'^([<>]) (.*?)\s+#\d+ \[hci0\] (?:[\d-]+ )?([\d:.]+)$')


def secs(t):
    parts = [float(x) for x in t.split(':')]
    v = 0.0
    for p in parts:
        v = v * 60 + p
    return v


tx, ncp, events = [], [], []
for line in sys.stdin:
    m = hdr.match(line.rstrip())
    if not m:
        continue
    d, what, t = m.group(1), m.group(2), secs(m.group(3))
    if d == '<' and what.startswith('ACL'):
        tx.append(t)
    elif 'Number of Completed Packets' in what:
        ncp.append(t)
    elif 'Inquiry' in what or 'Create Connection' in what or \
            'Connect Complete' in what:
        events.append((t, what.split('(')[0].strip()))

if not tx:
    sys.exit('no ACL TX packets found')

t0 = tx[0]


def gaps(ts):
    return [(a, b - a) for a, b in zip(ts, ts[1:])]


def describe(name, ts):
    g = [x[1] * 1000 for x in gaps(ts)]
    q = statistics.quantiles(g, n=100)
    print(f'{name}: n={len(ts)} median={statistics.median(g):.1f}ms '
          f'p99={q[98]:.1f}ms max={max(g):.1f}ms')


print(f'trace span {tx[-1] - t0:.1f}s')
describe('ACL TX interval', tx)
describe('Completed-packets interval', ncp)

# completion latency: pair each TX with the next unconsumed completion
lat, j = [], 0
for t in tx:
    while j < len(ncp) and ncp[j] < t:
        j += 1
    if j < len(ncp):
        lat.append((ncp[j] - t) * 1000)
        j += 1
if lat:
    q = statistics.quantiles(lat, n=100)
    print(f'TX->completion latency: median={statistics.median(lat):.1f}ms '
          f'p99={q[98]:.1f}ms max={max(lat):.1f}ms')

print('\nstalls >= 100ms in completions (air side):')
for start, g in gaps(ncp):
    if g * 1000 < 100:
        continue
    near = [f'{w}@{e - t0:.2f}s' for e, w in events
            if start - 5.2 <= e <= start + g]
    print(f'  t={start - t0:7.2f}s gap={g * 1000:6.1f}ms  '
          f'overlapping: {", ".join(near) or "-"}')

# exact inquiry / paging windows: command -> its completion (or cancel)
windows, start, kind = [], None, None
for e, w in events:
    if w.endswith('Command: Inquiry') or w.endswith('Command: Create Connection'):
        if start is None:
            start, kind = e, w.split(': ')[1]
    elif start is not None and ('Inquiry Complete' in w or 'Inquiry Cancel' in w
                                or 'Connect Complete' in w):
        windows.append((start, e, kind))
        start = None
if start is not None:
    windows.append((start, ncp[-1], kind))


def busy(t):
    return any(a <= t <= b for a, b, _ in windows)


inside = [g * 1000 for st, g in gaps(ncp) if busy(st)]
outside = [g * 1000 for st, g in gaps(ncp) if not busy(st)]
busy_s = sum(b - a for a, b, _ in windows)
print(f'\ninquiry/page active {busy_s:.1f}s of {ncp[-1] - ncp[0]:.1f}s')
for name, g in (('during inquiry/page', inside), ('idle radio', outside)):
    if len(g) < 2:
        print(f'  {name}: n={len(g)}')
        continue
    big = [x for x in g if x >= 100]
    print(f'  {name}: n={len(g)} stalls>={GAP_MS:.0f}ms={sum(x >= GAP_MS for x in g)} '
          f'stalls>=100ms={len(big)} worst={max(g):.0f}ms')

print('\nradio activity:')
for e, w in events:
    print(f'  t={e - t0:7.2f}s {w}')
