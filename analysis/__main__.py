"""Write the fossil layer for a finished run. Does not start an experiment."""

from __future__ import annotations

import argparse
from pathlib import Path

from analysis.layer import write_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="measure a finished Pegmatite run")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    document = write_record(args.run, args.out)
    decision = document["elemental"]["decision"]
    print(f"{document['run_id']} decision {decision} profiles {document['elemental']['distinct_numeric_profiles']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
