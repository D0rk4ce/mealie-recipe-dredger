"""config.py was a stale refactor leftover — no module imports it.
Pin that we don't accidentally reintroduce the duplication.
"""
import os
import re


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python_sources():
    for dirpath, dirs, files in os.walk(REPO):
        # Skip venv, tests, hidden dirs
        dirs[:] = [d for d in dirs if d not in ('.venv', 'tests', '__pycache__') and not d.startswith('.')]
        for f in files:
            if f.endswith('.py'):
                yield os.path.join(dirpath, f)


def test_no_source_file_imports_config_module():
    pattern = re.compile(r'^\s*(from\s+config\s+import|import\s+config\b)', re.MULTILINE)
    offenders = []
    for path in _python_sources():
        with open(path) as f:
            if pattern.search(f.read()):
                offenders.append(path)
    assert offenders == [], (
        f"config.py is dead — these files reintroduce the duplication: {offenders}"
    )


def test_config_py_is_removed():
    assert not os.path.exists(os.path.join(REPO, 'config.py')), \
        "config.py was a never-used duplicate; remove it instead of letting it drift"
