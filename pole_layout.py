"""
pole_layout.py -- one place that lists where everything sits on the pole.

Built from the PoleSpec (geometry.py), the Baseline attachments (loads.py)
and the parsed XML. Used by the Pole View tab (2D + 3D) and, next, by the
slip-joint keep-out check.

Conventions
  from_top : ft measured down from the pole tip (PLS-POLE "distance from
             origin top joint"; same as PoleSpec rel_dist)
  agl      : ft above ground line (negative = embedded)
  Slip joint zone = top of male tube (upper end of overlap) to bottom of
  female tube (lower end of overlap). The upper tube is the female.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Tube:
    no: int
    top_from_top: float
    bot_from_top: float
    length: float
    thickness: float
    d_top: float            # in, flat-to-flat
    d_bot: float            # in, flat-to-flat
    joint_below: str        # 'slip', 'flange' or 'base'


@dataclass
class SlipJoint:
    no: int                 # 1 = highest joint
    upper_tube: int         # female
    lower_tube: int         # male
    top_from_top: float     # top of male (upper end of overlap)
    bot_from_top: float     # bottom of female (lower end of overlap)
    lap: float
    top_agl: float
    bot_agl: float


@dataclass
class Attachment:
    label: str              # e.g. 'C1', 'SW'
    joint: str              # XML joint label, e.g. 'P:C1'
    kind: str               # 'clamp', 'davit', 'tip' ...
    from_top: float
    agl: float
    arm_length: float = 0.0  # ft, horizontal reach (0 = clamp on face)


@dataclass
class BasePlate:
    diameter: float         # in
    thickness: float        # in
    hole: float             # in
    bolt_circle: float      # in
    n_bolts: int
    bolt_diam: float        # in


@dataclass
class PoleLayout:
    label: str
    total_length: float
    agl_height: float
    embedment: float
    tip_diameter: float
    base_diameter: float
    tubes: list[Tube] = field(default_factory=list)
    slip_joints: list[SlipJoint] = field(default_factory=list)
    flange_joints: list[float] = field(default_factory=list)   # from_top
    attachments: list[Attachment] = field(default_factory=list)
    base_plate: BasePlate | None = None

    def agl_of(self, from_top: float) -> float:
        return self.agl_height - from_top


def _val(row, key, default=None):
    v = row.get(key, default) if row else default
    if isinstance(v, dict):
        v = v.get('value', default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def build_layout(spec, base=None, parsed=None) -> PoleLayout:
    """spec: geometry.PoleSpec; base: loads.Baseline (attachments);
    parsed: parse_pls_pole_xml() dict (clamp names, base plate)."""
    lay = spec.layout()
    agl_h = spec.agl_height
    out = PoleLayout(label=spec.label, total_length=spec.total_length,
                     agl_height=agl_h, embedment=spec.embedment,
                     tip_diameter=spec.tip_diameter, base_diameter=spec.base_diameter)

    for i, tb in enumerate(lay):
        last = i == len(lay) - 1
        out.tubes.append(Tube(no=tb['tube_no'], top_from_top=tb['start'], bot_from_top=tb['end'],
                              length=tb['length'], thickness=tb['thickness'],
                              d_top=tb['d_top'], d_bot=tb['d_bot'],
                              joint_below='base' if last else tb['joint_type']))
        if last:
            continue
        if tb['lap'] > 0:
            top = tb['end'] - tb['lap']
            out.slip_joints.append(SlipJoint(
                no=len(out.slip_joints) + 1, upper_tube=tb['tube_no'],
                lower_tube=lay[i + 1]['tube_no'], top_from_top=top, bot_from_top=tb['end'],
                lap=tb['lap'], top_agl=agl_h - top, bot_agl=agl_h - tb['end']))
        else:
            out.flange_joints.append(tb['end'])

    # clamp names from the XML (P:C1 -> C1), else strip the 'P:' prefix
    names = {}
    if parsed is not None:
        for inst in parsed.get('tables', {}).get('clamp_insulator_connectivity', []):
            for r in inst['rows']:
                j = r.get('structure_and_tip_attach')
                if j:
                    names[j] = ('clamp', r.get('clamp_label') or j)
    if base is not None:
        for ap in sorted(base.attach.values(), key=lambda a: a.s_pole):
            kind, nm = names.get(ap.label, (None, None))
            if kind is None:
                kind = 'davit' if ap.extra_horz > 0 else 'attach'
                nm = ap.label.split(':', 1)[-1]
            if ap.s_pole <= 1e-6 and kind == 'clamp':
                kind = 'tip'
            out.attachments.append(Attachment(label=nm, joint=ap.label, kind=kind,
                                              from_top=ap.s_pole, agl=agl_h - ap.s_pole,
                                              arm_length=ap.extra_horz))

    if parsed is not None:
        rows = [r for inst in parsed.get('tables', {}).get('base_plate_properties', [])
                for r in inst['rows']]
        is_bp = spec.embedment == 0
        if rows and is_bp:
            r = rows[0]
            out.base_plate = BasePlate(diameter=_val(r, 'plate_diam', 0.0),
                                       thickness=_val(r, 'plate_thick', 0.0),
                                       hole=_val(r, 'hole_diam', 0.0),
                                       bolt_circle=_val(r, 'bolt_pattern_diam', 0.0),
                                       n_bolts=int(_val(r, 'num_of_bolts', 0) or 0),
                                       bolt_diam=_val(r, 'bolt_diam', 0.0))
    return out


def location_rows(L: PoleLayout) -> list[dict]:
    """Flat table of every location on the pole, tip to base."""
    rows = []
    for a in L.attachments:
        rows.append({'item': a.label, 'type': {'tip': 'clamp (tip)'}.get(a.kind, a.kind),
                     'from top (ft)': a.from_top, 'above GL (ft)': a.agl, 'length (ft)': None})
    for s in L.slip_joints:
        rows.append({'item': f'Slip joint {s.no} top (male top, tube {s.lower_tube})',
                     'type': 'slip joint', 'from top (ft)': s.top_from_top,
                     'above GL (ft)': s.top_agl, 'length (ft)': s.lap})
        rows.append({'item': f'Slip joint {s.no} bottom (female bottom, tube {s.upper_tube})',
                     'type': 'slip joint', 'from top (ft)': s.bot_from_top,
                     'above GL (ft)': s.bot_agl, 'length (ft)': s.lap})
    for k, f in enumerate(L.flange_joints, 1):
        rows.append({'item': f'Flange joint {k}', 'type': 'flange', 'from top (ft)': f,
                     'above GL (ft)': L.agl_of(f), 'length (ft)': None})
    rows.append({'item': 'Ground line', 'type': 'GL', 'from top (ft)': L.agl_height,
                 'above GL (ft)': 0.0, 'length (ft)': None})
    if L.embedment > 0:
        rows.append({'item': 'Pole butt', 'type': 'base', 'from top (ft)': L.total_length,
                     'above GL (ft)': -L.embedment, 'length (ft)': None})
    rows.sort(key=lambda r: r['from top (ft)'])
    return rows
