"""fluid_router — branchless one-example routing kernel (Python reference).

The expression in `route_packed` was AUTHORED by a program-synthesis engine
(organism_inf.sphere) and appears here verbatim, verdict `minimal in D∩I`.
It is not hand-written and has not been hand-simplified.

    route(F1, A1, Fq) == (Fq + A1 - F1) mod 16

Given one worked example -- case F1 was handled by action A1 -- it returns the
action for any new case Fq. The offset is never stored; it is recovered from
the worked example on every call, so the action vocabulary can be renumbered
without touching any code.
"""

__all__ = ["route", "route_packed", "pack"]
__version__ = "1.0.0"

_MASK = 0xFFFFFFFF


def _w32(v: int) -> int:
    """Wrap to int32, matching C compiled with -fwrapv."""
    return ((v + (1 << 31)) & _MASK) - (1 << 31)


def pack(F1: int, A1: int, Fq: int) -> int:
    """Pack a worked example and a query into one word."""
    return (F1 & 15) | ((A1 & 15) << 4) | ((Fq & 15) << 8)


def route_packed(x: int) -> int:
    """THE AUTHORED EXPRESSION, verbatim.

    Bits 12-31 of `x` are ignored and provably cannot influence the result.
    """
    x = _w32(x)
    return 15 & _w32(_w32(x >> 4) + _w32(_w32(x >> 8) - x))


def route(F1: int, A1: int, Fq: int) -> int:
    """The action for case `Fq`, inferred from the worked example F1 -> A1."""
    return route_packed(pack(F1, A1, Fq))
