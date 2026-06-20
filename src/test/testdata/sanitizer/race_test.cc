// Data race on a shared counter. ThreadSanitizer must catch it under
// `blade test --sanitizer=thread`, failing the test; a normal build races
// benignly and passes.
#include <pthread.h>
static int shared = 0;
static void* worker(void*) {
    for (int i = 0; i < 100000; ++i) shared++;
    return 0;
}
int main() {
    pthread_t a, b;
    pthread_create(&a, 0, worker, 0);
    pthread_create(&b, 0, worker, 0);
    pthread_join(a, 0);
    pthread_join(b, 0);
    return 0;
}
