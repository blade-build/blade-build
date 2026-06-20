// Signed integer overflow (undefined behavior). UndefinedBehaviorSanitizer
// must catch it under `blade test --sanitizer=undefined` (made fatal), failing
// the test; a normal build wraps around silently and passes. The runtime base
// value defeats const-folding.
#include <climits>
int overflow(int x) { return x + 1; }

int main(int argc, char**) {
    int base = INT_MAX - (argc - 1);   // == INT_MAX at runtime
    volatile int r = overflow(base);   // signed-integer-overflow
    (void)r;
    return 0;
}
