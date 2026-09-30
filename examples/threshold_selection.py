"""Price a detector's fine threshold surface against a science tolerance.

The detector (pilot-proxy) writes each candidate threshold with its masked
fraction and kept residual; the verdict prices them against the band's
tolerance, forms the deployable set of each family and selects inside it.
The rows here are a small synthetic family, not a measurement.
"""
from rfisher import policy
from rfisher.verdict import interval

rules = policy.load()
rows = [{"candidate_set": "fine_surface", "block": "calibration", "threshold_family": "rho=1",
         "eta": 1.0 + 0.05 * i, "masked_fraction": 0.5 - 0.04 * i, "r_sys": 0.2 + 0.06 * i,
         "r_var": None, "candidate_order": i} for i in range(10)]
summary = {"threshold_family": "rho=1", "eta_eval": 1.05, "eta_pfa": 1.1, "eta_pfa_status": "available"}

candidates = interval.points(interval.fine_candidates(rows, rules), r_tol=0.5, policy=rules)
family = interval.interval(candidates, summary)
chosen = interval.select(family.members, rules)
print(f"deployable set: eta in [{family.interval_low:.2f}, {family.interval_high:.2f}] ({family.status})")
print(f"selected: eta {chosen.selected.eta:.2f}, masked fraction {chosen.selected.masked_fraction:.2f}, "
      f"R {chosen.selected.R:.2f}, cost {chosen.selected.cost:.3f}")
