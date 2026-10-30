/* Quiet Mode spinner (spin.sh): keeps one core from sleeping.
 *   nebulae_spin [yield]  only the "yield" hint in a tight loop: no memory
 *                         accesses, the least current (lowest hiss), but the
 *                         biggest step up when real work comes
 *   nebulae_spin work     the same even work over and over (arithmetic and a
 *                         4 KB table, stays in the L1 cache): more current,
 *                         closer to real work (smaller step), still even
 * The ear decides (noise_test.sh "spin=yield|work|shell[:cores]"). */
#include <string.h>

static volatile unsigned table[1024];

int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "work") == 0) {
        unsigned i = 0, acc = 1;
        for (;;) {
            acc = acc * 1664525u + table[i & 1023];
            table[i & 1023] = acc;
            ++i;
        }
    }
    for (;;) __asm__ volatile("yield");
}
