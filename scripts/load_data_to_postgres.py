#!/usr/bin/env python3
"""
Point d'entrée rétrocompatible.

L'ancien script `load_data_to_postgres.py` n'était plus aligné avec le schéma
réel. On délègue désormais vers `load_complete_data_to_postgres.py`.
"""

from load_complete_data_to_postgres import main


if __name__ == "__main__":
    main()
