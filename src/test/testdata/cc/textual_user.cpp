// Exercises cc_library.textual_hdrs: the .cc fragment below is #included
// textually (it is not a standalone translation unit).

namespace blade_test {

static const int kNumbers[] = {
#include "cc/numbers_data.cc"
};

unsigned num_numbers() {
    return sizeof(kNumbers) / sizeof(kNumbers[0]);
}

}  // namespace blade_test
