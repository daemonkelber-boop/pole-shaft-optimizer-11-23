"""
custom_layout.py -- user-specified shaft count, tube lengths and joint types.

Lengths are FABRICATED tube lengths (lap included; embedment included for
the bottom tube), top -> down, for tubes 1..n-1. The bottom tube takes the
remaining height so the total pole length stays as in the XML.

preview_spec() builds the pole for the Pole View preview and clearance check:
XML tip diameter and taper, XML wall thickness per tube (tube k takes the
XML thickness of tube min(k, n_xml); walls never get thinner going down),
laps recomputed (1.1 x 1.5 x female ID, rounded up). The optimizer sizes
diameters, taper and thicknesses itself (OptConstraints.custom_uppers).
"""
from __future__ import annotations

from geometry import PoleSpec, Segment

JOINTS = ["Slip", "Flange"]


def default_from_spec(spec) -> dict:
    """Copy of the XML layout: count, tubes 1..n-1 lengths, joint types."""
    segs = spec.segments
    return dict(n=len(segs),
                lengths=[round(s.length, 2) for s in segs[:-1]],
                joints=["Flange" if s.joint_type == "flange" else "Slip" for s in segs[:-1]])


def preview_spec(spec, lengths, joints, min_tube: float = 15.0, max_tube: float = 60.0):
    """Return (PoleSpec, bottom_length, warnings)."""
    H = spec.total_length
    xml_t = [s.thickness for s in spec.segments]
    fy = spec.segments[0].fy
    n = len(lengths) + 1
    ts = [xml_t[min(k, len(xml_t) - 1)] for k in range(n)]
    for k in range(1, n):                         # never thinner going down
        ts[k] = max(ts[k], ts[k - 1])
    jt = ["flange" if str(j).lower().startswith("f") else "slip" for j in joints]

    def build(bottom):
        segs = [Segment(float(L), ts[k], fy=fy, joint_type=jt[k]) for k, L in enumerate(lengths)]
        segs.append(Segment(max(bottom, 0.25), ts[-1], fy=fy, joint_type="none"))
        return PoleSpec(tip_diameter=spec.tip_diameter, taper=spec.taper, segments=segs,
                        embedment=spec.embedment, slip_clearance=spec.slip_clearance,
                        lap_factor=spec.lap_factor, lap_round=spec.lap_round)

    bottom = H - sum(lengths)
    sp = build(bottom)
    for _ in range(8):                            # laps above the bottom tube do not
        nb = round(H - sum(lengths) + sum(sp.laps()), 4)   # depend on its length
        if abs(nb - bottom) < 1e-6:
            break
        bottom = nb
        sp = build(bottom)
    warn = []
    if bottom < min_tube - 1e-9:
        warn.append(f"bottom tube {bottom:.2f} ft is shorter than the {min_tube:g} ft minimum")
    if bottom > max_tube + 1e-9:
        warn.append(f"bottom tube {bottom:.2f} ft is longer than the {max_tube:g} ft maximum")
    for k, L in enumerate(lengths, 1):
        if L < min_tube - 1e-9 or L > max_tube + 1e-9:
            warn.append(f"tube {k} {L:.2f} ft is outside {min_tube:g}–{max_tube:g} ft")
    if bottom <= 0:
        warn.append("tubes 1..n-1 already exceed the pole height")
    return sp, bottom, warn
