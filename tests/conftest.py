"""Shared pytest fixtures.

Adds the repo root to sys.path so tests can `import dredger` directly.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
