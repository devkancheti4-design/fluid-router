# A dictionary per codebase, measured on that codebase's real bugs

`../../BENCHMARK.md` measures mechanically-injected mutations. This directory
measures something harder and more honest: **real bug-fix commits from real
project history**, with a repair dictionary trained on *that same project's*
earlier bugs and scored on its later ones.

The question is the one a working engineer asks: *if I feed it the mistakes my
team actually keeps making, how much of my debugging does it cover?*

## Method

`mine.py` walks the git history of four Python libraries — `humanize`, `parse`,
`inflect`, `funcy` — and keeps commits that:

- have a message indicating a fix (`fix`, `bug`, `incorrect`, `wrong`, `broken`, `error`)
- modify **exactly one** non-test `.py` file
- replace **exactly one** line with one line

That yields 58 real one-line bug fixes as the maintainers actually wrote them.
Nothing is synthesised and nothing is chosen to suit the four shipped acts.

Each repository's bugs are split 55/45. A frontier model reads **only that
repository's seed bugs** — never the held-out ones, never the repo source, never
its history — and writes a dictionary. `score.py` then asks a single exact
question per held-out bug:

> does `candidates(broken_line)` contain the maintainer's actual fixed line?

The router is untouched throughout. The kind→act mapping is never written into
any dictionary; it is inferred from the one shipped worked example.

## Result

```
                held-out   recovered
  inflect          6          5    83%
  humanize         9          6    67%
  funcy            9          4    44%
  parse            4          1    25%
  ------------------------------------
  all             28         16    57%
  code bugs only  21         13    62%      (excluding docstring/typo fixes)
```

**Compared against the same measurement with one general dictionary trained on a
mix of all four repositories: 16/39 = 41%.**

Specialising to a single codebase is worth **+21 points**. Same kernel, same
single worked example — only the training examples changed, from "bugs in
general" to "the mistakes this project keeps making." That is the whole
argument for a per-team dictionary, and it holds.

## What this number is, and is not

**It is a ceiling.** The test asks whether the correct fix appears *anywhere* in
the generated candidate set, with the buggy line already supplied. Median
candidates per line: **13,708**. Retrieving the right one from that is a separate
and unsolved problem — see the localisation section of `../../BENCHMARK.md`,
where the same gap costs 152x wall clock.

**It is not 100%, and cannot be.** The recovered fixes are things a text
transform can express — wrapping in a call, adding an argument, anchoring a
regex, adding a conjunct:

```
- return get_translation().ngettext(message, plural, num)
+ return get_translation().ngettext(message, plural, int(num))

- long_description=open('README.rst').read(),
+ long_description=open('README.rst', encoding="utf-8").read(),

- (r"(%s)" % A_explicit_an, "an"),
+ (r"^(%s)" % A_explicit_an, "an"),
```

The misses need information that is **not present on the broken line**:

```
- if isinstance(seq, Sequence):
+ if isinstance(seq, Sequence) and not isinstance(seq, xrange):   a symbol from elsewhere

- u = int(float("." + u) * 1000000)
+ u = int(u.ljust(6, "0")[:6])                                    a different algorithm

- raise ValueError('type %r not recognised' % type)
+ raise ValueError('format spec %r not recognised' % type)        domain knowledge

- __version__ = "1.21.1"
+ __version__ = "1.22.0"                                          unknowable from the line
```

No enumeration reaches these. Enlarging the dictionary raises the candidate
count, not the ceiling.

## The ladder, all on real bugs

```
  16%   single-token substitutions -- their share of all real one-line fixes
  41%   one general dictionary across four unrelated codebases
  62%   one dictionary per codebase, trained on its own bug history
```

The defensible claim is the third line: **encode a team's recurring mistakes and
this kernel covers roughly three in five of them at zero tokens**, after a
one-time authoring cost of roughly 124,000 tokens per repository (measured on
one of the four).

`parse` at 1/4 is the reminder that four held-out bugs is not a sample. These
per-repository figures are indicative; only the pooled 13/21 is worth quoting.

## Reproduce

```bash
python3 benchmark/domain/mine.py humanize parse inflect funcy   # needs the four repos cloned
python3 benchmark/domain/score.py
```

`dictionaries/<repo>.py` is each authored dictionary as written, and
`dictionaries/<repo>.seeds.txt` is exactly what its author was shown.
