#!/usr/bin/env python
"""Utility a riga di comando di Django."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scacchi_web.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Django non è installato o l'ambiente virtuale non è attivo.") from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
