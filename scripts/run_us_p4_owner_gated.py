"""Dormant P4 entry point; never executed on import."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.us_p4_execution import cli  # noqa: E402
if __name__=='__main__':
    raise SystemExit(cli())
