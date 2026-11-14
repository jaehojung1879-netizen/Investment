"""Read a function definition only; no census computation or outcomes."""
import ast
import inspect
import json
from pathlib import Path
import sys

source = (Path(sys.argv[1]) / "research/evidence_first_v2/census.py").read_text()
node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "b1_screen")
namespace = {}
exec(compile(ast.get_source_segment(source, node), "<b1_screen definition only>", "exec"), namespace)
doc = namespace["b1_screen"].__doc__
print(json.dumps({"python": sys.version.split()[0], "strip": doc.strip(), "cleandoc": inspect.cleandoc(doc)}))
