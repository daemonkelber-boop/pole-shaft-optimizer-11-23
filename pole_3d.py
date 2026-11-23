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


def build_figure(L: PoleLayout, T: dict, height_px: int = 900) -> go.Figure:
    """T = Style B tokens (style_b.tokens())."""
    C_STEEL = '#9aa7ad' if T.get('text', '#000').startswith('#0') else '#7f8d94'
    C_EDGE = T.get('chart_ring', '#073247')
    C_LAP = T.get('warning', '#e08d17')
    C_CLAMP = T.get('danger', '#ed352c')
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
                             s.top_agl, s.bot_agl, C_LAP, f'Slip joint {s.no}',
                             hover=hv, scale=1.03))

    # clamps / attachments on the +x flat
    xs, ys, zs, txt, hov = [], [], [], [], []
    for a in L.attachments:
        r = _d_at(L, a.from_top) / 24.0
        xs.append(r * 1.02); ys.append(0.0); zs.append(a.agl)
        txt.append(f'{a.label}  {a.from_top:.2f} ft')
        hov.append(f'{a.label} ({a.kind})<br>{a.from_top:.2f} ft from top · {a.agl:.2f} ft AGL')
    if xs:
        data.append(go.Scatter3d(x=xs, y=ys, z=zs, mode='markers+text', text=txt,
                                 textposition='middle right',
                                 textfont=dict(color=C_CLAMP, size=12),
                                 marker=dict(size=6, color=C_CLAMP, symbol='diamond'),
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
    # true scale: aspect ratio = real extents, largest (height) = 1
    zmax = L.agl_height + 2.0
    zlo = zmin - 1.0
    half = g * 1.05
    dz = zmax - zlo
    axis = dict(showbackground=False, showgrid=False, zeroline=False, title='',
                showticklabels=False, showspikes=False)
    fig.update_layout(
        height=height_px, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor='rgba(0,0,0,0)',
        scene=dict(aspectmode='manual',
                   aspectratio=dict(x=ZOOM * 2 * half / dz, y=ZOOM * 2 * half / dz, z=ZOOM),
                   xaxis=dict(axis, range=[-half, half]),
                   yaxis=dict(axis, range=[-half, half]),
                   zaxis=dict(axis, range=[zlo, zmax]),
                   camera=dict(eye=dict(x=0.42, y=-0.72, z=0.1), center=dict(x=0, y=0, z=0),
                               projection=dict(type='orthographic'))),
    )
    return fig
