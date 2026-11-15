"""Reuse exact source bytes, without checking out or editing another branch."""
import ast
import bisect
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import ModuleType


def load(name, repo=None):
    pins = json.loads(Path(__file__).with_name('reference-pins.json').read_text())
    pin = pins[name]
    raw = subprocess.run(
        ['git', '--no-replace-objects', 'show', pin['commit'] + ':' + pin['path']],
        cwd=repo or Path(__file__).resolve().parents[2], check=True,
        capture_output=True, timeout=30, env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'}).stdout
    if hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('REFERENCE_BYTES_CHANGED')
    module = ModuleType('_a1b1_pinned_' + name)
    if pin['functions']:
        # Import only the existing pure presence gate, never its collection CLI.
        tree = ast.parse(raw)
        selected = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name in pin['functions']]
        if {n.name for n in selected} != set(pin['functions']):
            raise ValueError('REFERENCE_FUNCTION_MISSING')
        module.__dict__['bisect'] = bisect
        raw = compile(ast.Module(body=selected, type_ignores=[]), pin['path'], 'exec')
    else:
        raw = compile(raw, pin['path'], 'exec')
    exec(raw, module.__dict__)
    return module
