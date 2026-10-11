# Previous dashboard (undeployed archive)

These three files are byte-identical to main
`8f45870cf8a0c41c5d32c3ec1296417de23c5db1` before the terminal redesign.
The Pages staging workflow copies only root-level index.html, app.js and styles.css,
so this archive is never served or executed by the public dashboard.

Existing legacy frontend assertions still inspect these files without deleting
their contracts. `tests/test_research_terminal.py` and its Node contract suite
validate the new public interface. Research engines and historical artifacts stay
in their original locations and are unchanged.
