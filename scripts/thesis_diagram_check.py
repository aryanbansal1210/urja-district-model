import re, glob, os
W_REG, W_BOLD, W_MONO = 0.545, 0.590, 0.605
def check(path):
    t = open(path, encoding="utf-8").read()
    mm = re.search(r'viewBox="0 0 (\d+) (\d+)"', t)
    if not mm:
        return 0, 0, 0, ["unreadable: no viewBox"]
    W, H = map(int, mm.groups())
    issues = []
    # text boxes
    tb = []
    for m in re.finditer(r'<text x="([\d.]+)" y="([\d.]+)" font-size="([\d.]+)"[^>]*?>(.*?)</text>', t):
        x, y, fs, body = float(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4)
        tag = m.group(0)
        bold = 'font-weight="600"' in tag; mono = 'Mono' in tag
        a = re.search(r'text-anchor="(\w+)"', tag); a = a.group(1) if a else "start"
        f = W_MONO if mono else (W_BOLD if bold else W_REG)
        w = len(body)*fs*f
        if a=="middle": x -= w/2
        elif a=="end": x -= w
        tb.append((x, y-fs*0.80, w, fs*1.02, body))
        if x < -1 or x+w > W+1 or y-fs > -1 and y+2 > H:
            issues.append(f"TEXT off-canvas: '{body[:34]}' x={x:.0f}..{x+w:.0f} (W={W})")
    for i in range(len(tb)):
        for j in range(i+1, len(tb)):
            a, b = tb[i], tb[j]
            if (min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))>1.5 and (min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))>1.5:
                issues.append(f"TEXT overlap: '{a[4][:24]}' x '{b[4][:24]}'")
    # rects
    for m in re.finditer(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', t):
        x, y, w, h = map(float, m.groups())
        if x < -1 or y < -1 or x+w > W+1 or y+h > H+1:
            issues.append(f"RECT out of canvas: x={x:.0f} y={y:.0f} -> {x+w:.0f},{y+h:.0f} (canvas {W}x{H})")
    # lines
    for m in re.finditer(r'<line x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)"', t):
        x1,y1,x2,y2 = map(float, m.groups())
        for (xx,yy) in ((x1,y1),(x2,y2)):
            if xx < -1 or yy < -1 or xx > W+1 or yy > H+1:
                issues.append(f"LINE endpoint out: ({xx:.0f},{yy:.0f}) canvas {W}x{H}")
    # TEXT vs LINE  (I-beams, connectors, rules) - the class that slipped
    # through v1: a label sitting on a drawn stroke reads as a collision even
    # though no two labels overlap. Dashed strokes are gridlines/leaders and
    # are allowed to pass behind text.
    lines = []
    for m in re.finditer(r'<line x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" '
                         r'y2="([\d.-]+)"[^>]*?/>', t):
        seg = m.group(0)
        if "dasharray" in seg:
            continue
        x1, y1, x2, y2 = map(float, m.groups())
        swm = re.search(r'stroke-width="([\d.]+)"', seg)
        pad = max(1.5, (float(swm.group(1)) if swm else 1.0) / 2 + 0.6)
        lines.append((min(x1, x2) - pad, min(y1, y2) - pad,
                      max(x1, x2) + pad, max(y1, y2) + pad))
    for (bx, by, bw, bh, body) in tb:
        for (lx1, ly1, lx2, ly2) in lines:
            ox = min(bx + bw, lx2) - max(bx, lx1)
            oy = min(by + bh, ly2) - max(by, ly1)
            if ox > 1.0 and oy > 1.0:
                issues.append(f"TEXT-ON-LINE '{body[:30]}' crosses stroke "
                              f"({lx1:.0f},{ly1:.0f})-({lx2:.0f},{ly2:.0f})")
                break
    # PANEL-OVER-CONTENT: in SVG, later elements paint over earlier ones. A
    # large opaque rect that appears AFTER many smaller shapes it overlaps is
    # covering them (the D7 cost trace once landed on the second row of plan
    # grids). A panel drawn BEFORE its content is just a container, which is
    # why draw order, not geometry alone, is the test.
    rects = []
    for m in re.finditer(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" '
                         r'height="([\d.]+)"[^>]*?/>', t):
        seg = m.group(0)
        x, y, w, h = map(float, m.groups())
        opaque = 'opacity=' not in seg or 'opacity="1' in seg
        filled = 'fill="none"' not in seg
        rects.append((m.start(), x, y, w, h, w * h, opaque and filled))
    page = W * H
    for (pos, x, y, w, h, area, solid) in rects:
        if not solid or area < page * 0.02 or area > page * 0.55:
            continue
        covered = sum(
            1 for (p2, x2, y2, w2, h2, a2, _s) in rects
            if p2 < pos and 0 < a2 < area
            and min(x + w, x2 + w2) - max(x, x2) > 1
            and min(y + h, y2 + h2) - max(y, y2) > 1)
        if covered > 40:
            issues.append(f"PANEL-OVER-CONTENT rect at ({x:.0f},{y:.0f}) "
                          f"{w:.0f}x{h:.0f} paints over {covered} earlier shapes")
    # circles
    for m in re.finditer(r'<circle cx="([\d.-]+)" cy="([\d.-]+)" r="([\d.]+)"', t):
        cx, cy, r = map(float, m.groups())
        if cx-r < -1 or cy-r < -1 or cx+r > W+1 or cy+r > H+1:
            issues.append(f"CIRCLE out: ({cx:.0f},{cy:.0f}) r={r}")
    return W, H, len(tb), issues
tot = 0
for p in sorted(glob.glob("outputs/figures/D*.svg")):
    W,H,n,iss = check(p)
    tot += len(iss)
    print(f"{os.path.basename(p):<32} {W}x{H} {n:>3} labels  {'OK' if not iss else str(len(iss))+' ISSUES'}")
    for s in dict.fromkeys(iss): print("     ", s)
print("\nTOTAL:", tot)
