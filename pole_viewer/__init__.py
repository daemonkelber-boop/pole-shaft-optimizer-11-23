"""
pole_viewer -- smooth 3D pole viewer (three.js r160, vendored; no CDN).

A Streamlit custom component: the browser loads three.js once from the
component folder (cached), every rerun only sends the scene JSON. Camera
moves, zoom and focus run entirely in the browser (no server round trip).

scene_from(L, results, T) builds the JSON from a PoleLayout, the keepout
check results and the Style B tokens.
"""
from __future__ import annotations

import os

import streamlit.components.v1 as components

_FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
_component = components.declare_component("pole_viewer", path=_FRONTEND)


def _d_at(L, from_top: float) -> float:
    """Outside flat-to-flat D (in) of the outermost tube at a height (from top)."""
    from_top = min(max(from_top, 0.0), L.total_length)
    for t in L.tubes:
        if t.top_from_top - 1e-9 <= from_top <= t.bot_from_top + 1e-9:
            f = (from_top - t.top_from_top) / max(t.length, 1e-9)
            return t.d_top + f * (t.d_bot - t.d_top)
    return L.tubes[-1].d_bot


def scene_from(L, results, T: dict, token: str = "") -> dict:
    results = results or []
    bad_joints = set().union(*[r.bad_joints for r in results]) if results else set()
    agl = L.agl_of
    colors = dict(
        bg=T.get("bg_surface", "#ffffff"), surface=T.get("bg_surface", "#ffffff"),
        border=T.get("border", "#cdd6da"), text=T.get("text", "#041e2b"),
        muted=T.get("text_muted", "#8399a3"), primary=T.get("primary", "#3d98d3"),
        steel="#9aa7ad" if T.get("text", "#0").startswith("#0") else "#7f8d94",
        edge=T.get("chart_ring", "#073247"), lap=T.get("warning", "#e08d17"),
        bad=T.get("danger", "#ed352c"), zone=T.get("info", "#3d98d3"),
        bracket=T.get("text_secondary", "#2e4a57"), plate=T.get("text_secondary", "#2e4a57"),
        arm="#b7c2c7" if T.get("text", "#0").startswith("#0") else "#9aa7ad",
        label_bg="rgba(255,255,255,0.78)" if T.get("text", "#0").startswith("#0") else "rgba(16,35,46,0.8)",
    )
    tubes = [dict(no=t.no, y0=agl(t.top_from_top), y1=agl(t.bot_from_top), d0=t.d_top, d1=t.d_bot,
                  info=(f"<b>Tube {t.no}</b><br>L = {t.length:.2f} ft · t = {t.thickness:.4g} in"
                        f"<br>D top {t.d_top:.2f} in · D bot {t.d_bot:.2f} in"))
             for t in L.tubes]
    laps = [dict(no=s.no, y0=s.top_agl, y1=s.bot_agl, d0=_d_at(L, s.top_from_top),
                 d1=_d_at(L, s.bot_from_top), bad=s.no in bad_joints,
                 info=(f"<b>Slip joint {s.no}</b> (tube {s.upper_tube} over {s.lower_tube})"
                       f"<br>lap {s.lap:.2f} ft<br>{s.top_from_top:.2f}–{s.bot_from_top:.2f} ft from top"
                       f"<br>{s.top_agl:.2f}–{s.bot_agl:.2f} ft AGL"))
            for s in L.slip_joints]

    if results:
        rows = [(r.station, r) for r in results]
    else:
        from keepout import Station
        rows = [(Station(label=a.label, from_top=a.from_top), None) for a in L.attachments]
    stations = []
    for s, r in rows:
        bad = r is not None and r.ok is False
        info = f"<b>{s.label}</b><br>{s.from_top:.2f} ft from top · {agl(s.from_top):.2f} ft AGL"
        tag = f"{s.label} · {s.from_top:.2f} ft"
        if r is not None and s.checked:
            if s.kind != "None":
                info += f"<br>{s.kind} {s.height_in:.2f} in"
            if r.gap_above is not None:
                info += f"<br>{r.gap_above:.2f} ft to joint {r.above_no} above (needs {s.clr_above:.2f})"
            if r.gap_below is not None:
                info += f"<br>{r.gap_below:.2f} ft to joint {r.below_no} below (needs {s.clr_below:.2f})"
            if bad:
                info += f"<br><b>✗ {r.reason}</b>"
                tag += f"  ✗ {r.reason}"
        st = dict(label=s.label, y=agl(s.from_top), r=_d_at(L, s.from_top) / 24.0, bad=bad,
                  info=info, tag=tag, band=None, zone=None)
        if s.kind != "None" and s.height_in > 0:
            st["band"] = [agl(s.band_top), agl(s.band_bot)]
        if r is not None and s.checked and s.zone_bot - s.zone_top > 0.01:
            zt, zb = max(s.zone_top, 0.0), min(s.zone_bot, L.total_length)
            st["zone"] = dict(y0=agl(zt), y1=agl(zb), d0=_d_at(L, zt), d1=_d_at(L, zb),
                              info=(f"<b>{s.label} clear zone</b> (no slip joint)"
                                    f"<br>{zt:.2f}–{zb:.2f} ft from top · {agl(zt):.2f}–{agl(zb):.2f} ft AGL"
                                    f"<br>band {s.height_in:.2f} in + {s.clr_above:.2f} ft above + "
                                    f"{s.clr_below:.2f} ft below"))
        stations.append(st)

    arms, vangs = [], []
    for a in L.arms:
        sides = 4 if a.shape.upper().startswith("4") else 8 if a.shape.upper().startswith("8") else 12
        tipd = a.points[-1].d if a.points else 0
        info = (f"<b>{a.label}</b> ({a.prop})<br>on {a.attach} · length {a.length:.2f} ft"
                f"<br>{a.shape} · {a.points[0].d:.1f} → {tipd:.1f} in" if a.points else a.label)
        if a.points:
            tp = a.points[-1]
            info += f"<br>tip {tp.h:.2f} ft from pole axis · {tp.agl:.2f} ft AGL"
        arms.append(dict(label=a.label, az=a.azimuth, bracket=a.is_bracket, sides=sides,
                         pts=[[p.h, p.agl, p.d] for p in a.points], info=info,
                         tag=f"{a.attach} arm {a.length:.2f} ft"))
        for v, p in a.vangs:
            vangs.append(dict(label=v, h=p.h, y=p.agl, az=a.azimuth,
                              info=f"<b>Vang {v}</b><br>{p.h:.2f} ft from pole axis · {p.agl:.2f} ft AGL"))

    plate = None
    if L.base_plate and L.base_plate.diameter > 0:
        bp = L.base_plate
        plate = dict(d=bp.diameter, t=bp.thickness,
                     info=(f"<b>Base plate</b> Ø{bp.diameter:.2f} × {bp.thickness:.3f} in"
                           f"<br>{bp.n_bolts} bolts Ø{bp.bolt_diam:.3f} in on {bp.bolt_circle:.2f} in BC"))

    focus = [dict(label="Full pole", y=None, span=0)]
    reach_at = {}
    for a in L.arms:
        reach_at[a.attach] = max([reach_at.get(a.attach, 0.0)] + [p.h for p in a.points])
    # an arm attachment frames the whole arm (view is taller than wide: ~1.8x)
    focus += [dict(label=f"{a.label} · {a.from_top:.2f} ft from top", y=a.agl,
                   span=max(16.0, (reach_at.get(a.label, 0.0) + 4.0) * 1.8))
              for a in L.attachments]
    focus += [dict(label=f"Slip joint {j.no} · {j.top_from_top:.2f}–{j.bot_from_top:.2f} ft",
                   y=(j.top_agl + j.bot_agl) / 2, span=j.lap * 2.2) for j in L.slip_joints]
    focus += [dict(label=f"{s['label']} clear zone", y=(s["zone"]["y0"] + s["zone"]["y1"]) / 2,
                   span=(s["zone"]["y0"] - s["zone"]["y1"]) * 1.3) for s in stations if s["zone"]]
    focus += [dict(label="Base / ground line", y=1.5, span=14)]

    reach = max([L.base_diameter / 24.0 * 1.6] + [p.h for a in L.arms for p in a.points]
                + ([L.base_plate.diameter / 24.0] if L.base_plate else []))
    y_lo = -L.embedment - (L.base_plate.thickness / 12.0 if L.base_plate else 0.0)
    pole = dict(agl=L.agl_height, emb=L.embedment, total=L.total_length,
                fit_h=(L.agl_height - y_lo) * 1.1 + 2.0, mid_y=(L.agl_height + y_lo) / 2,
                ground=max(L.base_diameter / 12.0, (L.base_plate.diameter / 12.0) if L.base_plate else 0) * 0.75,
                reach=reach)
    return dict(token=token, colors=colors, pole=pole, tubes=tubes, laps=laps, stations=stations,
                arms=arms, vangs=vangs, plate=plate, focus=focus)


