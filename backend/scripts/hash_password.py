#!/usr/bin/env python3
"""Erzeugt einen Passwort-Hash für config/users.yaml.

Aufruf:  python backend/scripts/hash_password.py [passwort]
Ohne Argument wird das Passwort interaktiv (verdeckt) abgefragt.
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import hash_password  # noqa: E402

if __name__ == "__main__":
    passwort = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("Passwort: ")
    print(hash_password(passwort))
