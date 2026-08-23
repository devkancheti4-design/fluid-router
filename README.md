# fluid-router

A four-operator branchless kernel that infers a whole relabelling from **one worked
example**.

```c
15 & ((x >> 4) + ((x >> 8) - x))
```

Give it one fact — *case `F1` was handled by action `A1`* — and it returns the action
for any new case `Fq`:

```
route(F1, A1, Fq) == (Fq + A1 - F1) mod 16
```

The offset is never stored. It is recovered from the worked example on every call, so
you can renumber your action codes freely and no code changes. A lookup table is wrong
on 15 of the 16 possible renumberings; this is wrong on none.

## Provenance

**The expression was authored by a program-synthesis engine**
(`organism_inf.sphere`) from input/output pairs, an operator budget and an intent cut.
It appears in this repository **verbatim** — not hand-written, not hand-simplified.
The engine's verdict was `minimal in D∩I`: no smaller expression exists in the space it
was given.

Everything else here — the packing, the tests, the example application — is ordinary
hand-written code around it.

## Use

```python
from fluid_router import route

FLIP_STRICTNESS, REDUCE_LITERAL, SWAP_OPERANDS, FLIP_ARITHMETIC = 5, 6, 7, 8

# the one thing you tell it: fault kind 0 is repaired by act 5
act = route(0, FLIP_STRICTNESS, observed_fault_kind)
```

```c
#include "fluid_router.h"
int32_t act = fr_route(0, 5, observed_fault_kind);   /* compile with -fwrapv */
```

**Build requirement: `-fwrapv`.** The expression is only the function it was verified to
be under wrapping signed arithmetic.

## What is verified

Run `python3 tests/test_law.py` and `cc -O2 -fwrapv tests/test_law.c && ./a.out`.

| property | result |
|---|---|
| all 2³² int32 inputs vs the reference | **0 mismatches** |
| each action 0–15 occurs | exactly 2²⁸ times — a uniform partition |
| bits 12–31 influence the result | never |
| 16 renumberings × 16 example cases | 4096/4096 |
| 14 offsets never supplied to the engine | 3584/3584 |
| emitted code (arm64, `-O2 -fwrapv`) | 4 instructions: `lsr, sub, add, and` |

Twelve algebraic properties are checked, including identity (`route(F1,A1,F1) == A1`),
translation invariance (absolute codes carry no information, only their difference),
and composition (`route(o₂, route(o₁, q)) == q + o₁ + o₂`).

It is also checked to be **not a lookup table**: every case maps to 16 different actions
across the 16 offsets, so no table keyed on the query alone can reproduce it.

## Worked application: a zero-token repair router

`examples/` contains a single-line bug repair pipeline where this kernel is the only
decision-maker — a mechanical observer names the fault, the kernel picks the act, a
mechanical transform applies it, the test suite confirms. No language model anywhere.

Measured on synthetic modules, with act codes renumbered so a fixed table fails:

| benchmark | result | cost |
|---|---|---|
| 300 generated modules | 300/300 exact | 0 tokens, 3.8 s |
| the same 300 × all 16 renumberings | **4800/4800 exact** | 0 tokens, 62 s |
| 10 held-out modules written after the transforms were frozen | 10/10 exact | 0 tokens |

For comparison on the same 300 bugs, twelve parallel frontier-model agents also scored
300/300 — at **452,737 tokens and 62 s** against zero tokens and 3.8 s.

## Generalisation to unseen repositories

`UNSEEN.md` records an outside measurement on idioms from libraries in none of the
repositories above — funcy-style slicing, a chunking loop, cachetools-style TTL
arithmetic, a sortedcontainers-style bisect bound, and a diff helper.

    python3 tests/test_unseen.py        # 10.3 s, no dependencies

    repaired 5/5   EXACT 5/5   0 tokens

That corpus also found a real defect in the example pipeline: an act that decrements a
loop bound can make a candidate non-terminating, and the repair loop executed candidates
with no timeout — it hung for 595 s. `repair()` now bounds every candidate
(`CANDIDATE_TIMEOUT`), and a candidate that will not terminate is treated as a failed
candidate.

## Honest limits

**Measured on three real repositories** (cachetools, sortedcontainers, boltons; 1,150
tests green at HEAD) with a standard AST mutation operator set chosen without reference
to what this pipeline can repair:

- The four-act vocabulary covers **63%** of live mutants. Boolean swaps, `not` removal
  and multiplicative flips have no act and are never repaired — correctly, since nothing
  exists to route to.
- Within its vocabulary it exactly repaired **9 of 13** decidable cases.
- **Zero silently wrong repairs across all 27 live mutants.** Nothing greened a suite
  with an edit differing from HEAD.
- Every remaining in-vocabulary miss was traced to the hand-written transform layer
  (`re.search(r"\d+")` takes the *first* literal on a line, which is wrong when a line
  has several), **not to the router — which chose the correct act in every case**.

**What it cannot do.** It generalises over translations of the action vocabulary and
over case codes it never saw. It does **not** handle an arbitrary permutation of the
action codes — and neither can anything else, from one example: a single pair is
consistent with 15! relabellings, exactly one of which is a translation. Recovering an
arbitrary permutation needs all 16 pairs, which is the lookup table itself.

**Localisation is not solved here.** The example pipeline finds the buggy line by trying
candidates against the test suite. On large files that is the dominant cost.

## Licence

**GNU Affero General Public License v3.0** (AGPL-3.0-or-later). See `LICENSE`.

AGPL is copyleft and its network clause (section 13) applies: if you run a modified
version of this software so that users interact with it over a network, you must offer
those users the corresponding source of your modified version. If that does not suit
your use, ask about other terms.
