# Example: zero-token single-line repair

`kdebug.py` wires the router into a complete repair loop:

    mechanical observer  ->  fluid-router kernel  ->  mechanical transform  ->  tests confirm

The only fact supplied is `WORKED_EXAMPLE = (0, 5)`. Every other fault-to-act mapping
is inferred by the kernel, which is why the act codes can be renumbered arbitrarily
without editing a line of code.

    python3 kdebug_demo.py

Scope: single-line faults in four kinds — comparison strictness, off-by-one integer
literal, swapped binary operands, flipped additive operator. See the honest limits
section of the top-level README for measured coverage on real repositories.
