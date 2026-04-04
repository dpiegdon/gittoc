# gittoc Release Checklist

This is a pragmatic checklist for all public `gittoc` releases.

## Run internal testsuite

Validate zero failures for testsuite:
```bash
python3 -m unittest scripts.tests.test_gittoc
python3 -m py_compile scripts/gittoc scripts/gittoc_lib/*.py scripts/tests/test_gittoc.py
```

## Verify correctness of documentation and embedding procedure

Verify documentation:
- `README.md`
- `SKILL.md` (succinct version with things needed by agent only)

Verify and test embedding into new repositories:
- Does the described procedure in `README.md` work correctly?
- Do agents with blank context pick the installed skill up?

Verify correctness of `setup` script

## Check license

These must match:
- `LICENSE.txt` file
- license entry in `SKILL.md` header

## Version update

Update version strings in:
- `SKILL.md`
- `scripts/gittoc_lib/__init__.py`
