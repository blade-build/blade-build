// qux.cc: include bar.h first (transitively pulls foo.h in via its guard-
// protected #include), then directly include foo.h. Under GCC/clang's
// multiple-include-guard optimization, the second #include is suppressed and
// produces no -H line, so depth-1 in qux.cc.incstk lists only bar.h.
// The source-scan supplement (#1171) makes the check see foo.h too.
//
// Also mis-quotes a system header: this should NOT land in direct_hdrs --
// the wrapper's awk strips absolute paths from the .incstk and the source-
// scan supplement is intersected with paths the compiler actually traversed,
// so system headers spelled either way (`"stdio.h"` or `<stdio.h>`) drop out.
#include "guard_suppression/bar.h"
#include "guard_suppression/foo.h"
#include "stdio.h"

// A dead include of a non-existent file -- the source scanner picks it up,
// but the compiler never opens it (#if 0 block), so it is NOT in the .incstk
// and the intersection drops it. Build doesn't break despite the file
// missing, which empirically proves the dead-branch contract.
#if 0
#include "guard_suppression/ghost.h"
#endif

int qux() { return foo() + bar(); }
