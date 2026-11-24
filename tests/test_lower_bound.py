"""The search's lower-bound weight must never exceed a design's real weight,
or the pruning skips designs that would win (found on 007 R1, Nov 2026:
bound 50,072 lb vs real 46,588 lb).

Runs only when POLE_TEST_XML points to a PLS-POLE XML (no customer XML is
kept in this public repo):  POLE_TEST_XML=path/to/pole.xml pytest -q
"""
import os

import pytest

XML = os.environ.get("POLE_TEST_XML")
pytestmark = pytest.mark.skipif(not XML or not os.path.exists(XML or ""),
                                reason="set POLE_TEST_XML to a PLS-POLE XML")


def test_bound_not_above_real_weight():
    from loads import Baseline
    from optimizer import Design, Optimizer, OptConstraints
    from pls_pole_xml_parser import parse_pls_pole_xml

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "app.py")).read()       # build_spec lives in app.py
    ns = {}
    exec("import numpy as np\n" + src[src.index("def xml_lap_gap"):
                                      src.index("@st.cache_resource(show_spinner=False)\ndef run_candidate")], ns)
    spec = ns["build_spec"](parse_pls_pole_xml(XML))
    base = Baseline.from_xml(XML)
    tip, bs = spec.tip_diameter, spec.base_diameter
    C = OptConstraints(tip_min=tip - 3, tip_max=tip + 3, base_min=bs - 3, base_max=bs + 3,
                       taper_max=0.6, time_limit_s=60)
    o = Optimizer(base, spec, C, lambda f, m: None)
    ups = tuple(sg.length for sg in spec.segments[:-1])
    checked = 0
    for dt in (-1.0, 0.0, 1.0):
        for db in (-1.0, 0.0, 1.0):
            d = Design(round(tip + dt, 1), round(bs + db, 1), ups, ())
            lb, idx = o._lower_bound(d)
            if lb is None:
                continue
            e = o.size(Design(d.tip, d.base, ups, idx))
            if e is None:
                continue
            checked += 1
            assert lb <= e.weight * 1.0001, (d, lb, e.weight)
    assert checked > 0
