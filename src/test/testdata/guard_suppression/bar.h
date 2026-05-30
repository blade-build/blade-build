#ifndef GUARD_SUPPRESSION_BAR_H_
#define GUARD_SUPPRESSION_BAR_H_

#include "guard_suppression/foo.h"

inline int bar() { return foo() + 1; }

#endif  // GUARD_SUPPRESSION_BAR_H_
