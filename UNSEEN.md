# Generalisation to unseen repositories

The top-level README measures coverage on cachetools, sortedcontainers and
boltons. This file is an outside measurement on idioms from libraries in
**none** of those: funcy-style slicing, a chunking loop, cachetools-style TTL
arithmetic, a sortedcontainers-style bisect bound, and a diff helper.

    python3 tests/test_unseen.py        # 10.3 s, no dependencies

## Result

```
case                 result     exact?         tries  secs
funcy_slice_offset   REPAIRED   YES            1      0.03
chunk_loop_bound     REPAIRED   YES            2      0.07
ttl_additive         REPAIRED   YES            2      0.07
bisect_strictness    REPAIRED   YES            5      10.12
delta_operand_swap   REPAIRED   YES            1      0.03

repaired 5/5   EXACT 5/5   10.3 s   0 tokens
```

**Exact, not suite-green.** The check is byte equality with the intended
source, which is strictly stronger than a passing suite and is what catches a
repair that greens a weak oracle with the wrong edit. Across this corpus and an
earlier six-case one, the record is **9 of 9 exact in-vocabulary repairs, with
zero silently-wrong repairs**, and correct refusals on the two out-of-vocabulary
faults tried (boolean negation, multiplicative flip).

## The defect this measurement found

`examples/kdebug.py:64` runs each candidate with no timeout:

```python
subprocess.run(["python3", "-B", testname], cwd=w, capture_output=True)
```

On `chunk_loop_bound`, act 6 decremented a literal such that a loop counter
advanced by zero — a **non-terminating candidate**. The pipeline waited for it
indefinitely: the first run of this corpus **hung for 595 seconds and produced
nothing**. With a 5 s per-candidate bound the identical corpus completes in
10.3 s at 5/5.

`tests/test_unseen.py` installs that bound itself so the suite terminates. It
belongs in `repair()`; until it is there, the guard documents the defect rather
than hiding it. A repair loop that executes arbitrary mutated code must bound
execution — mutation into an infinite loop is not an edge case, it is a routine
consequence of an off-by-one act applied to a loop variable.

## What this does and does not establish

- **Does:** within its four-act vocabulary, the router chooses correctly on code
  it has never seen, and the pipeline produces the exact intended source.
- **Does not:** say anything about the ~37% of live mutants outside that
  vocabulary. Those are refused, not repaired, which is the correct behaviour
  and is measured in the top-level README.
- **Does not:** solve localisation. `bisect_strictness` took 5 candidate
  verifications and 10.1 s of the 10.3 s total — the search over lines, not the
  routing decision, is the entire cost. The router itself runs at ~656 ns in
  Python and four arm64 instructions in C, i.e. about 1/44,000 of a single
  candidate check.
