# Measured against a frontier model on repositories neither side has seen

Five libraries, none of them in this repo's measured set and none used while the
transforms were written: `humanize`, `inflection`, `natsort`, `parse`, `wcwidth`.
Bugs injected by a seeded standard mutation-operator set — comparison
strictness, equality, off-by-one literals, additive and multiplicative operator
confusion, boolean literal flips, `and`/`or` confusion. **The bugs were not
chosen by hand and not chosen to suit the four acts.** Only mutations the
library's own suite actually catches were kept: 33 of 40 candidates survived
that filter.

Both sides were given the same information — the file containing the defect,
and the library's own suite as the oracle. The model side ran as a fresh
instance per bug, sandbox-locked, with no access to the injected-bug list.

## Headline

```
33 real bugs           this kernel      Opus 5 (fresh per bug)
  suite green            19/33              33/33
  byte-exact restore     17/33              27/33
  model tokens               0         ~1,300,000
  wall clock             2,507 s        (ran in parallel)
```

**Opus 5 wins on coverage, 33 to 19.** The claim that this kernel out-debugs a
frontier model is not supported and should not be made.

Two numbers go the other way and are worth stating precisely:

**Precision on commit.** Of the repairs each side made, the fraction that
restored the original line byte-for-byte rather than merely greening the suite:

```
  this kernel   17/19 = 89%
  Opus 5        27/33 = 82%
```

**Correct refusal.** On the six bugs outside the four acts (`==`↔`!=`, `*`↔`/`,
`and`↔`or`, `True`↔`False`) it refused all six rather than guessing. That is the
documented behaviour in the README's Honest Limits and it held on unseen code.

## Neither side can tell a real bug from a phantom

Seven of the original 40 mutations landed in code no test covers. They were
dropped from the corpus above, but what both sides did with them matters:

```
  Opus 5       claimed FIXED on 7/7, spending 806,938 tokens
               (the most expensive single run was 181,331 tokens — on a non-bug)
  this kernel  reported success on 7/7, in 1.3-4.1 seconds each
```

Both fabricate a repair when there is nothing to repair. The kernel's only
stopping condition is *a test passed*, and the test was already passing. Its
refusal behaviour is a **vocabulary** check, not a **premise** check — those are
unrelated capabilities and it has only the first.

Fix: assert the suite fails before searching, and return "no failing test —
nothing to repair." Three lines at the top of `repair()`.

## What a per-repository act dictionary buys

The four shipped acts are a demonstration, not a ceiling. The router infers the
kind→act mapping from one worked example, so the vocabulary can be extended
without touching `fluid_router.py`. Tested by having a frontier model author one
dictionary per repository from **two seed faults and the repo alone**, then
running it against that repo's other bugs, which it never saw.

```
  dictionary authoring cost, per repository       mean 139,924 tokens
      humanize 164,680 · natsort 154,951 · wcwidth 150,276
      inflection 128,189 · parse 101,526

  Opus 5 fixing one bug alone                          39,436 tokens
  BREAK-EVEN                                              3.5 bugs
```

On 23 held-out bugs, with the buggy line supplied (what any real deployment
has — you know which test failed and which frame it failed in):

```
  byte-exact      20/23 = 87%
  green-only       1
  no fix found     2        (both comparison-strictness)
  mean             10.4 s and 13 candidates per bug, 0 tokens
```

The dictionary is a **compile step**: pay once per repository, then the kernel
runs free forever. The model's cost scales with bug count; the dictionary's
does not.

## Localisation is the binding constraint, not vocabulary

The same dictionaries, searching the whole file instead of being given the line:

```
  byte-exact      10/23  (was 20/23)
  mean            1,582 s per bug  (was 10.4 s)  -- 152x slower
  hit a 4,000-candidate budget cap: 10 of 23
```

Every one of those 10 contains the true fix in its candidate set — 21 of 23
overall do. **Coverage is 91%; realised repair rate is limited entirely by
search order.** A richer dictionary makes this worse, not better: `parse` scored
0/6 blind and 6/6 localised.

The README already says *"Localisation is not solved here... on large files that
is the dominant cost."* This quantifies it: 152x, and it is now the only thing
standing between 87% and the shipped numbers. The fix is ranking candidates by
prior likelihood, or localising before enumerating — not a bigger budget.

## Three defects found in the measurement itself

Recorded because the first numbers were wrong and every correction moved in the
kernel's favour. Anyone rerunning this should expect to hit them.

1. **Stale bytecode suppressed correct repairs.** The harness rewrote source and
   re-ran pytest without clearing `__pycache__`. Python validates a `.pyc` on
   whole-second mtime plus size, and act 6's edits are same-size writes made
   milliseconds apart (`\2`→`\1`, `3601`→`3600`, `[2:]`→`[1:]`), so stale
   bytecode was re-imported and correct candidates scored as failures. Kernel
   score before fix 14/33, after 19/33. One case went from *refused after 185
   tries* to *exact at try 5*. **`repair()` in this repo was never affected** —
   it passes `-B` and clears `__pycache__` each iteration. Harnesses built on
   top of it are not automatically safe.

2. **A plugin conflict invalidated a whole library.** `pytest-benchmark`
   collides with `wcwidth`'s own `benchmark` fixture, so every run returned
   non-zero and the kernel scored 0/8 across ~3,500 wasted seconds. With
   `-p no:benchmark` it scores 3/3.

3. **Seven "bugs" were not bugs.** The same conflict made the selector count
   mutations as live that no test covers. Corpus corrected 40 → 33.

## The defensible claim

> A frontier model compiles a per-repository act dictionary once for ~140k
> tokens. This kernel then repairs 87% of that repository's mechanical
> single-line faults byte-exact, at zero tokens, in ~10 seconds each — given
> localisation. Break-even at 4 bugs.

Not "beats a frontier model." **Makes one cheap** — which is the more valuable
claim and is the one the data supports.

What it does not reach, and no act dictionary will: wrong variable passed,
missing guard, wrong API call, misunderstood loop intent. Those are not regex
substitutions. The open question this benchmark does not answer is what
fraction of a given codebase's real defects are mechanical single-line faults.

## Licence

This file and `benchmark/` are part of fluid-router and are licensed
**AGPL-3.0-or-later**, like the rest of the repository.

The five libraries measured (`humanize`, `inflection`, `natsort`, `parse`,
`wcwidth`) are third-party packages fetched from PyPI at their own licences and
are not vendored here — `benchmark/pick.py` downloads them. `benchmark/bugs.json`
records single mutated lines from those packages solely to identify the injected
faults.
