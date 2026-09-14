"""Command-line entry point for pack."""

import sys

from core.pack import pack, reduction_report
from core.annotate import annotate, file_blocks


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print("usage: python pack.py <diff-file>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        raw = f.read()

    blocks = file_blocks(annotate(raw))
    result = pack(blocks)

    print()
    reduction_report(raw, result.payload())


if __name__ == "__main__":
    main()
