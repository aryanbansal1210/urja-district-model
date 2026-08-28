"""Stage E - owner-finance tests. Direct-runner style; NO solve
(reads outputs/data/energy/equity_report.json). Run: python tests/test_owner_finance.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics                      # noqa: E402
from energy.owner_finance import (                           # noqa: E402
    build_owner_finance, write_owner_finance_json, _npv, _irr, _payback_years,
)

_EQ = os.path.join(ROOT, "outputs", "data", "energy", "equity_report.json")


def _rep():
    eq = json.load(open(_EQ, encoding="utf-8"))
    return build_owner_finance(eq, load_economics(force_reload=True))


def test_npv_irr_math_sanity():
    # A 1-year project: invest 100, get 110 -> NPV@10% = 0, IRR = 10%.
    npv = _npv(0.10, 100.0, 110.0, 0.0, 0.0, 1)
    assert abs(npv) < 1.0, npv
    irr = _irr(100.0, 110.0, 0.0, 0.0, 1)
    assert irr is not None and abs(irr - 0.10) < 0.01, irr
    pb = _payback_years(100.0, 50.0, 0.0, 0.0, 10)
    assert pb is not None and abs(pb - 2.0) < 0.01, pb


def test_owner_occupiers_have_positive_npv():
    rep = _rep()
    for cls in ("mid_residential", "high_residential", "industrial", "commercial_public"):
        t = rep["by_tier"][cls]
        assert t["npv_owner_rate_inr"] > 0, (cls, t["npv_owner_rate_inr"])
        assert t["simple_payback_years"] is not None and t["simple_payback_years"] < 25


def test_ews_gov_investor_npv_negative_but_tenant_benefits():
    rep = _rep()
    ews = rep["by_tier"]["ews"]
    # gov bears the social cost (negative investor NPV); tenant saves a lot.
    assert ews["npv_owner_rate_inr"] < 0, ews["npv_owner_rate_inr"]
    assert ews["resident_lifetime_saving_inr"] > 0
    assert ews["resident_annual_saving_inr"] > 0


def test_social_npv_exceeds_private_npv():
    # Lower (5%) social discount rate -> higher NPV than owner rates.
    rep = _rep()
    d = rep["district_totals"]
    assert d["npv_at_social_5pct_inr"] > d["npv_at_owner_rates_inr"], d


def test_report_json_round_trips(tmp_path=None):
    import tempfile
    rep = _rep()
    with tempfile.TemporaryDirectory() as dd:
        p = os.path.join(dd, "owner_finance.json")
        write_owner_finance_json(rep, p)
        back = json.load(open(p, encoding="utf-8"))
    for k in ("meta", "by_tier", "district_totals"):
        assert k in back


def main():
    import time
    import traceback
    fns = [v for k, v in sorted(globals().items()) if callable(v) and k.startswith("test_")]
    passed, failed = [], []
    for fn in fns:
        t = time.time()
        try:
            fn()
            print(f"  OK   {fn.__name__}  ({time.time()-t:.2f}s)")
            passed.append(fn.__name__)
        except Exception as e:  # noqa: BLE001
            print(f"  XX   {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed.append(fn.__name__)
    print(f"\nPASS {len(passed)}  FAIL {len(failed)}")
    if failed:
        sys.exit(1)
    print("all owner_finance tests passed")


if __name__ == "__main__":
    main()
