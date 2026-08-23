/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Copyright (C) 2026 devkancheti4-design
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or (at your
 * option) any later version. It is distributed WITHOUT ANY WARRANTY; without
 * even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
 * PURPOSE. See the GNU Affero General Public License for more details.
 * You should have received a copy of the license along with this program.
 * If not, see <https://www.gnu.org/licenses/>.
 */
/* fluid_router.h — branchless one-example routing kernel.
 *
 * The expression in fr_route() was AUTHORED by a program-synthesis engine
 * (organism_inf.sphere) from input/output pairs, an operator budget and an
 * intent cut. It appears here VERBATIM. It was not hand-written and has not
 * been hand-simplified. The engine's verdict on it was:
 *
 *     minimal in D∩I     — no smaller expression exists in the supplied space
 *
 * WHAT IT DOES
 *   Given one worked example — "case F1 was handled by action A1" — and a new
 *   case Fq, it returns the action for Fq. The mapping is a relabelling of a
 *   4-bit vocabulary, and the offset is never stored: it is recovered from the
 *   worked example every call. Renumber your action codes and nothing changes.
 *
 *     route(F1, A1, Fq) == (Fq + A1 - F1) mod 16
 *
 * PACKING
 *   bits 0-3    F1   the case in the worked example
 *   bits 4-7    A1   the action that handled it
 *   bits 8-11   Fq   the new case to route
 *   bits 12-31  ignored — provably cannot influence the result
 *
 * BUILD REQUIREMENT
 *   Compile with -fwrapv. The expression is only the function it was verified
 *   to be under wrapping signed arithmetic.
 *
 * VERIFIED
 *   all 2^32 int32 inputs          0 mismatches vs the reference
 *   each action 0..15 occurs       exactly 2^28 times (uniform partition)
 *   bits 12-31 influence result    never
 *   emitted code (arm64 -O2)       4 instructions: lsr, sub, add, and
 */
#ifndef FLUID_ROUTER_H
#define FLUID_ROUTER_H

#include <stdint.h>

/* The authored expression, verbatim. */
static inline int32_t fr_route_packed(int32_t x)
{
    return 15 & ((x >> 4) + ((x >> 8) - x));
}

static inline int32_t fr_pack(int32_t F1, int32_t A1, int32_t Fq)
{
    return (F1 & 15) | ((A1 & 15) << 4) | ((Fq & 15) << 8);
}

/* route(F1, A1, Fq) — the action for case Fq, inferred from the single
 * worked example (F1 -> A1). */
static inline int32_t fr_route(int32_t F1, int32_t A1, int32_t Fq)
{
    return fr_route_packed(fr_pack(F1, A1, Fq));
}

#endif /* FLUID_ROUTER_H */
