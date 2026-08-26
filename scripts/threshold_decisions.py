#!/usr/bin/env python3
"""Show the threshold decision register and unresolved operating choices."""
from __future__ import annotations

import argparse
import json

from rfisher import selection_policy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check-operational", action="store_true")
    args = parser.parse_args(argv)

    if args.json:
        print(json.dumps(selection_policy.snapshot(), indent=2, sort_keys=True))
    else:
        print(f"policy sha256 {selection_policy.sha256()}")
        print(f"{'status':<12} {'basis':<15} decision")
        for key, item in sorted(selection_policy.DECISIONS.items()):
            print(f"{item.status:<12} {item.basis:<15} {key} = {item.value!r}")

    if args.check_operational:
        unresolved = selection_policy.blockers(
            selection_policy.OPERATIONAL_REQUIRED_IDS)
        if unresolved:
            if args.json:
                return 1
            print("\nunresolved operating decisions")
            for item in unresolved:
                print(f"- {item.id}: {item.status}; {item.rationale}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
