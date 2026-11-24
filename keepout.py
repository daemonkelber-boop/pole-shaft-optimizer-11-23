"""
keepout.py -- clearance from brackets / vangs to slip joints.

Each elevation (a clamp from the XML, or a row the user adds) can carry a
bracket or vang of overall height H (inches). The band is centred on the
elevation: H/2 above and H/2 below. The user sets two clear distances (ft):

  clr_above : band TOP    to the bottom of the nearest slip joint ABOVE it
  clr_below : band BOTTOM to the top    of the nearest slip joint BELOW it

Slip joint zone = top of male tube to bottom of female tube. All heights
in this module are ft FROM THE POLE TOP (larger = lower on the pole).

A row is checked when it has a bracket/vang or a clearance > 0. It fails
when a slip joint overlaps or touches the band, or a gap is below its
required clearance. The optimizer uses zone_conflict() on every candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

TYPES = ["None", "Bracket", "Vang"]
GROUP = "Group"     # same-shaft group: no joint may sit inside its span


@dataclass
class Station:
    label: str
    from_top: float
    kind: str = "None"          # 'None', 'Bracket', 'Vang'
    height_in: float = 0.0      # overall bracket / vang height (in), split half / half
    clr_above: float = 0.0      # ft, band top to slip joint above
    clr_below: float = 0.0      # ft, band bottom to slip joint below
    source: str = "XML"         # 'XML' or 'user'
    #: same-shaft group: (top, bottom) ft from top of the span no joint may
    #: enter -- from the top of the highest member's clear zone to the bottom
    #: of the lowest one. Touching the span edge is allowed (the members'
    #: clearances are already inside it).
    span: Optional[tuple] = None

    @property
    def half(self) -> float:
        return max(self.height_in, 0.0) / 24.0          # ft

    @property
    def band_top(self) -> float:
        return self.span[0] if self.span else self.from_top - self.half

    @property
    def band_bot(self) -> float:
        return self.span[1] if self.span else self.from_top + self.half

    @property
    def zone_top(self) -> float:
        """Top of the no-slip-joint zone (band top minus clearance above)."""
        return self.band_top - max(self.clr_above, 0.0)

    @property
    def zone_bot(self) -> float:
        """Bottom of the no-slip-joint zone (band bottom plus clearance below)."""
        return self.band_bot + max(self.clr_below, 0.0)

    @property
    def checked(self) -> bool:
        return self.kind != "None" or self.clr_above > 0 or self.clr_below > 0


@dataclass
class Result:
    station: Station
    above_no: Optional[int]     # nearest slip joint above the band
    gap_above: Optional[float]
    below_no: Optional[int]     # nearest slip joint below the band
    gap_below: Optional[float]
    overlap_no: Optional[int]   # slip joint overlapping / touching the band
    ok: Optional[bool]          # None = not checked
    reason: str = ""

    @property
    def bad_joints(self) -> set:
        if self.ok is not False:
            return set()
        out = set()
        if self.overlap_no is not None:
            out.add(self.overlap_no)
        if self.gap_above is not None and self.gap_above < self.station.clr_above:
            out.add(self.above_no)
        if self.gap_below is not None and self.gap_below < self.station.clr_below:
            out.add(self.below_no)
        return out


def zone_conflict(top: float, bot: float, s: Station) -> Optional[str]:
    """Reason a slip joint zone (top, bot from pole top) breaks station s,
    or None. Used by both the Pole View check and the optimizer."""
    if not s.checked:
        return None
    if s.span:                                                          # same-shaft group
        if bot <= s.band_top + 1e-9 or top >= s.band_bot - 1e-9:
            return None
        return "joint inside the same-shaft span"
    if bot < s.band_top - 1e-9:                                         # joint above band
        gap = s.band_top - bot
        if gap < s.clr_above - 1e-9:
            return f"{gap:.2f} ft below a slip joint, needs {s.clr_above:.2f}"
        return None
    if top > s.band_bot + 1e-9:                                         # joint below band
        gap = top - s.band_bot
        if gap < s.clr_below - 1e-9:
            return f"{gap:.2f} ft above a slip joint, needs {s.clr_below:.2f}"
        return None
    return "slip joint overlaps the elevation / band"


def check(stations: Iterable[Station], slip_joints) -> list[Result]:
    out = []
    for s in stations:
        above = [(s.band_top - j.bot_from_top, j.no) for j in slip_joints
                 if j.bot_from_top < s.band_top - 1e-9]
        below = [(j.top_from_top - s.band_bot, j.no) for j in slip_joints
                 if j.top_from_top > s.band_bot + 1e-9]
        eps = -1e-9 if s.span else 1e-9          # groups: touching the span edge is fine
        over = [j.no for j in slip_joints
                if not (j.bot_from_top < s.band_top - eps or j.top_from_top > s.band_bot + eps)]
        ga, na = min(above) if above else (None, None)
        gb, nb = min(below) if below else (None, None)
        no = over[0] if over else None
        if not s.checked:
            ok, why = None, ""
        elif no is not None:
            ok, why = False, (f"joint {no} inside the same-shaft span" if s.span
                              else f"inside slip joint {no}")
        else:
            why = []
            if ga is not None and ga < s.clr_above - 1e-9:
                why.append(f"{ga:.2f} < {s.clr_above:.2f} ft to joint {na} above")
            if gb is not None and gb < s.clr_below - 1e-9:
                why.append(f"{gb:.2f} < {s.clr_below:.2f} ft to joint {nb} below")
            ok, why = (not why), "; ".join(why)
        out.append(Result(s, na, ga, nb, gb, no, ok, why))
    return out


def stations_from_df(df) -> list[Station]:
    """Rows of the Pole View table (canonical form, 'from_top' column)."""
    out = []
    for i, r in df.reset_index(drop=True).iterrows():
        out.append(Station(label=str(r["Item"]) or f"row {i + 1}", from_top=float(r["from_top"]),
                           kind=str(r["Bracket / vang"]), height_in=float(r["Height (in)"]),
                           clr_above=float(r["Clear to joint above (ft)"]),
                           clr_below=float(r["Clear to joint below (ft)"]),
                           source=str(r["Source"])))
    return out


def group_station(label: str, members: list) -> Optional[Station]:
    """Same-shaft group from member Stations: span = top of the highest
    clear zone to the bottom of the lowest. None if fewer than 2 members."""
    if len(members) < 2:
        return None
    top = min(m.zone_top for m in members)
    bot = max(m.zone_bot for m in members)
    return Station(label=label, from_top=(top + bot) / 2, kind=GROUP, source="group", span=(top, bot))


class _J:
    def __init__(self, no, top, bot, kind):
        self.no, self.top_from_top, self.bot_from_top, self.kind = no, top, bot, kind


def all_joints(L) -> list:
    """Slip joints (lap zones) and flange joints (zero length) of a
    PoleLayout, top -> down. Flanges are numbered F1, F2 ..."""
    out = [_J(j.no, j.top_from_top, j.bot_from_top, "slip") for j in L.slip_joints]
    out += [_J(f"F{k}", f, f, "flange") for k, f in enumerate(L.flange_joints, 1)]
    return sorted(out, key=lambda j: j.top_from_top)
