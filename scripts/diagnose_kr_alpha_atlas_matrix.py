"""Source-only matrix diagnostic. Deliberately has no execute action."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import kr_alpha_atlas_matrix_diagnostics as D  # noqa: E402
from pipeline.kr_alpha_atlas_phase_c import contract  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['sample', 'bars', 'preflight'])
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--expected-main')
    args = parser.parse_args()
    D.run(contract.ROOT, args.work, args.action, args.expected_main)


if __name__ == '__main__':
    main()
