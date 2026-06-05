"""Convenience launcher: `python main.py` runs the Goggy dev server.

For production use `goggy run` (installed console script) or point a real ASGI
server at `goggy.main:app`.
"""

from goggy.cli import main

if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        sys.argv.append("run")
    main()
