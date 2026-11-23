"""
keepout.py -- clearance from brackets / vangs to the nearest slip joint.

Each elevation (a clamp from the XML, or a row the user adds) can carry a
bracket or vang. The bracket covers a band: `above` ft above the point and
`below` ft below it (0 / 0 = the point itself). The user sets the clear
distance they need between that band and the nearest slip joint zone.

Slip joint zone = top of male tube to bottom of female tube
(PoleLayout.slip_joints). All heights here are ft FROM THE POLE TOP.

gap > 0 : clear distance between band and zone
gap <= 0: band touches or overlaps the slip joint
A row passes when gap >= required clearance. Rows with type 'None' and
clearance 0 are listed but not checked.
"""
from __future__ import annotations

from dataclasses import dataclass

TYPES = ["None", "Bracket", "Vang"]


@dataclass
class Station:
    label: str
    from_top: float
    kind: str = "None"        # 'None', 'Bracket', 'Vang'
    above: float = 0.0        # ft, band above the point
    below: float = 0.0        # ft, band below the point
    clearance: float = 0.0    # ft, required clear distance to nearest slip joint
    source: str = "XML"       # 'XML' or 'user'

    @property
    def band_top(self) -> float:          # from top (smaller = higher)
        return self.from_top - max(self.above, 0.0)

    @property
    def band_bot(self) -> float:
        return self.from_top + max(self.below, 0.0)

    @property
    def checked(self) -> bool:
        return self.kind != "None" or self.clearance > 0


@dataclass
class Result:
    station: Station
    joint_no: int | None      # nearest slip joint
    side: str                 # 'above joint', 'below joint', 'overlaps'
    gap: float | None         # ft, clear distance (negative = overlap depth)
    ok: bool | None           # None = not checked


def gap_to_zone(top_a, bot_a, top_b, bot_b) -> float:
    """Clear distance between two bands given as (top, bottom) from the
    pole top. Negative = overlap depth."""
    return max(top_b - bot_a, top_a - bot_b)


def check(stations: list[Station], slip_joints) -> list[Result]:
    out = []
    for s in stations:
        best = None
        for j in slip_joints:
            g = gap_to_zone(s.band_top, s.band_bot, j.top_from_top, j.bot_from_top)
            if best is None or g < best[1]:
                best = (j, g)
        if best is None:
            out.append(Result(s, None, "no slip joints", None, True if s.checked else None))
            continue
        j, g = best
        if g <= 0:
            side = "overlaps"
        elif s.band_bot <= j.top_from_top:
            side = "above joint"
        else:
            side = "below joint"
        ok = (g >= s.clearance and g > 0) if s.checked else None
        out.append(Result(s, j.no, side, g, ok))
    return out


def stations_from_layout(L) -> list[Station]:
    return [Station(label=a.label, from_top=a.from_top) for a in L.attachments]
