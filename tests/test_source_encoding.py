from pathlib import Path
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UTF8_SOURCE_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".yaml",
    ".yml",
}


def test_tracked_source_files_are_valid_utf8() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout

    source_paths = [
        REPOSITORY_ROOT / path.decode("utf-8")
        for path in tracked.split(b"\0")
        if path and Path(path.decode("utf-8")).suffix.lower() in UTF8_SOURCE_SUFFIXES
    ]

    assert source_paths, "expected at least one tracked source file"
    for source_path in source_paths:
        source_path.read_text(encoding="utf-8")
