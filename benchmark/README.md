# Reproducing BENCHMARK.md

`../BENCHMARK.md` holds the results. This directory holds the harness.

```
inject.py          seeded standard mutation operators
pick.py            keep only mutations the library's own suite catches
run_router.py      the four shipped acts, whole-file line search
body2.py           a hand-extended eight-act dictionary
run_ext.py         body2 over the same corpus
run_authored.py    per-repo model-authored dictionaries, whole-file search
run_loc.py         the same dictionaries with the buggy line supplied
verify2.py         independent re-verification of the model side
dictionaries/      the five per-repo dictionaries, as authored
```

Results as JSON: `final.json` (shipped acts), `ext_results.json` (hand-extended),
`authored_results.json` (blind search), `loc_results.json` (localised),
`bugs.json` + `valid.json` (the corpus and which entries are genuine),
`tok.json` + `tok_auth.json` (model token costs).

Setup, then run in order:

```bash
python3 -m venv .venv && .venv/bin/pip install pytest pytest-timeout pytest-mock hypothesis freezegun pytest-cov
# fetch the five sdists into libs/, install each editable
.venv/bin/python pick.py 8
.venv/bin/python run_router.py
```

Two environment traps, both of which cost real measurements the first time:

- **`pytest-benchmark` collides with `wcwidth`'s own `benchmark` fixture.**
  Every run returns non-zero. Pass `-p no:benchmark`.
- **Clear `__pycache__` and set `PYTHONDONTWRITEBYTECODE=1`.** Same-size source
  rewrites inside one second re-import stale bytecode and score correct
  candidates as failures.
