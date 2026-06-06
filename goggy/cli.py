"""Command-line entry points for Goggy."""

from __future__ import annotations

import argparse
import getpass
import sys


def _run(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "goggy.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        ssl_certfile=args.ssl_certfile or None,
        ssl_keyfile=args.ssl_keyfile or None,
    )


def _hash(_args: argparse.Namespace) -> None:
    import bcrypt

    pw = getpass.getpass("New admin password: ")
    if pw != getpass.getpass("Confirm: "):
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)
    digest = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    print("\nSet this in your environment:\n")
    print(f"  export GOGGY_ADMIN_PASSWORD_HASH='{digest}'")


def main() -> None:
    parser = argparse.ArgumentParser(prog="goggy", description="Goggy blog server")
    sub = parser.add_subparsers(dest="cmd")

    from . import config

    run = sub.add_parser("run", help="Run the web server")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8000)
    run.add_argument("--reload", action="store_true", help="Auto-reload on changes")
    run.add_argument(
        "--ssl-certfile",
        default=config.SSL_CERTFILE,
        help="Path to a TLS certificate; serves HTTPS when set (with --ssl-keyfile)",
    )
    run.add_argument(
        "--ssl-keyfile",
        default=config.SSL_KEYFILE,
        help="Path to the TLS private key",
    )
    run.set_defaults(func=_run)

    hash_cmd = sub.add_parser("hash", help="Generate an admin password hash")
    hash_cmd.set_defaults(func=_hash)

    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()