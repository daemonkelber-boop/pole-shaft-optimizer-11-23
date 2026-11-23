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
class ArmPoint:
    label: str              # XML joint label, e.g. 'C2_ARM:T3'
    h: float                # ft, horizontal distance from the pole axis
    agl: float              # ft above GL
    d: float                # in, outside diameter / depth at this point


@dataclass
class Arm:
    label: str              # davit label, e.g. 'C2_ARM', 'C2_BRKT'
    prop: str               # davit property, e.g. 'COND_ARM_27'
    attach: str             # pole attach point name, e.g. 'C2'
    azimuth: float          # deg, from the XML
    length: float           # ft, arm length along its own axis (XML rel_dist at End)
    is_bracket: bool
    shape: str              # e.g. '8F', '4F'
    points: list = field(default_factory=list)   # ArmPoint, origin -> tip
    vangs: list = field(default_factory=list)    # (label, ArmPoint)


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
    arms: list[Arm] = field(default_factory=list)
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

    T = parsed.get('tables', {}) if parsed is not None else {}

    def rows(name):
        return [r for inst in T.get(name, []) for r in inst['rows']]

    # ---- elevations: pole attach points (P:X) from the XML ------------------
    clamp_at = {r.get('structure_and_tip_attach'): (r.get('clamp_label') or '')
                for r in rows('clamp_insulator_connectivity')}
    davit_conn = [{k: (v.get('value') if isinstance(v, dict) else v) for k, v in r.items()}
                  for r in rows('tubular_davit_arm_connectivity')]
    davit_at = {d['attach_label']: d for d in davit_conn}
    rel = rows('relative_attachment_labels_for')
    pts = []
    if rel:
        for r in rel:
            j = r.get('joint_label')
            pts.append((j, _val(r, 'distance_from_origin_top_joint', 0.0)))
        if 'P:t' in clamp_at or 'P:t' in davit_at:
            pts.insert(0, ('P:t', 0.0))
    elif base is not None:                       # fallback: load-model attachments
        pts = [(ap.label, ap.s_pole) for ap in base.attach.values()]
    seen = set()
    for j, s_ in sorted(pts, key=lambda x: x[1]):
        if j in seen:
            continue
        seen.add(j)
        nm = j.split(':', 1)[-1]
        if j in davit_at:
            kind = 'arm'
        elif j in clamp_at:
            kind = 'tip' if s_ <= 1e-6 else 'clamp'
            if j == 'P:t' and clamp_at[j]:
                nm = clamp_at[j]
        else:
            kind = 'attach'
        out.attachments.append(Attachment(label=nm, joint=j, kind=kind, from_top=s_,
                                          agl=agl_h - s_))

    # ---- arms: brackets + davit arms, exact local geometry ------------------
    if davit_conn:
        props = {}
        for r in rows('tubular_davit_properties'):
            props[r.get('davit_property_label')] = r
        geo = {}
        for inst in T.get('intermediate_joints', []):
            td = inst.get('titledetail') or ''
            if '"' in td:
                geo[td.split('"')[1]] = [(r.get('joint_label'), _val(r, 'horz_offset', 0.0),
                                          _val(r, 'vert_offset', 0.0)) for r in inst['rows']]
        dia = {}
        for r in rows('tubular_davit_arm_steel_properties'):
            el = r.get('element_label')
            dia.setdefault(el, []).append((_val(r, 'rel_dist', 0.0), _val(r, 'outer_diam', 0.0),
                                           r.get('joint_label')))
        vang = {}
        for r in rows('vang_connectivity'):
            vang.setdefault(r.get('attach_label'), []).append(r.get('tip_label') or r.get('vang_label'))
        s_of = {a.joint: a.from_top for a in out.attachments}
        placed = {}                                       # joint label -> (h, agl, azimuth)

        def face_h(from_top):
            return (spec.diameter_at(min(max(from_top, 0.0), spec.total_length)) / 24.0)

        todo = list(davit_conn)
        for _ in range(len(todo) + 1):                    # arms hang off brackets: resolve in order
            left = []
            for d in todo:
                lab, att, pr = d['davit_label'], d['attach_label'], d['davit_property_set']
                az = float(d.get('azimuth') or 0.0)
                if att in s_of:                           # on the pole face
                    s_ = s_of[att]
                    h0, z0, root = face_h(s_), agl_h - s_, att.split(':', 1)[-1]
                elif att in placed:                       # on another davit's joint
                    h0, z0, az0, root = placed[att]
                    az = az0 + az                         # assumed relative to the parent
                else:
                    left.append(d)
                    continue
                prop = props.get(pr, {})
                drows = sorted(dia.get(lab, []))
                L_ = drows[-1][0] if drows else 0.0
                d0 = drows[0][1] if drows else _val(prop, 'base_diameter_or_depth', 0.0)
                d1 = drows[-1][1] if drows else _val(prop, 'tip_diameter_or_depth', 0.0)
                pts_ = [ArmPoint(f'{lab}:O', h0, z0, d0)]
                for jl, ho, vo in geo.get(pr, []):
                    f = (ho / L_) if L_ else 1.0
                    # vert_offset is positive DOWN in PLS-POLE
                    pts_.append(ArmPoint(f'{lab}:{jl}', h0 + ho, z0 - vo, d0 + (d1 - d0) * min(f, 1.0)))
                for p_ in pts_:
                    placed[p_.label] = (p_.h, p_.agl, az, root)
                arm = Arm(label=lab, prop=pr, attach=root, azimuth=az, length=L_,
                          is_bracket='BRKT' in lab.upper() or 'BRACKET' in lab.upper(),
                          shape=str(prop.get('steel_shape') or ''), points=pts_)
                for p_ in pts_:
                    for v in vang.get(p_.label, []):
                        arm.vangs.append((v, p_))
                out.arms.append(arm)
            todo = left
            if not todo:
                break

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
