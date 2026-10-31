"""Entry point: `python main.py [--dry-run | --limit N]` runs one sync and exits."""

import logging
import os
import sys

from dotenv import load_dotenv

from rillmark.cli import run

if __name__ == "__main__":
    load_dotenv(override=False)  # exported environment variables win over .env
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    sys.exit(run(sys.argv[1:], os.environ))
