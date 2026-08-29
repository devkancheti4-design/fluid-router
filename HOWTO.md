# A fault family is a shape

Show it one full example of a shape and it repairs every future instance of that
shape, in code it has never seen, for zero tokens.

```
                         result   candidates   runnable here?
leakage                   7 / 7      4-5       tests/test_leakage.py
races, simple             5 / 5      2         tests/test_concurrency.py
races, complex            5 / 5      1         no — harness not in this repo
four hard classes         9 / 9      2-9       no — harness not in this repo
token removal             3 / 3      10-27     no — real scikit-learn/einops commits
```

Two of the five reproduce from a clean clone with no dependencies. The other
three were measured with a harness that is not in this repo; the corpora they
ran against are, under `benchmark/`. Numbers you cannot re-run yourself should
be read as claims, not proofs, and they are marked as such above.

Random edits from the same file, same oracle, same search loop, **500× the
budget**: 0 / 9 at 2,000 candidates each. The acts carry the information, not
the search.

---

## How it works

Three pieces. Two you write once; one your project already has.

```
observe(line)    which fault shapes this line could exhibit      you write it
acts(line, act)  candidate repairs for that shape               derived from your example
a failing test   fails with the bug, passes without it          your project has it
```

Between them sits the router, which is the whole decision kernel:

```c
route(F1, A1, Fq) == (Fq + A1 - F1) mod 16
```

Three integers in, one out. It never sees code. You give it **one** worked
example — *"fault kind F1 is repaired by act A1"* — and it addresses every other
kind for free. That is its entire job: there is no kind→act table, so there is
no table to go stale when you add an act.

The loop is unremarkable and that is the point:

```
for each line:
    for each shape observe() sees on it:
        act  = route(one_example, shape)
        for each candidate acts() offers:
            write it, run the test, keep it if green
```

**The router indexes. The acts repair.** Almost every misreading of the numbers
below comes from swapping those two.

---

## Writing the example

This is the part that decides whether it works. Everything else is mechanical.

### 1. Give it the whole unit, not a diff line

A one-line diff carries no conditions, and the conditions are what stop the act
firing everywhere.

```python
# BAD — a diff line
-  self.data = rows
+  self.data = list(rows)
#  → 3,892 findings across 17 repos. All noise.

# GOOD — the whole unit, showing why it is a bug
class Box:
    def __init__(self, items):      # items is a caller-supplied parameter
-       self.items = items          # stored by reference
+       self.items = list(items)
    def add(self, v):
        self.items.append(v)        # and mutated later, so the aliasing bites
#  → 10 findings. One is a genuine aliasing bug in scikit-learn.
```

Measured, narrowing one condition at a time: **4,012** on the shape alone →
**984** once the right-hand side must be a parameter → **10** once the attribute
must also be mutated.

### 2. Separate the pattern from the scenery

Every feature of your example is either the pattern or incidental. Keeping the
incidental ones is as fatal as keeping none.

| feature of the example | verdict | findings if kept literally |
|---|---|---|
| the RHS is a parameter | pattern — keep | narrows correctly |
| the attribute is mutated | pattern — keep | **10** |
| the mutator is `.append` | scenery — drop | 0 |
| the function is `__init__` | scenery — drop | 0 |

Four of the ten correct findings are reached through `__setitem__`, a mutator
the example never showed. Generalise to *any mutator, any function whose
parameter it is*. Nothing automates this call; a human makes it once per act.

### 3. Know whether your fix is structural

This tells you, before writing anything, whether one example can generalise.

```
STRUCTURAL   every token the fix introduces is already on the broken line,
             or is a generic construct (list, int, with, lock, ravel)
             → one example covers unbounded future instances

CONTENT      the fix introduces a token from outside — cv_results_, dim=,
             'licenses', 195
             → one example covers exactly one bug
```

Across 48 real ML bugs, **no content fact repeated even once**. That is why
examples accumulate for structural shapes and cannot for content ones.

### 4. Order `observe()` most-specific-first

`act = kind + offset` is a translation — it shifts every kind equally. If a line
exhibits two shapes, whichever `observe()` lists first wins, **for every possible
worked example**. No choice of example fixes it.

```
'k += 1' exhibits kind 1 (has a digit) and kind 4 (a lone accumulate)

  generic first    0 of 16 offsets correct   → k += 0, suite green, wrong
  specific first  11 of 16 offsets correct   → the spurious line deleted
```

### 5. Check your test actually fails

A test that passes with the bug present is not an oracle, and nothing can work
against one. Run it three to five times and require it to fail every time.

```
plain  self.n = self.n + v  race  →  failed 0 of 5 runs   NOT AN ORACLE
read, yield, write          race  →  failed 5 of 5 runs   usable
```

---

## A worked example, end to end

The leakage act, in full. The example:

```python
def standardize(xs, n_train):
-   mu = mean(xs)                    # statistic over the WHOLE array
-   sd = stdev(xs)
+   mu = mean(xs[:n_train])          # restricted to the train slice
+   sd = stdev(xs[:n_train])
    z = [(v - mu) / sd for v in xs]
    return z[:n_train], z[n_train:], mu
```

The act taken from it hardcodes no statistic, no array name, and no split
variable — the split variable is recovered from the function's own signature by
finding which parameter is used as a slice bound in the body. It then repairs:

```
median imputation                  SOLVED  5 candidates
variance-threshold selection       SOLVED  5
whitening factor from stdev        SOLVED  5
mean centring only                 SOLVED  5
per-column max used for clipping   SOLVED  4
min used for shifting              SOLVED  4
L2 normalisation constant          SOLVED  4
```

Seven statistics across three call forms — `xs.stat(...)`, `stat(xs)`,
`mod.stat(xs)` — where the example showed one form and two statistics.

---

## What it is

It works on the shapes you have shown it. That is the whole specification, and
it is a complete one.

It does not guess. Given a shape it has not been shown, it emits **zero
candidates** and stops — not a wrong answer. Given a bug whose fix needs a fact
from outside the file, the same.

Two numbers worth keeping next to the rest. Bugs it solved cost a frontier model
**more** than bugs it refused — 41,629 against 37,988 tokens — so there is no
relationship between what is hard for a model and what an act can express. And
this repo's mutation benchmark is **55% structural** against **31%** for real ML
work, so any shape-based tool scores about 1.8× better here than on a working
codebase. Both are stated so you do not have to find them.

---

## Reproduce

```bash
python3 tests/test_leakage.py        # one example → 7 leakage variants
python3 tests/test_concurrency.py    # one example → 5 race shapes
python3 tests/test_from_examples.py  # acts derived from example pairs
python3 tests/test_multiline.py      # delete/insert acts, and act ordering
python3 tests/test_unseen.py         # 5/5 exact on unseen library idioms
python3 tests/test_law.py            # the routing law, re-checked exhaustively
```

No dependencies. Every test runs in seconds and prints what it did.
