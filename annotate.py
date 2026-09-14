"""Command-line entry point for annotate."""

import sys

from core.annotate import annotate, allow_list, render_for_model


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print("usage: python annotate.py <diff-file>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        diff_text = f.read()

    lines = annotate(diff_text)
    allowed = allow_list(lines)

    print(render_for_model(lines))

    changed = [a for a in lines if a.change != "context"]
    print(f"\n{len(changed)} changed lines, {len(lines) - len(changed)} context lines, "
          f"across {len({a.path for a in lines})} file(s)")

    print("\n--- allow-list (the guard against misplaced comments) ---")
    for path, sides in allowed.items():
        left = ", ".join(str(n) for n in sorted(sides["LEFT"])) or "-"
        right = ", ".join(str(n) for n in sorted(sides["RIGHT"])) or "-"
        print(f"{path}\n    LEFT  (deleted): {left}\n    RIGHT (added):   {right}")


if __name__ == "__main__":
    main()