def pole_viewer(scene: dict, height: int = 820, key: str | None = None):
    return _component(scene=scene, height=height, key=key, default=None)


# ---------------------------------------------------------------------------
# 2D drawing viewer: the matplotlib elevation as vector SVG with smooth
# pan / zoom in the browser (no reruns while navigating).
# ---------------------------------------------------------------------------
_SVG_FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "svg_frontend")
_svg_component = components.declare_component("pole_svg_viewer", path=_SVG_FRONTEND)


def fig_to_svg(fig) -> str:
    """Matplotlib figure -> SVG text (text kept as text: small, sharp, searchable)."""
    import io
    import matplotlib as mpl
    buf = io.StringIO()
    with mpl.rc_context({"svg.fonttype": "none"}):
        fig.savefig(buf, format="svg", bbox_inches="tight", facecolor=fig.get_facecolor())
    s = buf.getvalue()
    i = s.find("<svg")
    return s[i:] if i >= 0 else s


def svg_viewer(svg: str, T: dict, height: int = 820, token: str = "", key: str | None = None):
    import hashlib
    colors = dict(bg=T.get("bg_surface", "#ffffff"), surface=T.get("bg_surface", "#ffffff"),
                  border=T.get("border", "#cdd6da"), text=T.get("text", "#041e2b"),
                  muted=T.get("text_muted", "#8399a3"), primary=T.get("primary", "#3d98d3"))
    return _svg_component(svg=svg, svg_key=hashlib.md5(svg.encode()).hexdigest(), colors=colors,
                          height=height, token=token, key=key, default=None)
