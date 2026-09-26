"""Generate src/station/station-remap.css from src/styles.css.

The original stylesheet was written for a dark background: translucent black/white fills and pale
text. For the Trail Station theme every such declaration is re-emitted under `body.station` with
the station colour tokens, so old pages become readable without touching their markup. Rules that
belong to other plugin themes (body[data-theme=...]) and animation keyframes are skipped.
Run: python tools/station/gen_remap.py
"""
import colorsys, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'src' / 'styles.css'
OUT = ROOT / 'src' / 'station' / 'station-remap.css'

# Selectors whose look is deliberately dark or drawn over imagery; leave them alone.
SKIP_SEL = re.compile(r'data-theme|leaflet|::?(before|after)|(^|[\s.#>+~,(:])(map-mode-dock|map-fallback|elevation-chip|mappi3-elevation-badge|weather-animation|herbie|sense-led|led-grid|led-cell|pixel|globe|codepen|amcharts|bottom-nav|liquid-nav|nav-orb|hamburger|app-nav-header|brand-mark|splash|launcher|password-strength|sky-view|sky-overlay|sky-reticle|star-|constellation|arcade|game-|snake|pacman)', re.I)

def parse_color(v):
    v = v.strip().lower()
    m = re.fullmatch(r'#([0-9a-f]{3}|[0-9a-f]{6})', v)
    if m:
        h = m.group(1)
        if len(h) == 3: h = ''.join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    m = re.fullmatch(r'rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)', v)
    if m:
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4) or 1))
    if v in ('#fff', 'white'): return (255, 255, 255, 1.0)
    return None

def lum(c):
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255

def text_token(c):
    r, g, b, _ = c
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if s > 0.45 and l < 0.93:
        deg = h * 360
        if deg < 20 or deg >= 340: return 'var(--st-bad)'
        if deg < 65: return 'var(--st-warn)'
        if deg < 160: return 'var(--st-good)'
        if deg < 250: return 'var(--st-water)'
        return '#8a3f86'
    return 'var(--st-ink)' if lum(c) > 0.86 else 'var(--st-muted)'

def remap_decl(prop, value):
    prop = prop.strip().lower()
    important = '!important' in value
    val = value.replace('!important', '').strip()
    out = None
    if prop == 'color':
        c = parse_color(val)
        if c and lum(c) > 0.62:
            out = text_token(c)
    elif prop in ('background', 'background-color', 'background-image'):
        low = val.lower()
        if 'url(' in low:
            return None
        colors = re.findall(r'#[0-9a-f]{3,6}\b|rgba?\([^)]*\)', low)
        parsed = [parse_color(x) for x in colors]
        parsed = [p for p in parsed if p]
        if parsed:
            dark_or_glass = all((p[3] < 0.6) or lum(p) < 0.32 for p in parsed)
            opaque = [p for p in parsed if p[3] >= 0.6]
            sat = lambda p: colorsys.rgb_to_hls(p[0] / 255, p[1] / 255, p[2] / 255)[2]
            if dark_or_glass:
                out = 'var(--st-panel)'
                prop = 'background'
            elif opaque and all(lum(p) > 0.85 and sat(p) < 0.5 for p in opaque):
                out = 'var(--st-paper)'
                prop = 'background'
            elif opaque and any(lum(p) > 0.45 and sat(p) >= 0.4 for p in opaque):
                out = 'var(--st-brass);color:var(--st-brass-ink)'
                prop = 'background'
    elif prop in ('border-color',) or (prop.startswith('border') and prop.endswith('color')):
        c = parse_color(val)
        if c and (c[3] < 0.7 or lum(c) > 0.8):
            out = 'var(--st-line)'
    elif prop in ('border', 'border-top', 'border-bottom', 'border-left', 'border-right'):
        m = re.search(r'(rgba?\([^)]*\)|#[0-9a-f]{3,6}\b)', val, re.I)
        if m:
            c = parse_color(m.group(1))
            if c and (c[3] < 0.7 or lum(c) > 0.8):
                out = val.replace(m.group(1), 'var(--st-line)')
    elif prop == 'text-shadow':
        out = 'none'
    if out is None:
        return None
    return f'{prop}:{out}{"!important" if important else ""}'

def split_rules(css):
    """Yield (media_prefix, selector, body) for flat and single-level @media rules."""
    i, n = 0, len(css)
    while i < n:
        if css.startswith('@media', i):
            brace = css.index('{', i)
            cond = css[i:brace].strip()
            depth, j = 1, brace + 1
            while depth and j < n:
                depth += {'{': 1, '}': -1}.get(css[j], 0); j += 1
            inner = css[brace + 1:j - 1]
            for _, sel, body in split_rules(inner):
                yield cond, sel, body
            i = j
        elif css.startswith('@', i):
            brace = css.find('{', i); semi = css.find(';', i)
            if semi != -1 and (brace == -1 or semi < brace):
                i = semi + 1; continue
            depth, j = 1, brace + 1
            while depth and j < n:
                depth += {'{': 1, '}': -1}.get(css[j], 0); j += 1
            i = j
        else:
            brace = css.find('{', i)
            if brace == -1: break
            end = css.find('}', brace)
            yield None, css[i:brace].strip(), css[brace + 1:end]
            i = end + 1

def main():
    css = re.sub(r'/\*.*?\*/', '', SRC.read_text(encoding='utf-8'), flags=re.S)
    out, count = [], 0
    for media, sel, body in split_rules(css):
        sel = sel.strip().lstrip('}').strip()
        if not sel or SKIP_SEL.search(sel) or '{' in sel or '}' in sel:
            continue
        parts, depth, cur = [], 0, ''
        for ch in sel:
            if ch == '(': depth += 1
            elif ch == ')': depth -= 1
            if ch == ',' and depth == 0: parts.append(cur); cur = ''
            else: cur += ch
        parts.append(cur)
        sels = [s.strip() for s in parts if s.strip() and not SKIP_SEL.search(s) and not re.search(r'[>+~]\s*$', s.strip())]
        if not sels:
            continue
        decls = []
        for d in re.split(r';(?![^()]*\))', body):
            if ':' not in d: continue
            p, v = d.split(':', 1)
            r = remap_decl(p, v)
            if r: decls.append(r)
        if not decls:
            continue
        scoped = ','.join(('body.station ' + s) if not s.startswith(('html', 'body', ':root')) else s.replace('body', 'body.station', 1) for s in sels)
        rule = f'{scoped}{{{";".join(decls)}}}'
        out.append(f'@media {media[6:].strip()}{{{rule}}}' if media else rule)
        count += 1
    OUT.write_text('/* Generated by tools/station/gen_remap.py from styles.css. Do not edit by hand. */\n' + '\n'.join(out) + '\n', encoding='utf-8')
    print(f'wrote {count} rules to {OUT.relative_to(ROOT)}')

if __name__ == '__main__':
    main()
