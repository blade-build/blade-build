// Heap-buffer-overflow read. AddressSanitizer must catch it under
// `blade test --sanitizer=address`, failing the test; a normal build reads
// garbage and returns 0 (passes). The runtime index defeats const-folding.
int read_at(const int* p, int i) { return p[i]; }

int main(int argc, char**) {
    int* a = new int[3];
    volatile int x = read_at(a, argc + 4);  // OOB index >= 5
    (void)x;
    delete[] a;
    return 0;
}
