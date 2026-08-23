/* Complete-domain proof of the routing law over all 2^32 int32 inputs.
 * Build: cc -O2 -fwrapv -o test_law test_law.c   (-fwrapv is REQUIRED) */
#include <stdint.h>
#include <stdio.h>
#include <time.h>

#include "../fluid_router.h"
#define law fr_route_packed

int main(void) {
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    uint64_t wrong = 0, first_bad = 0; int have = 0;
    uint64_t hist[16] = {0};
    uint32_t u = 0;
    do {
        int32_t x = (int32_t)u;
        int F1 =  x        & 15;
        int A1 = (x >> 4)  & 15;
        int Fq = (x >> 8)  & 15;
        int want = ((Fq + A1 - F1) % 16 + 16) % 16;
        int got  = law(x);
        if (got != want) { if (!have) { first_bad = u; have = 1; } wrong++; }
        hist[got & 15]++;
        u++;
    } while (u != 0);

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double sec = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;

    printf("COMPLETE DOMAIN 2^32 = 4,294,967,296 inputs\n");
    printf("  mismatches vs (Fq + A1 - F1) mod 16 : %llu\n", (unsigned long long)wrong);
    if (have) printf("  first bad input                     : 0x%08X\n", (unsigned)first_bad);
    printf("  swept in %.2f s (%.0f M/sec)\n", sec, 4294.967296 / sec);

    printf("  output range check: ");
    int lo_ok = 1;
    for (int i = 0; i < 16; i++) if (hist[i] != (1ULL << 28)) lo_ok = 0;
    printf("%s (each act 0..15 occurs exactly 2^28 times: %s)\n",
           lo_ok ? "UNIFORM" : "NON-UNIFORM", lo_ok ? "yes" : "no");

    /* independence of bits 12..31: law(x) must equal law(x & 0xFFF) everywhere */
    uint64_t dep = 0;
    for (uint64_t k = 0; k < (1ULL << 32); k += 9973) {
        int32_t x = (int32_t)(uint32_t)k;
        if (law(x) != law((int32_t)((uint32_t)k & 0xFFF))) dep++;
    }
    printf("  bits 12..31 influence result        : %llu of %llu sampled\n",
           (unsigned long long)dep, (unsigned long long)((1ULL << 32) / 9973 + 1));
    return wrong != 0;
}
