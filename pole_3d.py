"""
pole_3d.py -- true-scale 3D pole model (Plotly) from a PoleLayout.

12-sided tubes (flat-to-flat D from the XML), slip joint zones in amber,
clamps on one face, round base plate. Units: ft. z = height above ground
line (GL = 0). Flats face +x/-x and +y/-y; clamps sit on the +x flat.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from pole_layout import PoleLayout

N_SIDES = 12
_ANG = np.radians(15.0 + 30.0 * np.arange(N_SIDES))   # vertex angles -> flat on +x
_RFAC = 1.0 / np.cos(np.radians(15.0))                # circumradius / (D_ff/2)
ZOOM = 1.85   # default fit of the orthographic view (same factor on x, y, z = true scale)


def _ring(d_in, z):
    r = d_in / 24.0 * _RFAC
    return np.c_[r * np.cos(_ANG), r * np.sin(_ANG), np.full(N_SIDES, z)]


def _frustum(d_top, d_bot, z_top, z_bot, color, name, opacity=1.0, hover=None, scale=1.0):
    top, bot = _ring(d_top * scale, z_top), _ring(d_bot * scale, z_bot)
    v = np.vstack([top, bot])
    i, j, k = [], [], []
    n = N_SIDES
    for a in range(n):
        b = (a + 1) % n
        i += [a, b]; j += [b, n + b]; k += [n + a, n + a]
    return go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=i, j=j, k=k, color=color,
                     opacity=opacity, flatshading=True, name=name, showlegend=False,
                     hovertemplate=(hover or name) + '<extra></extra>',
                     lighting=dict(ambient=0.8, diffuse=0.6, specular=0.1, roughness=0.7),
                     lightposition=dict(x=200, y=100, z=300))


def _edges(d_top, d_bot, z_top, z_bot, color):
    """Vertex lines and end rings, so the 12 flats read clearly."""
    top, bot = _ring(d_top, z_top), _ring(d_bot, z_bot)
    xs, ys, zs = [], [], []
    for a in range(N_SIDES):
        xs += [top[a, 0], bot[a, 0], None]; ys += [top[a, 1], bot[a, 1], None]
        zs += [top[a, 2], bot[a, 2], None]
    for ring in (top, bot):
        loop = np.vstack([ring, ring[:1]])
        xs += list(loop[:, 0]) + [None]; ys += list(loop[:, 1]) + [None]
        zs += list(loop[:, 2]) + [None]
    return go.Scatter3d(x=xs, y=ys, z=zs, mode='lines', line=dict(color=color, width=2),
                        hoverinfo='skip', showlegend=False)


def _disk(d_in, z_top, z_bot, color, name, hover, n=72):
    r = d_in / 24.0
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    top = np.c_[r * np.cos(a), r * np.sin(a), np.full(n, z_top)]
    bot = np.c_[r * np.cos(a), r * np.sin(a), np.full(n, z_bot)]
    v = np.vstack([top, bot, [[0, 0, z_top], [0, 0, z_bot]]])
    ct, cb = 2 * n, 2 * n + 1
    i, j, k = [], [], []
    for p in range(n):
        q = (p + 1) % n
        i += [p, q, ct, cb]; j += [q, n + q, q, n + p]; k += [n + p, n + p, p, n + q]
    return go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=i, j=j, k=k, color=color,
                     flatshading=True, name=name, showlegend=False,
                     hovertemplate=hover + '<extra></extra>')


def _d_at(L: PoleLayout, from_top: float) -> float:
    """Outside flat-to-flat D (in) of the outermost tube at a height."""
    for t in L.tubes:                               # top tube first = female wins in a lap
        if t.top_from_top - 1e-9 <= from_top <= t.bot_from_top + 1e-9:
            f = (from_top - t.top_from_top) / max(t.length, 1e-9)
            return t.d_top + f * (t.d_bot - t.d_top)
    return L.tubes[-1].d_bot


def _box(x0, x1, y0, y1, z0, z1, color, hover, opacity=1.0):
    x = [x0, x1, x1, x0, x0, x1, x1, x0]
    y = [y0, y0, y1, y1, y0, y0, y1, y1]
    z = [z0, z0, z0, z0, z1, z1, z1, z1]
    i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3]
    j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4]
    k = [2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7]
    return go.Mesh3d(x=x, y=y, z=z, i=i, j=j, k=k, color=color, opacity=opacity,
                     flatshading=True, showlegend=False,
                     hovertemplate=hover + '<extra></extra>')


def build_figure(L: PoleLayout, T: dict, height_px: int = 900, results=None,
                 focus_agl: float | None = None, zoom: float = 1.0,
                 view: str = 'iso') -> go.Figure:
    """T = Style B tokens (style_b.tokens()). results = keepout.check() output."""
    results = results or []
    bad_joints = set().union(*[r.bad_joints for r in results]) if results else set()
    C_STEEL = '#9aa7ad' if T.get('text', '#000').startswith('#0') else '#7f8d94'
    C_EDGE = T.get('chart_ring', '#073247')
    C_LAP = T.get('warning', '#e08d17')
    C_CLAMP = T.get('primary', '#3d98d3')
    C_BAD = T.get('danger', '#ed352c')
    C_BRK = T.get('text_secondary', '#2e4a57')
    C_ZONE = T.get('info', '#3d98d3')
    C_TEXT = T.get('text', '#041e2b')
    C_PLATE = T.get('text_secondary', '#2e4a57')

    z = L.agl_of
    data = []

    for t in L.tubes:
        hv = (f'Tube {t.no}<br>L = {t.length:.2f} ft · t = {t.thickness:.4g} in'
              f'<br>D top {t.d_top:.2f} in · D bot {t.d_bot:.2f} in')
        data.append(_frustum(t.d_top, t.d_bot, z(t.top_from_top), z(t.bot_from_top),
                             C_STEEL, f'Tube {t.no}', hover=hv))
        data.append(_edges(t.d_top, t.d_bot, z(t.top_from_top), z(t.bot_from_top), C_EDGE))

    for s in L.slip_joints:
        hv = (f'Slip joint {s.no} (tube {s.upper_tube} over tube {s.lower_tube})'
              f'<br>lap {s.lap:.2f} ft'
              f'<br>top {s.top_from_top:.2f} ft from top · {s.top_agl:.2f} ft AGL'
              f'<br>bottom {s.bot_from_top:.2f} ft from top · {s.bot_agl:.2f} ft AGL')
        data.append(_frustum(_d_at(L, s.top_from_top), _d_at(L, s.bot_from_top),
                             s.top_agl, s.bot_agl, C_BAD if s.no in bad_joints else C_LAP,
                             f'Slip joint {s.no}',
                             hover=hv, scale=1.03))

    # clearance zones: see-through sleeve over band + clearance above / below
    for r in results:
        s = r.station
        if not s.checked or s.zone_bot - s.zone_top < 0.01:
            continue
        zt = max(s.zone_top, 0.0); zb = min(s.zone_bot, L.total_length)
        bad = r.ok is False
        hv = (f'{s.label} clear zone (no slip joint)<br>{zt:.2f}–{zb:.2f} ft from top'
              f'<br>{L.agl_of(zt):.2f}–{L.agl_of(zb):.2f} ft AGL'
              f'<br>band {s.height_in:.2f} in + {s.clr_above:.2f} ft above + '
              f'{s.clr_below:.2f} ft below')
        data.append(_frustum(_d_at(L, zt), _d_at(L, zb), L.agl_of(zt), L.agl_of(zb),
                             C_BAD if bad else C_ZONE, f'{s.label} clear zone',
                             opacity=0.28, hover=hv, scale=1.35))
        data.append(_edges(_d_at(L, zt) * 1.35, _d_at(L, zb) * 1.35, L.agl_of(zt), L.agl_of(zb),
                           C_BAD if bad else C_ZONE))

    # elevations (clamps from the XML + user rows) on the +x flat
    if results:
        pts = [(r.station.label, r.station.from_top, r.station.kind, r) for r in results]
    else:
        pts = [(a.label, a.from_top, a.kind, None) for a in L.attachments]
    groups = {}
    for label, ft, kind, r in pts:
        rr = _d_at(L, min(max(ft, 0.0), L.total_length)) / 24.0
        bad = r is not None and r.ok is False
        g = groups.setdefault(bad, ([], [], [], [], []))
        g[0].append(rr * 1.02); g[1].append(0.0); g[2].append(L.agl_of(ft))
        tag = f'{label}  {ft:.2f} ft'
        hv = f'{label}<br>{ft:.2f} ft from top · {L.agl_of(ft):.2f} ft AGL'
        if r is not None and r.station.checked:
            s_ = r.station
            if s_.kind != 'None':
                hv += f'<br>{s_.kind} {s_.height_in:.2f} in'
            if r.gap_above is not None:
                hv += f'<br>{r.gap_above:.2f} ft to joint {r.above_no} above (needs {s_.clr_above:.2f})'
            if r.gap_below is not None:
                hv += f'<br>{r.gap_below:.2f} ft to joint {r.below_no} below (needs {s_.clr_below:.2f})'
            if bad:
                tag += f'  ✗ {r.reason}'
        g[3].append(tag); g[4].append(hv)
        # bracket / vang band as a plate on the +x face
        if r is not None and r.station.kind != 'None' and r.station.height_in > 0:
            s = r.station
            w = rr * 0.55
            data.append(_box(rr, rr + 0.35, -w, w, L.agl_of(s.band_bot), L.agl_of(s.band_top),
                             C_BAD if bad else C_BRK,
                             f'{label} {s.kind} {s.height_in:.2f} in'))
    for bad, (xs, ys, zs, txt, hov) in groups.items():
        col = C_BAD if bad else C_CLAMP
        data.append(go.Scatter3d(x=xs, y=ys, z=zs, mode='markers+text', text=txt,
                                 textposition='middle right',
                                 textfont=dict(color=col, size=12),
                                 marker=dict(size=6, color=col, symbol='diamond'),
                                 hovertext=hov, hoverinfo='text', showlegend=False))

    zmin = -L.embedment
    if L.base_plate and L.base_plate.diameter > 0:
        bp = L.base_plate
        tp = bp.thickness / 12.0
        hv = (f'Base plate Ø{bp.diameter:.2f} in × {bp.thickness:.3f} in'
              f'<br>{bp.n_bolts} bolts Ø{bp.bolt_diam:.3f} in on {bp.bolt_circle:.2f} in BC')
        data.append(_disk(bp.diameter, 0.0, -tp, C_PLATE, 'Base plate', hv))
        zmin = -tp

    # ground line marker (thin square outline)
    g = max(L.base_diameter / 12.0, (L.base_plate.diameter / 12.0) if L.base_plate else 0) * 1.2
    data.append(go.Scatter3d(x=[-g, g, g, -g, -g], y=[-g, -g, g, g, -g], z=[0] * 5,
                             mode='lines', line=dict(color=C_TEXT, width=2, dash='dash'),
                             hoverinfo='skip', showlegend=False))
    data.append(go.Scatter3d(x=[g], y=[-g], z=[0], mode='text', text=['GL'],
                             textfont=dict(color=C_TEXT, size=12), hoverinfo='skip',
                             showlegend=False))

    fig = go.Figure(data=data)
    # true scale: same factor on x, y, z. Zoom = bigger scene box in the
    # orthographic view; focus = camera centre at that height (AGL).
    zmax = L.agl_height + 2.0
    zlo = zmin - 1.0
    half = g * 1.05
    dz = zmax - zlo
    k = ZOOM * max(zoom, 1.0)
    ar = dict(x=k * 2 * half / dz, y=k * 2 * half / dz, z=k)
    zf = (zlo + zmax) / 2 if focus_agl is None or zoom <= 1.0 else focus_agl
    cz = (zf - (zlo + zmax) / 2) / dz * ar['z']
    # plotly x = PLS +Y (transverse, clamps face), plotly y = -PLS X
    dirs = {'iso': (0.42, -0.72, 0.1), 'transverse': (0.0, -0.85, 0.0),
            'longitudinal': (-0.85, 0.0, 0.0), 'top': (0.0, -0.05, 0.85)}
    ex, ey, ez = dirs.get(view, dirs['iso'])
    axis = dict(showbackground=False, showgrid=False, zeroline=False, title='',
                showticklabels=False, showspikes=False)
    fig.update_layout(
        height=height_px, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor='rgba(0,0,0,0)',
        # keep the user's own rotation across reruns until focus / zoom / view change
        uirevision=f"{focus_agl}-{zoom}-{view}",
        scene=dict(aspectmode='manual', aspectratio=ar, dragmode='turntable',
                   xaxis=dict(axis, range=[-half, half]),
                   yaxis=dict(axis, range=[-half, half]),
                   zaxis=dict(axis, range=[zlo, zmax]),
                   camera=dict(eye=dict(x=ex, y=ey, z=cz + ez), center=dict(x=0, y=0, z=cz),
                               up=dict(x=0, y=0, z=1),
                               projection=dict(type='orthographic'))),
    )
    return fig
