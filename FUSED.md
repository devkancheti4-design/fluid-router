# fluid-router + fluid-router2

Two kernels that answer different questions and compose in one order.

```
fluid-router2   is my MEASUREMENT lying to me, and which way?
fluid-router    given a sound measurement, which edit fixes this line?
```

Run fr2 first. It gates; fr1 repairs. Everything below was measured, and every
number that moved is stated next to the one that did not.

---

## fluid-router works from full examples, and generalises

```
  corpus                                  supplied         result
  concurrency, 5 different shapes         ONE example      5/5
  novel bugs in unseen code               3 examples       3/3 byte-exact
  hard categories: conc/mem/scale/arch    same-class ex.   9/9
  novel variants, acts left unchanged     nothing new      4/6
  real ML source bugs (content-bearing)   24 examples      0/24
```

The concurrency row is the clean case. One example — a counter whose method body
performs an unguarded read-modify-write, wrapped in `with self.lock:` — yields an
act that matches the SHAPE. It then repairs a dict update, a list rebuild, a
compare-and-set and a two-field invariant, none of which it was written against.
See `tests/test_concurrency.py`.

The last row is the boundary, and it is not about difficulty. Those fixes need a
token that is not on the line: `tuple`, `cv_results_`, `dim=`, `with`. An act
rearranges what is present; it cannot invent a name it was never given.

**The dividing line is measurable in advance.** A fix is *structural* if every
token it introduces is already on the broken line or is a generic Python
construct; otherwise it is *content-bearing*.

```
                                structural      content-bearing
  real ML bugs (einops+sklearn)  15/48 = 31%     33/48 = 69%
  real bugs (4 general libs)     23/58 = 40%     35/58 = 60%
  the mutation benchmark         18/33 = 55%     15/33 = 45%
```

One example covers a whole structural class. Content-bearing fixes need the fact
itself, and across 48 real ML bugs **no content fact repeated even once** — so
one example there buys exactly one bug. Note the third row: this repo's own
mutation benchmark is 55% structural against 31% for real ML work, which is the
bias in it, quantified.

---

## Fusing fr2 in outperforms fr1 alone

```
  axis                          fr1 alone      fused           what changed
  phantom bugs (7)              7/7 WRONG      7/7 blocked     corruption -> refusal
  benchmark gate (33 genuine)   --             33/33 allowed   0 false refusals
  ML pipeline jobs (24)         no concept     21/24           a class fr1 cannot see
  mutation benchmark (33)       19/33          19/33           unchanged
  concurrency (5)               5/5            5/5             unchanged
  hard categories (9)           9/9            9/9             unchanged
```

**Two rows move, and they are the two that mattered.**

*The phantom bugs.* Seven mutations landed in code no test covers, so the suite
stayed green with the fault present. fluid-router alone reported success on all
seven, having edited an unrelated line — once a module reference 282 lines from
the fault. fr2 names every one `FOLDED`: *the harness scores a right and a wrong
implementation the same.* All seven blocked.

*The gate costs nothing.* Over the 33 genuine bugs it allows 33, including all 19
fluid-router actually repairs. **Zero false refusals.** A gate that protects you
by refusing everything is worthless; this one is not that.

*A class fr1 has no representation for.* fr2's six lanes are ML pipeline
failures, not source faults:

```
  CIRCULAR    the feature IS the label            target leakage
  DEGENERATE  the posed targets take one value    single-class split
  TRUNCATED   exact on posed, wrong on real       train/deploy gap
  EVALUATOR   grader != machine semantics         wrong metric
  FOLDED      right and wrong score the same      metric cannot discriminate
```

On 24 real sklearn pipeline jobs — every observation bit measured by running the
job, the law never shown the truth column — **21/24 named correctly, and 24/24
given correct bits.** All three misses were threshold constants in the measuring
body, not the dispatch.

The leakage case is the one to look at. A random forest with the label pasted
into `X` reports **1.000 accuracy** and truly scores **0.483** — worse than a
coin. Caught in all four instances, named `TRUNCATED -> CIRCULAR`, both faults
handled in sequence by `ADVANCE`.

---

## The precise claim

> fr2 does not repair more code. It stops fr1 answering when the question is
> unanswerable, and it covers a bug class fr1 has no representation for.
> **It outperforms on correctness and on class coverage, not on repair count.**

---

## What neither reaches

- **Content-bearing fixes.** 60–69% of real bugs. No act enumerates a fact it was
  never told, and those facts do not repeat.
- **fr2 finds nothing on its own.** It routes observations a body has already
  made. Deciding to run the suite on a known-good variant, or to sample the real
  domain, is still the body's job — and in the ML pipeline run, three of three
  errors were the body's thresholds.
- **CIRCULAR is named, never repaired.** Drop the leaking feature and there is
  nothing left. Diagnosis is not repair.

## Reproduce

```bash
python3 tests/test_concurrency.py     # one example -> 5 shapes
python3 tests/test_from_examples.py   # acts derived from example pairs
python3 tests/test_multiline.py       # delete/insert acts, and act ordering
cc -O2 -o checklaws verify/verify.c && ./checklaws     # in fluid-router2
```
