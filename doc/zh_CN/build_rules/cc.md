# C/C++ 构建规则

C/C++ 的编译过程分为三个阶段：预处理、编译（将预处理后的源文件转换为 `.o` 文件）、链接（将 `.o`、`.a` 链接为可执行文件或动态库）。各阶段使用各自的编译器选项。

## 源语言

`srcs` 接受 C（`.c`）、C++（`.cc`/`.cpp`/`.cxx`）、汇编（`.s`/`.S`/`.asm`），以及
Objective-C / Objective-C++（`.m` / `.mm`）。Objective-C(++) 走相同的编译规则——
clang/gcc 驱动按扩展名自动判定语言——`.mm` 按 C++ 处理（用 `cxxflags`/`extra_cxxflags`）。
链接 Apple framework 用 `extra_linkflags`，例如 `extra_linkflags=['-framework', 'Foundation']`。
MSVC 工具链不支持 Objective-C，因此在 Windows 上要把 `.m`/`.mm` 从 `srcs` 里排除掉
（在 BUILD 里用 `blade.cc_toolchain` 条件判断）。

## 第三方库

除了从源码构建依赖，C/C++ 目标还可以链接预编译的系统库（`#name`，如 `#pthread`），
以及通过 `vcpkg#<port>:<lib>` 依赖使用 [vcpkg](https://github.com/microsoft/vcpkg)
管理的第三方包。完整说明见[使用 vcpkg 包](vcpkg.md)。

## C/C++ 通用属性

### `warning`：string = ['yes', 'no']

控制是否屏蔽全部编译警告。

**示例：** `warning='no'`
**默认值：** `'yes'`（通常无需显式书写）

### `defs`：string[] = []

用户自定义的预处理宏。

**示例：** `defs=['_MT']`；带值的宏可写作 `defs=['A=1']`。
**说明：** 仅对当前目标生效，不会透传给依赖该目标的其他目标。

### `incs`：string[] = []

头文件搜索路径。

**示例：** `incs=['poppy/myinc']`
**最佳实践：** 建议在源代码中使用完整的 include 路径，而非依赖额外的搜索路径。`incs` 一般只用于集成第三方库。

### `optimize`：string[] = []

编译器优化选项。

**示例：** `optimize=['-O3']`（默认为 `['-O2']`）
**设计原因：** `optimize` 之所以从 `extra_cppflags` 中单独拆出，是因为它在 debug 模式下需要被禁用，以保留可调试性。对于性能敏感、一般无需调试的成熟库（例如 hash、压缩、加解密等），可通过 `always_optimize = True` 使其始终开启优化。

### `extra_cppflags`：string[] = []

额外的编译选项，应用于**所有** C 系源文件（C、C++ 和汇编）。

**示例：** `extra_cppflags = ['-Wno-format-literal']`
**说明：** 常用选项（如 `-g`、`-fPIC` 等）Blade 已内置，该参数应尽量少用。

### `extra_cflags` / `extra_cxxflags` / `extra_asflags`：string[] = []

在 `extra_cppflags` 之外，仅应用于**单一源语言**的额外编译选项：

- `extra_cflags` — C 源文件（`.c`）
- `extra_cxxflags` — C++ 源文件（`.cc`、`.cpp`、`.cxx`）
- `extra_asflags` — 汇编源文件（`.s`、`.S`、`.asm`）

当某个选项只对一种语言有效时（例如仅 C++ 的 `-std=` 或某个告警开关），用它们以免传给其它语言。按源文件扩展名逐个选择。

**示例：** `extra_cxxflags = ['-fno-rtti']`

### `extra_linkflags`：string[] = []

额外的链接选项。

**示例：** `extra_linkflags = ['-fopenmp']`
**说明：** 常用选项（如 `-g`）已默认包含，该参数应尽量少用。

### `linkflags`：string[] = None

覆盖全局 [`linkflags`](../config.md#cc_config) 配置。

**示例：** `linkflags = ['-fopenmp']`
**注意：** 该参数会整体覆盖全局设置。除非你非常了解 GCC 和链接器的相关选项，否则不建议使用。

## cc_library

用于描述 C++ 库目标。

`cc_library` 同时用于构建静态和动态库，默认只构建静态库，只有被设置了 `dynamic_link = True` 的 `cc_binary` 依赖时或者命令行指定 `--generate-dynamic` 才生成动态链接库。

cc_library 生成的动态链接库里不包含其依赖的代码，而是包含了对所依赖的库的路径。这些库主要是为了开发环境本地使用（比如运行测试），并不适合部署到生产环境。
如果你需要生成需要在运行时动态加载或者在其他语言中作为扩展调用的动态库，应该使用 `cc_plugin` 构建规则，这样生成的动态库已经以静态链接的方式包含了其依赖。

示例：

```python
cc_library(
    name='lowercase',
    srcs=['lower/plowercase.cpp'],
    hdrs=['lower/plowercase.h'],
    deps=['#pthread'],
    link_all_symbols=False
)
```

属性：

- `hdrs`: list(string) = []，声明库的公开接口头文件。

  对于通常的库，`hdrs` 都是应该存在的，否则这个库可能就无法被调用。因此这个属性是必选的，否则会报告出一个诊断问题，
  问题的严重性可以通过 [`cc_library_config.hdrs_missing_severity`](../config.md#cc_library_config) 来控制。
  对于在支持 hdrs 前已经存在的问题，可以通过 [`cc_library_config.hdrs_missing_suppress`](../config.md#cc_library_config) 来抑制。

  对于构建期间生成头文件的规则，比如 `proto_library` 生成的 `pb.h` 或者 `gen_rule` 目标的 `outs` 里如果包含头文件，这些头文件也会被自动列入。
  把头文件纳入到依赖管理中，可以避免包含了头文件但是没有加入依赖的库造成的编译或者链接问题，特别是对动态生成的头文件。

  一个头文件可以属于多个 `cc_library`，`cc_library` 不会自动导出其 `deps` 里依赖的其他 `cc_library` 的 `hdrs`。
  `hdrs` 里只应该列入公开的头文件，对于私有头文件，即使它被公有头文件包含，也不需要列入。私有头文件应当列入到它的 `srcs` 里。

  所有的 CC 库都应该通过 `cc_library` 来描述，特别是对于只有头文件的库。因为任何库都难免依赖其他库，如果是普通的库缺失，链接期间会报找不到符号的错误，
  根据错误信息比较容易补充缺失的依赖，但是对于只有头文件的库，即使是间接依赖，也是在最终链接时才报告错误，让使用者难以发现。

  因此，对于只有头文件的库，也需要用 `cc_library` 来描述，其公开头文件需要列入到其 `hdrs` 中，其直接依赖需要列入到 `deps` 中。

  如果库的粒度太大，那么通过强制 `hdrs` 检查机制，会导致传递一些不必要的依赖，这时应该进行适当的拆分以降低不必要的耦合。
  比如 gtest 里的 [gtest_prod.h](https://github.com/google/googletest/blob/master/googletest/include/gtest/gtest_prod.h)，
  常用来在产品代码中为测试提供支持，但是它本身只包含一些声明，并不依赖 gtest 库的实现部分。这种情况就适合再单独声明成一个
  独立的 `gtest_prod` 库，而不是和 `gtest` 库放在一起，否则可能导致 gtest 库被链接进产品代码。

- `textual_hdrs`: list = []，以**文本方式**被 `#include` 的类头文件文件。

  这类文件会暴露给依赖方并被文本包含，但从不单独编译或解析。这是 Bazel
  `textual_hdrs` 的对应物。

  与 `hdrs` 不同——`hdrs` 必须是自洽的、会检查头文件扩展名、并且每个都会被单独
  预处理以构建包含依赖图——`textual_hdrs` 不受这些约束：可以是任意扩展名，也无需
  能够独立编译。与 `hdrs` 一样，它们会被声明为由本库提供，因此依赖方 `#include`
  其中之一即可通过“缺失依赖”检查（并使该依赖计为已使用）。

  它适用于那些只有被粘贴进另一个翻译单元中间才有意义的文件：

  - **X-macro / 列表展开**——一个文件以不同的宏定义被反复 `#include` 以展开一张表
    （没有 include guard，无法独立编译）：

    ```python
    cc_library(
        name = 'opcodes',
        srcs = ['vm.cc'],          # vm.cc: #define OP(x) ...; #include "opcodes.def"
        hdrs = ['vm.h'],
        textual_hdrs = ['opcodes.def'],
    )
    ```

  - **按平台分发的实现片段**——某个源文件按平台 `#include` 对应的实现片段，因此这些
    片段不会被直接编译：

    ```python
    cc_library(
        name = 'event_loop',
        # event_loop.cc: #if __linux__  #include "event_loop_epoll.inc" ...
        srcs = ['event_loop.cc'],
        hdrs = ['event_loop.h'],
        textual_hdrs = ['event_loop_epoll.inc', 'event_loop_kqueue.inc'],
    )
    ```

  若把这种被文本包含的文件错误地列入 `hdrs`，则会失败：blade 会拒绝非头文件扩展名，
  否则会尝试单独预处理它——而引用了仅由其包含者定义的符号/宏的片段会因此报错。
  `textual_hdrs` 才是这类文件的正确归属。

- `link_all_symbols`: bool = False，整个库的内容不管是否用到，全部链接到可执行文件中。

  如果你通过全局对象的构造函数执行一些动作（比如注册一些可以按运行期间字符串形式的名字动态创建的类），而这个全局变量本身没有被任何地方引用到。
  这在 cc_binary 中是没有问题的，但是如果是在库中，就有可能被整个丢弃从而达不到期望的效果。这是因为如果一个库中的符号（函数，全局变量）没有被可执行文件直接
  或者间接地显式使用到，通常不会被链接进去。

  如果为 `True` ，任何直接或间接依赖于此库的可执行文件将会把这个库完整地链接进去，即使库中某些符号完全没有被可执行文件引用到，从而解决上述问题。

  需要全部链接的部分最好单独拆分出来做成单独小库，而不是整个库全都全部链接，否则会无端增大可执行文件的大小。

  需要注意的是，link_all_symbols 是库自身的属性，不是使用库时的属性。

  如还有疑问，可以进一步阅读[更多解答](https://stackoverflow.com/questions/805555/ld-linker-question-the-whole-archive-option)。

- `generate_dynamic`: bool | None = None，是否在静态库之外额外生成动态库（`.so`/`.dylib`/`.dll`）。

  默认的 `None` 表示“自动判断”：仅当本库被某个 `dynamic_link` 可执行文件依赖、或使用 `--generate-dynamic` 构建时才生成动态库。无论如何静态库都会生成。

  设为 `generate_dynamic = False` 表示永久退出：不再生成动态库，并且即便被 `dynamic_link` 可执行文件依赖也以**静态**方式链接。对于跨链接边界暴露全局可变数据的库（例如带全局用例注册表的测试框架），这是正确的选择——这类数据无法通过自动导出的动态库安全共享，详见下文[Windows DLL 支持](#windows-dll-支持)。

  设为 `generate_dynamic = True` 则强制无条件生成动态库。

- `check_undefined`: bool = True **（实验性）**

  是否在归档完成、最终链接之前**静态校验**：本库声明的 `deps` 是否覆盖了它引用的全部未定义符号。如果有未定义符号缺乏来源，立即给出诊断并指出具体的缺失依赖；否则一直等到最终二进制链接才会爆出（往往滞后到几百个目标之后），错误消息只指向二进制名而非有问题的库本身。

  检查方式：对本目标新生成的 `.a` 跑 `nm -u`（MSVC 下用 `dumpbin`），对每个传递的 `cc_library` 依赖归档跑 `nm --defined-only`（同样 MSVC 下用 `dumpbin`），再加上每个 `#alias` 系统库（如 `#m`、`#pthread`、`#dl`）的预生成符号缓存（消费者用了 `pow()` 就必须显式声明 `'#m'`）。即便 `generate_dynamic = True`，本检查也仍然执行——它比最终链接更快、并能更早、按库粒度指出问题。

  本检查默认启用，但目前仍属实验阶段，其诊断默认以 `warning` 级别输出（见 [`cc_library_config.check_undefined_severity`](../config.md#cc_library_config)）——构建照常继续，未覆盖到的边缘情况以告警形式出现，而不会直接打断 CI。在你的代码库上稳定通过后，可将级别切换为 `error`。

  详见 [静态未定义符号检查](#static-undefined-symbol-check)；本次调用级覆盖：`--cc-check-undefined` / `--no-cc-check-undefined`；全局默认：[`cc_library_config.check_undefined`](../config.md#cc_library_config)。

- `allow_undefined`: bool | list[str] = False

  允许本库引用 deps 中没有任何目标提供的符号——也就是这些符号会在最终链接时由依赖图之外的东西补齐（典型场景：插件被宿主进程加载、宿主提供符号）。

  - `False`（默认）—— 所有未定义符号必须有 `deps` 覆盖，静态检查会强制这点。
  - `True` —— 完全放行：跳过静态检查，并且也不传 `-Wl,--no-undefined` 给链接器。用于宿主装载的插件库。
  - `list[str]` —— 窄化的允许清单，每条是一个正则表达式（按 `nm -u` 输出的 mangled 名字 `re.fullmatch` 匹配）。静态检查正好放行列出的几个名字，其余仍然强制闭合。

  这是单目标设置。项目级（同样的正则语义）允许清单见 [`cc_library_config.allow_undefined`](../config.md#cc_library_config)。

- `binary_link_only`: bool = False，本库只能作为可执行文件目标（比如 `cc_binary` 或者 `cc_test`）的依赖，而不是其他 `cc_library` 的依赖。

  本属性适用于排他性的库，比如 malloc 库。

  例如 `tcmalloc` 和 `jemalloc` 库都包含了一些相同的符号（`malloc`、`free`等）。如果某个 `cc_library` 依赖了 `tcmalloc`，那么依赖他的 `cc_binary` 将不
  能再选择 `jemalloc` 库，否则会造成链接冲突。通过把 `tcmalloc` 和 `jemalloc` 都设置这个属性，使得其只能作为可执行文件的目标的依赖，从而避免这类问题。

  'binary_link_only' 库可以依赖其他 'binary_link_only' 库。

  示例：

  ```python
  cc_library(
      name = 'tcmaloc',
      binary_link_only = True,
      ...
  )

  cc_library(
      name = 'jemaloc',
      binary_link_only = True,
      ...
  )
  ```

- `always_optimize` : bool，是否不管 debug 还是 release 都开启优化。

  True: 不论 debug 版本还是 release 版本总是被优化。
  False: debug 版本不作优化。
  默认为 False。目前只对 cc_library 有效。

- `prebuilt` : bool = False。

  废弃，请使用 prebuilt_cc_library 构建规则。

- `export_incs` : list(str) = []，导出的头文件搜索路径。

  类似于 `incs`，但是不仅作用于本目标，还会传递给依赖这个库的目标，和 `incs` 一样，建议仅用于不方便改代码的第三方库，自己的项目代码还是建议使用全路径头文件包含。

- `system_include` : bool = False

  设为 `True` 时，消费者编译用 `-isystem <path>` 而不是 `-I <path>` 暴露本库的 `export_incs`。编译器把这些头当作系统头：内部诊断默认抑制（也不会被消费者的 `-Werror` 升级为错误）。适合包裹第三方 / vendored / 生成头文件的薄壳库——它们自己的 warning 不该污染一方代码的构建。`foreign_cc_library` 自动按此处理；`system_include = True` 是手写 wrapper 的 opt-in。

### 修复 `hdrs` 引发的依赖缺失的检查问题

在大规模 C++ 项目中，依赖管理很重要，而长期以来头文件并未被纳入其中。从 Blade 2.0 开始，头文件也被纳入了依赖管理中。
当一个 cc 目标要包含一个头文件时，也需要把其所属的 `cc_library` 放在自己的 `deps` 里，否则 Blade 就会检查并报告问题。

在 `deps` 中缺少对代码中用到的头文件所属的库的依赖的声明会带来如下问题：

- 导致库之间的依赖无法正确传递。如果某个未声明的头文件所属的库将来增加了新的依赖，可能造成链接错误。
- 对于构建期间生成的头文件，缺少对其所属的库的依赖声明会导致编译时这些头文件可能还未生成，从而造成编译错误。
- 更糟糕的是，如果这些头文件已经存在，但是尚未更新，编译时用到的就可能是过时的头文件，会导致更加难以排查的运行期错误。

问题的严重性可以通过 [`cc_config.hdr_dep_missing_severity`](../config.md#cc_config) 配置项来控制。对于在支持 hdrs 前已经存在的问题，
可以通过 [`cc_config.hdr_dep_missing_suppress`](../config.md#cc_config) 来抑制。

Blade 能检查到两种缺失情况：

- `Missing dependency` 直接依赖缺失

  在 `srcs` 或者 `hdrs` 里的文件通过 `#include` 指令包含了头文件，但是其所属的库没有在 `deps` 里声明，
  或者这些头文件根本没有在任何 `cc_library` 的 `hdrs` 里声明。

  在机械地按提示「加这个 dep」之前，先停一步，对照下面几条确认你属于哪种情形——只有情形 1 适合直接照办；情形 6 是多余的 include 应该直接删；情形 7 在下次构建会撞到 visibility 错误，需要走 `friend`-式扩 visibility。

  具体原因及解决方法：

  1. 该头文件所属的库没有在本目标的 `deps` 里声明，按提示修复即可。
  2. 该头文件是所属的库的私有头文件，禁止直接使用。**例外见情形 7。**
  3. 该头文件应当是本目标的公有头文件，在其 `hdrs` 里声明即可。
  4. 该头文件应当是本目标的私有头文件，在其 `srcs` 里声明即可。
  5. 该头文件应当是其他库的公有头文件，但是没有声明，在相应库的 `hdrs` 里声明即可。
  6. **这个 `#include` 本身是多余的，直接删掉就行。** Blade 的 missing-dep 检查不看你的代码内容，只看你 `#include` 了什么。如果你的源文件并没有真的用到那个头里定义的任何名字（include 是早年复制粘贴留下的、重构后变成 dead code、或者你以为需要的类型其实通过你已经 include 的另一个头传递性可达），正确解法是**删掉这一行 `#include`**，而不是加一个 dep。快速判断：在源文件里 grep 一下可疑头里定义的类型/函数名；如果一个都没匹配到，include 就是死的。
  7. **跨越 visibility 边界的合法 "facade" 再导出场景。** 当一个 umbrella 目标的公共头通过 `#include` 把内层私库的头导出，使得 umbrella 的消费者能用到那些类型时，blade 会对 umbrella 报 missing-dep——因为内层私库的 `visibility` 把 umbrella 锁在外面。但 umbrella 本来就是合法消费者——它是这些类型的规范再导出点——情形 (2) 那条「私头禁止直接用」太绝对，没给这种合法 facade 留口子。把 umbrella 当成 C++ 的 `friend`：在内层私库的 `visibility` 列表里把它加进去（一个窄而具名的开放），然后在 umbrella 的 `deps` 里声明该私库。visibility 行和 deps 行都附上注释说明再导出关系，让意图自文档。

     ```python
     # 内层私库：
     cc_library(
         name = 'http_filter',
         hdrs = 'http_filter.h',
         ...,
         # `friend` 式白名单：只允许下面两个 umbrella facade 直接依赖；
         # 其它消费者必须走 facade。
         visibility = ['//flare/rpc:http', '//flare/rpc:rpc'],
     )

     # 在公共头里再导出该私库的 umbrella：
     cc_library(
         name = 'rpc',
         hdrs = ['http_filter.h', ...],  # 透传 include 内层头
         deps = [
             ...,
             '//flare/rpc/protocol/http:http_filter',  # 我们再导出
         ],
         visibility = 'PUBLIC',
     )
     ```

     如果 umbrella 只是「消费者」（用了内层库的公共接口，但**不**通过自己的 hdrs 再导出），并且 `unused_deps` 报了这个 dep，那其实是反方向的 [Header re-export 自动豁免](#检查未使用的依赖) 场景——把内层私库的头列入 umbrella 自己的 `hdrs` 即可，无需放开 visibility。

- `Missing indirect dependency` 间接依赖缺失

  源文件通过 `#include` 指令包含的头文件链中，某个头文件所属的库没有出现在本目标及其传递依赖的 `deps` 里。

  我们只对编译期间生成的头文件做这个检查。因为对于生成头文件的规则（比如 `proto_library` 或者可能是 `gen_rule`），如果依赖缺失，
  可能会导致在编译当前目标时，这些头文件可能还没生成或者是过时的，导致编译错误。

  修复这个错误麻烦一些，你需要顺着错误信息报告的包含栈，从源文件开始，依次向上查找各个头文件所属的库中，是否依赖了其包含的头文件所属的库。

  这时可能遇到一种情况，就是某些纯头文件的库没有实现文件，因此根本没有对应的 `cc_library` 描述它，这时候就需要为它写一个新的 `cc_library`，在 `hdrs`
  中列出头文件，`deps` 中列入其实现所需要的依赖。然后把它加入到使用到它的库的依赖中。

  这样能解决根本问题，不过确实需要花一些精力。简单粗暴的解决方式则是把报告缺失的库加入到当前目标的 `deps` 中，这相当于依赖了某些库的实现细节，非常不
  推荐。

由于 Blade 把头文件也完全纳入了依赖管理，对于未在任何库的 `hdrs` 或者 `srcs` 中声明的头文件，构建结束后也会报错，如果这些头文件应当属于当前目标，
根据其是公开或者私有的，分别将其加入到 `hdrs` 或者 `srcs` 中；如果属于其他库，则应当加入到其他库的 `hdrs` 中，不能包含其他库的未声明的私有头文件。
对于升级前代码库中已经存在的未声明的头文件，可以用 [cc_config.allowed_undeclared_hdrs](../config.md#cc_config) 配置项屏蔽检查。

### 检查未使用的依赖

与上面「缺失依赖」相对，Blade 还能检查**多余的依赖**：在 `deps` 中声明了某个库，但本目标的源文件和头文件并没有直接 `#include` 它的任何公开头文件。多余依赖会拖慢构建、传递不必要的依赖，长期容易腐化。

该检查默认即以 `'warning'`（建议性）开启：会提示但不导致构建失败。通过 [`cc_config.unused_deps_severity`](../config.md#cc_config) 可设为 `'error'` 让构建失败，或设为 `'debug'` 关闭。与 Bazel 的 `unused_deps`、Buck2 一致，默认是建议性的。

#### `keep_deps` 何时该用、何时不该用

**`keep_deps` 在实践中应当极其少见。** Blade 已经自动豁免了一系列「看起来未用但实际是真依赖」的结构性场景；一个结构合理的 BUILD 几乎不需要任何 `keep_deps`。在添加 `keep_deps` 之前，先确认下面的自动豁免条件是否已经覆盖你的情况，或者问题的真正解法是不是**改结构**而非**抑制告警**。

#### 自动被豁免的情况

以下任一条满足时，依赖**永远不会**被报告为未使用：

1. **该依赖没有公开头文件** —— 显式 `hdrs = []`，或等价的「header-less」状态。自动适用于：
   - 显式 `hdrs = []` 的库（无公开接口）。
   - 名字列在 [`cc_library_config.hdrs_missing_suppress`](../config.md#cc_library_config) 里的库 —— 用户已经声明「此库没有公开头文件」，Blade 视为等同 `hdrs = []`。
   - 未声明 `hdrs` 的 `foreign_cc_library`。这类目标注册的 `hdr_dir` 是源码树内的目录（如 `thirdparty/gflags/gflags`），而消费者只会从安装后的目录引用头文件（如 `<gflags/gflags.h>`），未使用检查没有任何机会将依赖判定为「已使用」。

2. **目标没有可扫描的 C/C++ 源文件**。当一个目标的 `srcs` 和 `hdrs` 加起来没有任何文件可被 Blade 扫描 `#include` 时（空 srcs 的伞库、`.cc` 落在 `build_dir` 下的 `proto_library` 包装、纯生成代码、外部构建……），本目标直接跳过检查 —— 没有 `#include` 语料可以对照，否则每个 dep 都会变成误报。

3. **头文件再导出（re-export）**。当伞目标声明的某个 `hdrs` 同时被它的某个 dep 也声明为公开头文件时，该 dep 被视为隐式已使用。这是典型的伞门面模式（如 `fiber:fiber` 把 `async.h`、`future.h` 列在自己 `hdrs` 中，而 `fiber:async`、`fiber:future` 也分别声明这些头）。

4. **`export_incs` 虚拟路径**。当一个库的头文件放在私有子目录、通过 `-Iexport_inc_path` 暴露给消费者（例如 `protobuf-3.4.1` 的 `src/google/protobuf/message.h` 配 `export_incs = ['src']`）时，Blade 同时注册完整路径与「消费者可见的相对路径」（`google/protobuf/message.h`），使 `#include <google/protobuf/message.h>` 能解析回 protobuf 目标。

5. **系统库**（形如 `#:NAME` 的依赖，例如 `#:dl`、`#:pthread`）。它们的头文件（`<dlfcn.h>`、`<pthread.h>`）确实存在，但 Blade 没有「系统头 → 系统库」的映射表，本检查无从对照。

6. **`keep_deps` 与 `unused_deps_suppress`** —— 用户显式覆盖。

#### 何时真的需要 `keep_deps`

剔除上面所有自动豁免之后，剩下的是「纯链接时」模式：依赖的符号在 link 时被引用，但消费者并不 `#include` 它的任何公开头文件。即便如此，`keep_deps` 通常仍**不**是正确答案：

- **自注册库** —— 协议实现、NSLB、name resolver、压缩器、工厂插件等通过静态初始化向全局注册表自注册、消费者从不直接 `#include` 它的库 —— 应当**把 `.h` 移到 `srcs`、并声明 `hdrs = []`**。该库通过上面 (1) 自动豁免。**如果某个目标（典型如它对应的 `*_test.cc`）确实需要 `#include` 这个私有头文件，只要测试目标直接依赖该库，Blade 允许它按名引用** —— 私有头文件可以被直接依赖该库的目标按名引用。这意味着你**不需要**为了测试能 include 而把头文件公开。

- **伞门面（umbrella facade）** —— 在自己 `hdrs` 中列出子库的公开头文件，(3) 即可自动豁免，不需要 `keep_deps`。

- **「为了显式」而重复列出的传递依赖** —— 直接删掉。如果 `:hbase_channel` 已经依赖 `:hbase_client_protocol`，那么依赖 `:hbase_channel` 的伞目标 `:hbase_client` 就**不需要**再直接列一遍 `:hbase_client_protocol`。这种冗余直依赖才是触发「未使用」的根源。

为副作用（自注册全局对象等）被链接的库，本身应当声明 `link_all_symbols = True`，以避免链接器丢弃。

只有当以上情况都不适用时，`keep_deps` 才合适 —— 例如，一个伞库聚合了若干个「纯链接注册、自身也没有可再导出的公开头文件」的子目标。

```python
cc_library(
    name = 'foo',
    srcs = ['foo.cc'],
    hdrs = ['foo.h'],
    deps = [':bar'],          # 通过头文件使用
    keep_deps = [':baz'],     # 真正的纯链接、不属于自动豁免的情形
)
```

#### 常见的误用模式（看起来像多余依赖、其实不是）

- **私有头文件被错误地列入 `hdrs`**。如果一个库的 `.h` 只被自身 `.cc` 和它的 `*_test.cc` 使用，根本不需要公开头文件。把 `.h` 移到 `srcs`、`hdrs = []`，所有消费者通过 (1) 自动豁免。测试目标仍可按名 `#include` 私有头。
- **伞门面没有把子库的头文件再列一遍**。如果伞库聚合多个子库，把子库的公开头文件也加入伞库自己的 `hdrs`，(3) 即可自动豁免「伞 → 子库」的依赖。
- **未显式声明 `hdrs` 的 `foreign_cc_library`**。这种情况下 hdr_dir 注册的是源码树路径，永远无法匹配消费者的 `#include`；(1) 已自动处理，但如果你还想要缺失依赖检查也生效，建议把公开头显式列入 `hdrs`。
- **通过 `export_incs` 路径访问的库**。(4) 已自动处理 —— 如果检查仍触发，确认 `export_incs` 配置的是实际的根（如 `src`，不是 `.` 或完整路径）。
- **`proto_library` 当成「纯链接」依赖**。`proto_library` 生成的 `.pb.h` 目前还未与 `_hdr_targets_map` 完全打通，可能暂时仍需要保留在 `keep_deps` 中。（已知待修复。）

> 提示：在确定结构性解法（私有细节通过 `hdrs` 泄漏？伞库没再导出？冗余的传递性依赖？）已经不适用之前，不要急于用 `keep_deps` 或 `unused_deps_suppress` 来抑制检查。看起来像「Blade 太烦」的模式，几乎都是检查正确捕捉到的真问题。

在 [`cc_config.unused_deps_suppress`](../config.md#cc_config) 中按 `{target: [deps]}` 列出的依赖也会被豁免（主要用于存量代码的逐步治理——批量改 BUILD 不现实时）。

### Static undefined-symbol check

Blade 的「缺失依赖检查」（上文）解决头文件遗漏；与之配套的**未定义符号检查**解决其链接侧对偶问题：本 `cc_library` 引用了某个符号，而它声明的 deps（含传递 `cc_library` 与 `#alias` 系统库）里没有任何目标真正定义这个符号。

没有这个检查时，缺失的 `deps` 只能在最终二进制链接那一步才会爆出，往往是一片 `undefined reference to ...` 报错——错误信息只点名**二进制**，而不是出问题的库。本检查把这次失败前移到时间线上更早的位置：归档刚生成、按库粒度，错误消息直接指出该补哪条 dep。

工作方式：

- `nm -u <archive>` 列出本目标新归档里的未定义符号。
- `nm --defined-only` 对每个传递的 `cc_library` 依赖归档做同样列举。
- 传递依赖中每个 `#alias` 系统库（`#m`、`#pthread`、`#dl` …）贡献一份预生成的符号缓存。
- 一份内置基线吸收平台符号（libc、libstdc++、弱引用等）。
- 还有未匹配的符号 → 报错，给出符号名和所属目标，构建失败。

**适用平台。** Linux 和 macOS。MSVC 跳过（`link.exe` 自身的 LNK2019 已经拒绝未定义外部符号；而且 MSVC 的 `.obj` DEFAULTLIB 指令解析 C/C++ 标准符号的路径在源码可见的 `-l<name>` 图之外，nm 模型无法忠实表达）。当 target 设了 `check_undefined = False` 或 `allow_undefined = True` 时也跳过。

**`generate_dynamic = True` 时的行为。** 仍然执行本检查。最终动态链接的 `-Wl,--no-undefined` 才是最权威的答案，但 nm **在任何链接发生之前**、**按库**就能捕到同样的问题，速度更快、并能精确指向需要修改的那条 dep。

**控制方式。**

- 按目标 —— 在 `cc_library` 上设 [`check_undefined`](#cc_library) 或 [`allow_undefined`](#cc_library)。
- 按本次调用 —— `--cc-check-undefined` 强制开启、`--no-cc-check-undefined` 强制关闭。CLI 覆盖项目默认；但 target 上的 `check_undefined = False` 仍然胜出。
- 项目级 —— [`cc_library_config.check_undefined`](../config.md#cc_library_config) 以及全局正则白名单 [`cc_library_config.allow_undefined`](../config.md#cc_library_config)。

**合法的未定义符号情形。** 被宿主进程装载的插件库，其引用的符号只会由宿主二进制提供——设 `allow_undefined = True`，该库同时退出静态检查和链接器 `--no-undefined`。如果只是放行少数个别符号（例如某种 toolchain 注入但不参与链接的特殊符号），用列表形式 `allow_undefined = [r'__some_symbol']` 让其他闭合性约束继续生效。

**与 `--generate-dynamic` 的性能对比。** 在本检查存在之前，验证「每个 cc_library 的 deps 是否完整」的常规做法是用 `--generate-dynamic` 把整个项目都构成动态库——每次共享链接会走 `-Wl,--no-undefined`，缺依赖就链接失败。这种方式能用，但代价有两条：(a) 即便项目本来不需要动态链接，也要把每个共享库真的链一遍；(b) 失败只发生在最终链接阶段，报错指向的是二进制，而不是出问题的库。静态检查把同一份验证前移到归档时、按库进行。

实测（Tencent/flare 的 `flare/rpc/...`，180 个 cc 目标，macOS arm64、Python 3.14、`-j10`）：

| 场景 | Wall-clock | 备注 |
| --- | --- | --- |
| 冷态全量构建，`--generate-dynamic --no-cc-check-undefined` | 2m56s | 静态库 + 动态库，无校验 |
| 冷态全量构建，`--generate-dynamic --cc-check-undefined` | 3m06s | 静态库 + 动态库 + 静态检查 |
| 冷态构建的静态检查边际开销 | **+10s（+5.7%）** | 与链接阶段并行 |
| 增量纯检查阶段（warm，仅重跑 check） | **4.2s** | 180 个目标，源码已 build |
| 增量纯 dylib 重链接，`--no-cc-check-undefined` | 3.1s | 91 个 dylib，源码已 build |

也就是说：对**本来不需要动态库**的项目，`--cc-check-undefined` 是验证依赖图最便宜的方式——只在普通静态构建之上加几秒；而 `--generate-dynamic` 要付出每个共享链接的完整代价，只为找一条漏依赖。两者互为补充而非替代：要动态库就继续用 `--generate-dynamic`；只为校验图完整性，用静态检查。

## prebuilt_cc_library

主要用于描述一些没有源代码或者或者是通过别的构建系统已经构建好的第三方库。
除了编译和链接库本身代码的属性外，其余 `cc_library` 的属性都适用于本目标。
对应的库文件可以放在子目录中，子目录的名字通过 `libpath_pattern` 属性设置。

库文件有两种定位方式：

- **按命名约定**（默认）：文件名为 `lib<name><后缀>`，位于 `lib{32,64}` 风格的子目录下。
- **按显式路径**：通过 `static_library` / `dynamic_library`（见下）直接给出路径——当文件名或目录结构不符合约定时很有用。

属性：

- `libpath_pattern` : str
  库文件所在的子目录名。默认使用 `cc_library_config.prebuilt_libpath_pattern` 配置。
  本属性是一个可替换的字符串模式，因此可以同时描述多个目标平台的库，比如不同 CPU 位数，等等。具体
  参见 [cc_library_config.prebuilt_libpath_pattern](../config.md#cc_library_config)，如果只构建一个平台的目标，可以只有一个目录。
  本属性可以为空，表示没有子目录（库文件就放在当前 BUILD 文件所在的目录）。
- `static_library` : str，静态库（`.a` / `.lib`）的显式路径（相对于目标所在目录）。
- `dynamic_library` : str，动态库（`.so` / `.dylib` / `.dll`）的显式路径（相对于目标所在目录）。
- `import_library` : str，**Windows 导入库**（`.lib`）的显式路径（相对于目标所在目录）——即链接 `.dll` 时所链接的文件。仅 Windows 有效：在 MSVC 工具链上生效，其它平台忽略。设置后，blade 用导入库进行动态链接，并把 `dynamic_library`（即 `.dll`）作为仅运行期产物（在 test/run 的 runfiles 中铺平）。在 MSVC 上，设置 `dynamic_library` **必须**同时设置 `import_library`——`.dll` 不能直接链接，且无法仅凭文件名区分导入库与真正的静态 `.lib`（因此用 `static_library` 与 `import_library` 加以区分）。
  设置任一显式路径时，至少需要一个，命名约定不再生效，`libpath_pattern` 也会被忽略（给出告警）。与约定模式一致，当只存在一种库时，它同时用于静态链接与动态链接。

示例：

```python
# 按命名约定（在 lib{32,64} 子目录下查找 lib<name>）：
prebuilt_cc_library(
    name = 'mysql',
    deps = [':mystring', '#pthread']
)

# 按显式路径：
prebuilt_cc_library(
    name = 'foo',
    hdrs = ['foo.h'],
    static_library = 'lib/libfoo.a',
    dynamic_library = 'lib/libfoo.so',
    export_incs = ['include'],
)

# Windows：链接导入库，DLL 作为运行期产物：
prebuilt_cc_library(
    name = 'bar',
    hdrs = ['bar.h'],
    import_library = 'lib/bar.lib',
    dynamic_library = 'bin/bar.dll',
    export_incs = ['include'],
)
```

## foreign_cc_library

注意：本特性目前还处于实验状态。

世界上已经有大量已经存在的库，它们用一些不同的构建系统构建，如果要增加 Blade 构建，需要投入大量的时间成本和维护。
foreign_cc_library 用于描述不是直接通过 Blade 构建而是其他构建工具产生的 C/C++ 库，比如 make 或 cmake 等。
foreign_cc_library 和 prebuilt_cc_library 的主要区别是其描述的库是 Blade 在构建期间调用其他构建系统动态生成的，
而 prebuilt_cc_library 所描述的库是构建前提前放置于源代码树中的。所以 foreign_cc_library 总是需要搭配 gen_rule 来使用。

考虑到大量采用 [GNU Autotools](http://autotoolset.sourceforge.net/tutorial.html) 构建，foreign_cc_library 的默认参数适配其安装后的
[目录布局](https://www.gnu.org/software/automake/manual/html_node/Standard-Directory-Variables.html)。
为了能正确找到库和头文件，foreign_cc_library 假设包构建后会安装到某一个目录下（也就是 `configure` 的 `--prefix` 参数所指定的路径），头文件在 `include`
子目录下，库文件安装到 `lib` 子目录下。

属性：

- `name` 库的名字
- `install_dir` 包构建完成后的安装目录
- `lib_dir` 库在安装目录下的子目录名
- `has_dynamic` 是否生成了动态库
- `static_library` / `dynamic_library` / `import_library`：str，外部构建产出的库的显式路径（相对于 `install_dir`），用于覆盖 `lib_dir`/`has_dynamic` 的命名约定。当构建产出的名字无法用 `lib<name>.<后缀>` 约定表达时（带版本后缀、多个库等）很有用。`import_library` 是 Windows 上为产出的 `.dll` 链接所需的导入库 `.lib`（在 MSVC 上给定 `dynamic_library` 时必需）。与 `prebuilt_cc_library` 行为一致的双模式；链接选择、运行期文件与 `check_undefined` 的 `.syms` 处理在两个规则间共享。

### 示例 1，zlib

zlib 是最简单的 autotools 包，假设 zlib-1.2.11.tar.gz 在 thirdparty/zlib 目录下，其 BUILD 文件则是 thirdparty/zlib/BUILD：

```python
# 假设执行本规则后，会把构建好的包安装到 `build_release/thirdparty/zlib` 下，那么头文件在 `include` 下，库文件则在 `lib` 下。
# 我们为 autotools 和 cmake 开发了通用的构建规则，不过还处于实验状态，这里还是假设用 gen_rule 来构建。
gen_rule(
    name = 'zlib_build',
    srcs = ['zlib-1.2.11.tar.gz'],
    outs = ['lib/libz.a', 'include/zlib.h', 'include/zconf.h'],
    cmd = '...',  # tar xf，configure, make, make install...
    export_incs = 'include',
)

# 描述 zlib 安装后的库

foreign_cc_library(
    name = 'z',  # 库的名字为 libz.a，在 `lib` 子目录下
    install_dir = '', # 包的安装目录是 `build_release/thirdparty/zlib`
    # lib_dir= 'lib', # 默认值满足要求，因此可以不写
    deps = [':zlib_build'],
)
```

使用上述库

```python
cc_binary(
    name = 'use_zlib',
    srcs = ['use_zlib.cc'],
    deps = ['//thirdparty/zlib:z'],
)
```

use_zlib.cc：

```cpp
#include "thirdparty/zlib/include/zlib.h"
// 或
#include "zlib.h"
// 因为 thirdparty/zlib/include/ 已经被导出
```

### 示例 2，openssl

严格说来，openssl 并非用 autotools 构建的，不过它大致兼容 autotools，他的对应 autotools configure 的文件是 Config，安装后的目录布局则兼容。
不过其头文件带包名，也就是不是直接在 `include` 下 而是在 `include/openssl` 子目录下。
假设 openssl-1.1.0.tar.gz 在 thirparty/openssl 目录下，其 BUILD 文件则是 thirdparty/openssl/BUILD：

```python
# 假设执行本规则后，会把构建好的包安装到 `build_release/thirdparty/openssl` 下，那么头文件在 `include/openssl` 下，库文件则在 `lib` 下。
gen_rule(
    name = 'openssl_build',
    srcs = ['openssl-1.1.0.tar.gz'],
    outs = ['lib/libcrypto.a', 'lib/libssl.a'],
    cmd = '...',  # tar xf，Config, make, make install...
    export_incs = 'include', # 让编译器能找到 include 下的 openssl 子目录
)

# 描述 openssl 里包含的两个库

foreign_cc_library(
    name = 'crypto',  # 库的名字为 libcrypto.a，在 `lib` 子目录下
    install_dir = '', # 包的安装目录是 `build_release/thirdparty/openssl`
    deps = [':openssl_build'],
)

foreign_cc_library(
    name = 'ssl',  # 库的名字为 libssl.a，在 `lib` 子目录下
    install_dir = '', # 包的安装目录是 `build_release/thirdparty/openssl`
    deps = [':openssl_build', ':crypto'],
)
```

使用上述库：

```python
cc_binary(
    name = 'use_openssl',
    srcs = ['use_openssl.cc'],
    deps = ['//thirdparty/openssl:ssl'],
)
```

use_openssl.cc：

```cpp
#include "openssl/ssl.h"  // 路径带包名
```

## cc_binary

定义 C++可执行文件目标：

```python
cc_binary(
    name='prstr',
    srcs=['./src/mystr_main/mystring.cpp'],
    deps=['#pthread',':lowercase',':uppercase','#dl'],
)
```

属性：

- `dynamic_link`: bool= True

  cc_binary 默认为静态编译以方便部署，静态链接了 C++运行库和代码库中所有被依赖了的库。由于一些
  [技术限制](https://stackoverflow.com/questions/8140439/why-would-it-be-impossible-to-fully-statically-link-an-application)，glibc 并不包含在内，虽然
  也可以强行静态链接 glibc，但是有可能导致运行时出错。

  如果希望动态链接可执行文件依赖的库，可以使用此参数指定，此时被此 target 依赖的所有库都会自动生成对应的动态库供链接。这能有效地减少磁盘空间占用，但是
  程序启动时会变慢，一般仅用于非部署环境比如本地测试。

  需要注意的是，dynamic_link 只适用于可执行文件，不适用于库。

- `export_dynamic`: bool = True

  常规情况下，so 中只引用所依赖的 so 中的符号，但是对于应用特殊的场合，需要在 so 中引用宿主可执行文件中的符号，就需要这个选项。

  这个选项告诉连接器在可执行文件的动态符号表中加入所有的符号，而不只是用到的其他动态库中的符号。这样就使得在 dlopen 方式加载的 so 中可以调用可执行文件中
  的这些符号。

  详情请参考 man ld(1) 中查找 --export-dynamic 的说明。

### 使用 dwp 文件

当开启 DebugFission（通过 [`cc_config.fission`](../config.md#cc_config) 配置）并开启 dwp 打包
（通过 [`cc_config.dwp`](../config.md#cc_config) 配置）后，调试信息会被分离到单独的 `.dwo` 文件中，
然后这些文件会被打包成单个 `.dwp` 文件（每个 binary target 对应一个）。

如果你需要在生产环境或其他环境中部署带有调试信息的二进制文件以便调试，
可以通过 binary target 来引用 dwp 文件，将其包含在 package 中：

```python
package(
    name = 'server_package',
    ...,
    srcs = [
        # executable
        ('$(location //server:server)', 'bin/server'),
        # Include the dwp file for server binary
        ('$(location //server:server dwp)', 'bin/server.dwp'),
        ...,
    ],
)
```

`$(location :target dwp)` 语法允许你引用特定 binary target 生成的 dwp 文件。

## cc_test

相当于 cc_binary，再加上自动链接 gtest 和 gtest_main。

还支持 testdata 参数， 列表或字符串，文件会被链接到输出所在目录 name.runfiles 子目录下，比如：testdata/a.txt => name.runfiles/testdata/a.txt

用 `blade test` 子命令，会在成功构建后到 name.runfiles 目录下自动运行，并输出总结信息。

- `testdata`: list = []

  在 name.runfiles 里建立 symbolic link 指向工程目录的文件，目前支持以下几种形式：
  - `'file'`

    在测试程序中使用这个名字本身的形式来访问

  - `'//your_proj/path/file'`

    在测试程序中用 `your_proj/path/file` 来访问。

  - `('//your_proj/path/file', "new_name")`

    在测试程序中用 `new_name` 来访问

可以根据需要自行选择，这些路径都也可以是目录。

```python
cc_test(
    name = 'textfile_test',
    srcs = 'textfile_test.cpp',
    deps = ':io',
    testdata = [
        'test_dos.txt',
        '//your_proj/path/file',
        ('//your_proj/path/file', 'new_name')
    ]
)
```

## cc_plugin

生成一个通过静态链接方式包含了其所有依赖的动态链接库，用于在其他语言环境中动态加载。

```python
cc_plugin(
    name='mystring',
    srcs=['./src/mystr/mystring.cpp'],
    deps=['#pthread',':lowercase',':uppercase','#dl'],
    warning='no',
    defs=['_MT'],
    optimize=['O3']
)
```

属性：

- `prefix`: str | None, 生成的动态库的文件名前缀。默认为 `None`，表示沿用当前工具链的平台默认前缀（Linux/macOS 为 `lib`，Windows 为空）。
- `suffix`: str | None, 生成的动态库的文件名后缀。默认为 `None`，表示沿用当前工具链的平台默认后缀（Linux 为 `.so`，macOS 为 `.dylib`，Windows 为 `.dll`）。
- `allow_undefined`: bool, 链接时是否允许未定义的符号。因为很多插件库运行时依赖宿主进程提供的符号名，链接阶段并不存在这些符号的定义。
- `strip`: bool, 是否去除调试符号信息，开启后可以减少生成的库的大小，但是无法进行符号化调试。
- `linker_script`: str，单个[链接器脚本](https://sourceware.org/binutils/docs/ld/Scripts.html)，用来控制链接过程。
  它的作用主要是规定如何把输入文件内的 section 放入输出文件内，并控制输入文件内各部分在程序地址空间内的布局。
  链接器有个默认的内置链接脚本，可用 `ld --verbose` 查看。此选项将会替换系统的默认链接脚本。
  链接器脚本文件的扩展名一般为 `.ld` 或者 `.lds`。
  只接受单个文件：SECTIONS 脚本会替换默认脚本，多个 `-T` 脚本无法有意义地组合。
  链接器脚本通常相当复杂，如果只是想控制符号的可见性，请使用下面的 `export_map` 选项。
  > **GNU ld 特性。** `linker_script` 就是 GNU ld 的 `-T` 选项，需要 GNU ld 兼容的链接器：ELF（Linux）上的 GNU `ld` / `ld.lld`，以及面向 Windows 时 **MinGW 的 GNU `ld`**。MSVC `link.exe` 和 Apple `ld64` **不支持**：在 macOS 上 Blade 会发出 warning 并跳过该脚本(以前会让链接以晦涩的 "unknown options" 失败);MSVC 上会在 `_cc_link` 这一层走不到。
  > 复数形式 `linker_scripts`（列表）是**已废弃的别名**，使用时会告警，且只取第一个文件。
- `export_map`: str，单个[链接器“版本”脚本](https://sourceware.org/binutils/docs/ld/VERSION.html)，用来控制共享库导出哪些符号。
  虽然链接器术语叫“版本脚本”，但这里的机制是*导出过滤*而非 ABI 版本管理，因此命名为 `export_map`（业界对符号导出控制文件的通称）。使用匿名版本形式（不指定版本号）即可只控制可见性。
  只接受单个文件（GNU ld 不允许多于一个匿名版本节点）。可用于 `cc_library`、`cc_binary` 和 `cc_plugin`。会传给 GNU ld 的 `--version-script`；导出映射文件的扩展名一般为 `.exp`、`.sym`、`.ver` 或者 `.map`。参见[下文的 C++ 示例](#控制共享库导出哪些符号)。
  > **跨平台。** 在 Linux 上直接传给 GNU ld。在 **MSVC** 上没有 `--version-script`，Blade 会自行应用该映射：它把每个符号的**反修饰名**（`UnDecorateSymbolName`）与 `global`/`local` 模式匹配，据此过滤自动生成的 `.def`（参见 [Windows DLL 支持](#windows-dll-支持)）。在 **macOS（Apple ld64）** 上同样如此：Blade 通过 `nm` 枚举每个 `.o` 的全局符号，用 libc++abi 的 `__cxa_demangle` 反修饰后与脚本模式匹配，把匹配的（保留 Mach-O 前导下划线的）mangled 名写到 ld64 的 `-exported_symbols_list` 文件里。由于反修饰是*仅名字*的，MSVC 和 macOS 上有两点共同限制：**重载会合并**（一个名字要么连同其所有重载一起导出、要么都不导出），以及带签名的引号模式（`"f(int)"`）只按其**名字部分**匹配（并给出一次性告警）。完整的 ELF 符号版本管理（版本节点）仅限 Linux。实践中只要写 `ns::class::method` 形式的模式就完全够用。
  > 复数形式 `version_scripts`（列表）是 `export_map` 的**已废弃别名**，使用时会告警，且只取第一个文件。

`prefix` 和 `suffix` 控制生成的动态库的文件名。假设 `name='file'`，在 Linux 工具链上默认生成 `libfile.so`；设置 `prefix=''` 则变为 `file.so`。传入已带共享库后缀的 `name`（如 `name='file.so'`）不再被隐式识别为"输出文件全名"，如需完全自定义输出文件名，请改用 `prefix=''` 与 `suffix='.so'` 显式表达。

### 控制共享库导出哪些符号

要控制链接结果中符号是否对外可见，可以通过[源代码中的 GCC 扩展属性或者命令行选项](https://gcc.gnu.org/wiki/Visibility)来进行。当你不想（或无法）改动源码时，`export_map` 能在链接阶段做同样的事：列出要保持 `global`（导出）的符号，其余落入 `local` 的一律隐藏。

#### C++ 示例

假设某个库只想对外暴露 `mylib::Api` 类和工厂函数 `mylib::Create()`，而隐藏其余一切（辅助函数、被静态链入的第三方符号等）：

```cpp
// api.h
namespace mylib {
class Api {
 public:
    void Run();
};
Api* Create();
}  // namespace mylib
```

由于 C++ 符号会被名字修饰（mangle），需要把*反修饰后*的名字写在 `extern "C++"` 块里。编写 `export_map` 文件（如 `api.map`）：

```ld
{
global:
    extern "C++" {
        # 加引号表示按字面精确匹配（不走通配符）——用于在意确切签名、
        # 或避免误匹配重载的场合。
        "mylib::Create()";

        # 不加引号则可用通配符：导出 mylib::Api 的全部成员
        # （构造函数、Run() ……）。
        mylib::Api::*;

        # 跨库继承或 dynamic_cast 时需要 vtable / typeinfo。反修饰器在此
        # 处会打印一个空格，用单字符通配符 '?' 去匹配它。
        typeinfo?for?mylib::Api;
        vtable?for?mylib::Api;
    };
local:
    *;  # 隐藏上面未列出的一切
};
```

在 BUILD 文件中接上（只影响共享库，静态库不变）：

```python
cc_library(
    name = 'mylib',
    srcs = ['api.cc'],
    hdrs = ['api.h'],
    export_map = 'api.map',
)
```

要查看库中的符号的可见性，可以用 nm 命令：

```console
000000000000010c t _init
                 U puts@@GLIBC_2.2.5
0000000000000060 t register_tm_clones
00000000000000f0 T hello
0000000000000100 t world
```

第二列为符号的类别，大写字母为全局符号，小写字母为局部符号。`U` 为库依赖的未定义的外部符号，不用关心。

`cc_plugin` 主要是为 `JNI`，python 扩展等需要运行期间通过调用某些函数动态加载的场合而设计的，不应该用于其他目的。
即使它出现在其他 cc 目标的 `deps` 里，链接时也会被忽略。

### Windows DLL 支持

在 Windows（MSVC）工具链下，需要动态库的 `cc_library` 会被构建为 **DLL 加导入库（import library）**，对应它在 Linux 上会产出的 `.so`。触发条件与其他平台一致：本库被某个 `dynamic_link` 可执行文件依赖，或使用 `--generate-dynamic` 构建。

有两个 Windows 特性已为你自动处理：

- **自动导出。** ELF 默认导出所有全局符号，而 Windows 默认不导出任何符号，除非以 `__declspec(dllexport)` 标注或在模块定义文件（`.def`）中列出。为避免改动源码，Blade 会扫描库的目标文件并生成 `.def`，导出每一个已定义的、对外可见的符号——但会排除位于去重 COMDAT 段中的符号（模板实例化、内联函数等）。C++ vtable 和 RTTI 符号是个例外：即使它们是 COMDAT 也会保留，这样通过 `__declspec(dllimport)` 消费的多态类才能正确链接。这样一个普通的 `cc_library` 无需任何标注即可当作 DLL 使用，就像它已经能当作 `.so` 使用一样。同一批目标文件同时服务静态和动态链接，所以你永远不用写 `dllexport`，库也不会被编译两遍。
- **运行期查找。** Windows 没有 rpath，且 PE 导入表只记录 DLL 的基本名（base name）。因此在测试/运行时，Blade 会把每个依赖 DLL 平铺（flatten）到目标的 `runfiles` 目录，并将该目录前置到 `PATH`——这是 `LD_LIBRARY_PATH` 在 Windows 上的对应物。由于每个 DLL 的名字都编码了它的包路径，平铺时不会冲突。

需要导出纪律，或要控制在 PE 的 64K 导出上限以内时，用 [`export_map`](#cc_library) 收窄导出集。

#### 使用侧的限制

导出端自动化了，但 **Windows 的导入端并不对称**——消费方仍受平台 ABI 约束。当你 `#include` 一个 Blade 构建的 DLL 的头文件并使用它的符号时：

- **函数** —— 无需任何标注即可使用，导入库会提供跳板（thunk）。
- **全局变量 / 静态数据成员** —— 消费方**必须**用 `__declspec(dllimport)` 声明。否则编译器读到的是导入表槽位（一个指针）而不是变量的值，会无声地得到错误结果。因此依赖共享全局可变状态的库——最典型的是带全局用例注册表的测试框架——应设置 `generate_dynamic = False`，使其以静态方式链接进可执行文件。这样依赖图的其余部分仍可以是 DLL，而有状态的库保持正确。
- **多态类** —— Blade 会导出 vtable 和 RTTI，所以通过 `__declspec(dllimport)` 消费的类能正确链接。但你仍需在类声明上加 `__declspec(dllimport)`（编译器引用的是*导入的* vtable/RTTI）。
- **隐式特殊成员** —— `dllimport` 类还会导入它的构造/析构/赋值函数。auto-export 只导出 DLL 里**实际发出**的符号，而仅被消费侧用到的隐式成员在 DLL 里从未发出，会链接失败。把这类成员声明为 out-of-line（例如在 `.cc` 里写 `Greeter::Greeter() = default;`）以强制 DLL 发出并导出它们，或者用工厂函数让消费侧不直接构造该类。
- **一致性** —— 消费方按静态还是 DLL 编译，必须和实际链接的库一致。不匹配会导致 `LNK2019`（未解析）或 `LNK4217`（本地定义符号被当作导入）错误。

在 Linux/macOS 上这些都不存在：导入通过 GOT 解析、无需标注，所以为这些平台写的头文件在使用侧不需要任何修饰。

**推荐做法：** 跨 DLL 边界优先用基于函数的 ABI（访问器 / 工厂函数），而不是直接导出全局变量或多态类。函数无需 `dllimport`、静态/动态共用一套对象，也让头文件免于平台相关的修饰。

> 把使用侧的导入宏也自动化（让头文件无需手写 `dllimport`）已在计划中但尚未实现；目前遗留的导出类头文件仍需自带导入宏。

## windows_resources

使用 Windows SDK 资源编译器 (`rc.exe`) 将 `.rc` 资源脚本文件编译为 `.res` 目标文件。
生成的 `.res` 文件会自动链接到任何通过 `deps` 依赖此目标的 `cc_binary` 中。

在非 Windows 平台上，此规则是**空操作**：它不产生任何构建输出，对构建没有影响。

```python
windows_resources(
    name = 'hello_res',
    rc_files = ['hello_gui.rc', 'version.rc'],
    hdrs = ['resource.h'],
    resources = ['image/blade.ico'],
)
```

参数：

- `rc_files` (必选): **string[]** — 要编译的资源脚本文件 (`.rc`)。
- `hdrs` (可选): **string[]** — `.rc` 脚本包含的头文件。
- `resources` (可选): **string[]** — `.rc` 脚本引用的二进制资源文件 (如 `.ico`, `.bmp`)。这些文件的变化会触发重建。

此目标生成的 `.res` 文件会像目标文件和库文件一样出现在链接器的输入中。与 `cc_binary` 配合使用：

```python
cc_binary(
    name = 'hello_gui',
    srcs = ['hello_gui.c'],
    extra_linkflags = ['/SUBSYSTEM:WINDOWS', 'user32.lib'],
    deps = [':hello_res'],
)
```

## resource_library

把数据文件编译成静态资源，可以在程序中读取。

我们经常会遇到部署一个可执行程序，还需要附带一堆辅助文件才能运行起来的情况。

blade 通过 resource_library，支持把程序运行所需要的数据文件也打包到可执行文件里，这样单个可执行文件即可用于部署。

比如 poppy 下的 BUILD 文件里用的静态资源：

```python
resource_library(
    name = 'static_resource',
    srcs = [
        'static/favicon.ico',
        'static/forms.html',
        'static/forms.js',
        'static/jquery-1.4.2.min.js',
        'static/jquery.json-2.2.min.js',
        'static/methods.html',
        'static/poppy.html'
    ]
)
```

构建后会生成一个头文件 static_resource.h 及相应的库文件 libstatic_resource.a 或 libstatic_resource.so。

在程序中使用时以完整路径包含进来即可使用。需要包含 static_resource.h（带上相对于 BLADE_ROOT 的路径）和 `common/base/static_resource.h`，
用 STATIC_RESOURCE 宏来引用数据：

```c
StringPiece data = STATIC_RESOURCE(poppy_static_favicon_ico);
```

STATIC_RESOURCE 的参数是从 BLADE_ROOT 目录开始的数据文件的文件名，把所有非字母数字和下划线的字符都替换为_。

得到的 data 在程序运行期间一直存在，只可读取，不可写入。

用 static resource 在某些情况下也有一点不方便：就是不能在运行期间更新，因此是否使用，需要根据具体场景自己权衡。

## cu_library

使用 nvcc 编译器编译包含 CUDA 代码的 C++ library

语法和 `cc_library` 基本一致，额外添加两个属性 `cuda_path` 和 `extra_cuflags` 。  
`cuda_path` 指向 cuda 的工作区绝对路径，一般为当前仓库内置的 cuda 目录，可以摆脱对本地 cuda 环境的依赖。对应的 cuda 的 binary `{cuda_path}/bin/nvcc` 和 include 目录 `{cuda_path}/include` 都会自动识别，下面介绍的环境变量指定 cuda 相关路径信息也会被直接忽略。  
`extra_cuflags` 添加仅 cuda 的参数，和 cc 通用的 flag 依然保存在 `extra_ccflags`。


编译 cu_library 需要使用 `NVCC` 环境变量指向 `nvcc binary` ，例如 `NVCC=/usr/local/cuda/bin/nvcc blade build`。  
使用 `CUDA_PATH` 环境变量指向本地 cuda 的安装路径，`CUDA_PATH/include` 和 `{CUDA_PATH}/samples/common/inc` 会自动加到 include search path。

作用优先级： `cuda_path` > `NVCC`/`CUDA_PATH` 。

```python
cu_library(
    name = 'template_gpu',
    srcs = ['template_gpu.cu'],
    hdrs = [],
    # cuda_path = '//thirdparty/cuda',
)
```

## cu_binary

使用 nvcc 编译器编译包含 CUDA 代码的 C++ binary

语法同 `cc_binary` ，命令环境变量参考 `cu_library`

```python
cu_binary(
    name = 'template',
    srcs = ['template.cu'],
    deps = [':template_cpu'],
    # cuda_path = '//thirdparty/cuda',
)
```

## cu_test

使用 nvcc 编译器编译包含 CUDA 代码的 C++ UT

语法同 `cc_test` ，命令环境变量参考 `cu_library`

```python
cu_test(
    name = 'cu_test',
    srcs = ['cu_test.cu'],
    deps = [':template_cpu'],
    # cuda_path = '//thirdparty/cuda',
)
```
