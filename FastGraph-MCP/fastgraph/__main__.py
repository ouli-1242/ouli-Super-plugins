# mypy: disable-error-code=import-untyped
"""Entry point for `python -m fastgraph`."""

from fastgraph.cli import main

if __name__ == "__main__":
    raise SystemExit(main())