#!/usr/bin/env python
"""Django management script."""
import os
import sys


def main() -> None:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marketlab_backend.settings.local')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Make sure it's installed and your venv is active."
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
