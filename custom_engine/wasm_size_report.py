#!/usr/bin/env python3
"""Size report for a Godot web template built with debug_symbols=yes.
Reads the wasm 'name' section (function names) + the code section (function sizes), demangles the names and prints
how many bytes every engine part takes. Output is a small text file (a few hundred KB) instead of the 100 MB wasm."""
import sys, subprocess, re, collections

def leb(d, i):
    r = 0; s = 0
    while True:
        b = d[i]; i += 1; r |= (b & 0x7f) << s; s += 7
        if not b & 0x80:
            return r, i

def main(path, out):
    d = open(path, 'rb').read()
    i = 8; sec = {}; custom = {}
    while i < len(d):
        sid = d[i]; i += 1; sz, i = leb(d, i)
        if sid == 0:
            l, j = leb(d, i); nm = d[j:j + l].decode('utf8', 'ignore'); custom[nm] = (j + l, sz - (j + l - i))
        else:
            sec[sid] = (i, sz)
        i += sz
    # imports (to offset function indexes)
    p, _ = sec[2]; n, j = leb(d, p); nimp = 0
    for _ in range(n):
        l, j = leb(d, j); j += l; l, j = leb(d, j); j += l; k = d[j]; j += 1
        if k == 0: _, j = leb(d, j); nimp += 1
        elif k == 1:
            j += 1; f, j = leb(d, j); _, j = leb(d, j)
            if f & 1: _, j = leb(d, j)
        elif k == 2:
            f, j = leb(d, j); _, j = leb(d, j)
            if f & 1: _, j = leb(d, j)
        elif k == 3: j += 2
    p, _ = sec[10]; n, j = leb(d, p); sizes = []
    for _ in range(n):
        l, j = leb(d, j); sizes.append(l); j += l
    names = {}
    if 'name' in custom:
        p, ln = custom['name']; end = p + ln; j = p
        while j < end:
            sub = d[j]; j += 1; sl, j = leb(d, j); nxt = j + sl
            if sub == 1:
                cnt, k = leb(d, j)
                for _ in range(cnt):
                    idx, k = leb(d, k); l, k = leb(d, k); names[idx] = d[k:k + l].decode('utf8', 'ignore'); k += l
            j = nxt
    lines = []
    w = lines.append
    w('file %s  total %.2f MB' % (path, len(d) / 1e6))
    w('sections (MB): ' + ', '.join('%s=%.2f' % (k, v[1] / 1e6) for k, v in sorted(sec.items())))
    w('functions: %d (imports %d), with names: %d' % (len(sizes), nimp, len(names)))
    if not names:
        w('NO NAME SECTION FOUND - the build was not made with debug_symbols=yes'); open(out, 'w').write('\n'.join(lines)); return
    order = [(nimp + k, sizes[k]) for k in range(len(sizes))]
    mang = [names.get(idx, '') for idx, _ in order]
    # demangle in one go
    try:
        dem = subprocess.run(['c++filt'], input='\n'.join(mang), capture_output=True, text=True).stdout.split('\n')
    except Exception:
        dem = mang
    if len(dem) < len(mang): dem += [''] * (len(mang) - len(dem))
    def key(name):
        if not name: return '(unnamed)'
        n = re.sub(r'\([^()]*\)\s*(const)?$', '', name)        # drop argument list
        n = re.sub(r'<[^<>]*>', '', n)                         # drop template arguments (twice for nesting)
        n = re.sub(r'<[^<>]*>', '', n)
        n = n.replace('(anonymous namespace)::', '')
        parts = n.split('::')
        if len(parts) >= 2:
            if parts[0] in ('std', '__2', 'std::__2'): return 'std (libc++)'
            return parts[0] if parts[0] not in ('JPH',) else 'JPH (Jolt)'
        m = re.match(r'([A-Za-z_]+)', n)
        return ('C:' + m.group(1)[:24]) if m else '(other)'
    agg = collections.Counter(); cnt = collections.Counter()
    for (idx, sz), nm in zip(order, dem):
        k = key(nm); agg[k] += sz; cnt[k] += 1
    total = sum(sizes)
    w('')
    w('=== bytes of code per class / library (top 400) ===')
    for k, v in agg.most_common(400):
        w('%9.1f KB  %5.2f%%  %5d fn  %s' % (v / 1024, 100.0 * v / total, cnt[k], k))
    w('')
    w('=== 120 biggest single functions ===')
    big = sorted(zip(order, dem), key=lambda t: -t[0][1])[:120]
    for (idx, sz), nm in big:
        w('%8.1f KB  %s' % (sz / 1024, nm[:150]))
    open(out, 'w').write('\n'.join(lines))
    print('report written:', out, len(lines), 'lines')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'size-report.txt')
