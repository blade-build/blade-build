# C/C++ 规则

C/C++ 程序的构建分为预处理，编译（把预处理后的源文件转化为 `.o` 文件）和链接（把 `.o`, `.a` 链接成可执行文件或者动态库）三个阶段，不同阶段用不同的编译参数。

CC 目标均支持的属性为：

- `warning` 是否屏蔽warning

  `warning='no'`，默认不屏蔽 `warning = 'yes'`, 默认不用写，已开启。

- `defs` 用户定义的宏

  `defs = ['_MT']`，如果要带值，用等号：`A=1`。只对当前目标生效，不会透传给依赖它目标。

- `incs` 增加编译源文件时的头文件查找路径

  `incs = ['poppy/myinc']`。一般用于第三方库，用户代码建议使用全路径 include，不要使用该属性。

- `optimize` 目标的优化选项

  默认为 `optimize = ['-O2']`，之所以需要单独提出来，是因为 debug 模式下需要忽略，optimize影响代码的可调试性。
  如果某些目标，例如性能相关又一般无需调试的库，比如 hash，压缩，加解密之类的，可以加上`always_optimize = True`让他们总是开启优化。

- `extra_cppflags` 额外的 C/C++ 编译 flags

  例如：`extra_cppflags = ['-Wno-format-literal']`。常用 flags 比如 `-g`，`-fPIC` 等都已经内置，一般无需指定。

- `extra_linkflags` 额外的链接 flags
  例如：`extra_linkflags = ['-fopenmp']`。常用 flags 比如 `-g` 等都已经内置，一般无需指定。

- `linkflags`: list = None，覆盖全局配置里的 [linkflags](../config.md#cc_config)

  例如：`linkflags = ['-fopenmp']`。常用 flags 比如 `-g` 等都已经内置，一般无需指定。由于会覆盖全局选项，除非你非常理解 `gcc` 和 `ld` 的各种链接选项，不要轻易用这个参数。

## cc_library

用于描述 C++ 库目标。

`cc_library` 同时用于构建静态和动态库，默认只构建静态库，只有被设置了 `dynamic_link = True` 的 `cc_binary` 依赖时或者命令行指定 `--generate-dynamic` 才生成动态链接库。

cc_library生成的动态链接库里不包含其依赖的代码，而是包含了对所依赖的库的路径。这些库主要是为了开发环境本地使用（比如运行测试），并不适合部署到生产环境。
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

- `link_all_symbols`: bool = False，整个库的内容不管是否用到，全部链接到可执行文件中。

  如果你通过全局对象的构造函数执行一些动作（比如注册一些可以按运行期间字符串形式的名字动态创建的类），而这个全局变量本身没有被任何地方引用到。
  这在 cc_binary 中是没有问题的，但是如果是在库中，就有可能被整个丢弃从而达不到期望的效果。这是因为如果一个库中的符号（函数，全局变量）没有被可执行文件直接
  或者间接地显式使用到，通常不会被链接进去。

  如果为 `True` ，任何直接或间接依赖于此库的可执行文件将会把这个库完整地链接进去，即使库中某些符号完全没有被可执行文件引用到，从而解决上述问题。

  需要全部链接的部分最好单独拆分出来做成单独小库，而不是整个库全都全部链接，否则会无端增大可执行文件的大小。

  需要注意的是，link_all_symbols是库自身的属性，不是使用库时的属性。

  如还有疑问，可以进一步阅读[更多解答](https://stackoverflow.com/questions/805555/ld-linker-question-the-whole-archive-option)。

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

  True: 不论debug版本还是release版本总是被优化。
  False: debug版本不作优化。
  默认为False。目前只对cc_library有效。

- `prebuilt` : bool = False。

  废弃，请使用 prebuilt_cc_library 构建规则。

- `export_incs` : list(str) = []，导出的头文件搜索路径。

  类似于 `incs`，但是不仅作用于本目标，还会传递给依赖这个库的目标，和 `incs` 一样，建议仅用于不方便改代码的第三方库，自己的项目代码还是建议使用全路径头文件包含。

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
  或者这些头文件根本没有在任何 `cc_library` 的 `hdrs` 里声明。具体原因及解决方法：

  - 该头文件所属的库没有在本目标的 `deps` 里声明，按提升修复即可
  - 该头文件是所属的库的私有头文件，禁止直接使用
  - 该头文件应当是本目标的公有头文件，在其 `hdr` 里声明即可
  - 该头文件应当是本目标的私有头文件，在其 `src` 里声明即可
  - 该头文件应当是其他库的公有头文件，但是没有声明，在相应库 `hdr` 里声明即可

- `Missing indirect dependency` 间接依赖缺失

  `#include` 指令包含头文件中包含的其他头文件中的所属的库，没有出现在本目标及其传递依赖的 `deps` 里。

  我们只对编译期间生成的头文件做这个检查。因为对于生成头文件的规则（比如 `proto_library` 或者可能是 `gen_rule`），如果依赖缺失，
  可能会导致在编译当前目标时，这些头文件可能还没生成或者是过时的，导致编译错误。

  修复这个错误麻烦一些，你需要顺着错误信息报告的包含栈，从源文件开始，依次向上查找各个头文件所属的库中，是否依赖了其包含的头文件所属的库。

  这时可能遇到一种情况，就是某些纯头文件的库没有实现文件，因此根本没有对应的 `cc_library` 描述它，这时候就需要为它写一个新的 `cc_library`，在 `hdrs`
  中列出头文件，`deps` 中列入其实现所需要的依赖。然后把它加入到使用到它的库的依赖中。

  这样能解决根本问题，不过确实需要花一些精力。简单粗暴的解决方式则是把报告缺失的库加入到当前目标的 `deps` 中，这相当于依赖了某些库的实现细节，非常不
  推荐。

由于Blade把头文件也完全纳入了依赖管理，对于未在任何库的 `hdrs` 或者 `src` 中声明头文件，构建结束后也会报错，如果这些头文件应当属于当前目标，
根据其是公开或者私有的，分别将其加入到 `hdrs` 或者 `srcs` 中，如果属于其他库，则应当其他库的 `hdrs` 中加入，不能包含其他库的未声明的私有头文件。
对于升级前代码库中已经存在的未声明的头文件，可以用 [cc_config.allowed_undeclared_hdrs](../config.md#cc_config) 配置项屏蔽检查。

## prebuilt_cc_library

主要用于描述一些没有源代码或者或者是通过别的构建系统已经构建好的第三方库。
除了编译和链接库本身代码的属性外，其余 `cc_library` 的属性都适用于本目标。
对应的库文件可以放在子目录中，子目录的名字通过 `libpath_pattern` 属性设置。

属性：

- `libpath_pattern` : str
  库文件所在的子目录名。默认使用 `cc_library_config.prebuilt_libpath_pattern` 配置。
  本属性是一个可替换的字符串模式，因此可以同时描述多个目标平台的库，比如不同 CPU 位数，等等。具体
  参见 [cc_library_config.prebuilt_libpath_pattern](../config.md#cc_library_config)，如果只构建一个平台的目标，可以只有一个目录。
  本属性可以为空，表示没有子目录（库文件就放在当前 BUILD 文件所在的目录）。

示例：

```python
prebuilt_cc_library(
    name = 'mysql',
    deps = [':mystring', '#pthread']
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

### 示例1，zlib

zlib 是最简单的 autotools 包，假设 zlib-1.2.11.tar.gz 在 thirdparty/zlib 目录下，其 BUILD 文件则是 thirdparty/zlib/BUILD：

```python
# 假设执行本规则后，会把构建好的包安装到 `build64_release/thirdparty/zlib` 下，那么头文件在 `include` 下，库文件则在 `lib` 下。
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
    install_dir = '', # 包的安装目录是 `build64_release/thirdparty/zlib`
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

### 示例2，openssl

严格说来，openssl 并非用 autotools 构建的，不过它大致兼容 autotools，他的对应 autotools configure 的文件是 Config，安装后的目录布局则兼容。
不过其头文件带包名，也就是不是直接在 `include` 下 而是在 `include/openssl` 子目录下。
假设 openssl-1.1.0.tar.gz 在 thirparty/openssl 目录下，其 BUILD 文件则是 thirdparty/openssl/BUILD：

```python
# 假设执行本规则后，会把构建好的包安装到 `build64_release/thirdparty/openssl` 下，那么头文件在 `include/openssl` 下，库文件则在 `lib` 下。
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
    install_dir = '', # 包的安装目录是 `build64_release/thirdparty/openssl`
    deps = [':openssl_build'],
)

foreign_cc_library(
    name = 'ssl',  # 库的名字为 libssl.a，在 `lib` 子目录下
    install_dir = '', # 包的安装目录是 `build64_release/thirdparty/openssl`
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

定义C++可执行文件目标：

```python
cc_binary(
    name='prstr',
    srcs=['./src/mystr_main/mystring.cpp'],
    deps=['#pthread',':lowercase',':uppercase','#dl'],
)
```

属性：

- `dynamic_link`: bool= True

  cc_binary 默认为静态编译以方便部署，静态链接了C++运行库和代码库中所有被依赖了的库。由于一些
  [技术限制](https://stackoverflow.com/questions/8140439/why-would-it-be-impossible-to-fully-statically-link-an-application)，glibc并不包含在内，虽然
  也可以强行静态链接glibc，但是有可能导致运行时出错。

  如果希望动态链接可执行文件依赖的库，可以使用此参数指定，此时被此target依赖的所有库都会自动生成对应的动态库供链接。这能有效地减少磁盘空间占用，但是
  程序启动时会变慢，一般仅用于非部署环境比如本地测试。

  需要注意的是，dynamic_link只适用于可执行文件，不适用于库。

- `export_dynamic`: bool = True

  常规情况下，so中只引用所依赖的so中的符号，但是对于应用特殊的场合，需要在so中引用宿主可执行文件中的符号，就需要这个选项。

  这个选项告诉连接器在可执行文件的动态符号表中加入所有的符号，而不只是用到的其他动态库中的符号。这样就使得在dlopen方式加载的so中可以调用可执行文件中
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

相当于cc_binary，再加上自动链接gtest和gtest_main。

还支持testdata参数， 列表或字符串，文件会被链接到输出所在目录 name.runfiles 子目录下，比如：testdata/a.txt => name.runfiles/testdata/a.txt

用 `blade test` 子命令，会在成功构建后到 name.runfiles 目录下自动运行，并输出总结信息。

- `testdata`: list = []

  在 name.runfiles 里建立 symbolic link 指向工程目录的文件，目前支持以下几种形式：
  - `'file'`

    在测试程序中使用这个名字本身的形式来访问

  - `'//your_proj/path/file'`

    在测试程序中用"your_proj/path/file"来访问。

  - `('//your_proj/path/file', "new_name")`

    在测试程序中用"new_name"来访问

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

## lex_yacc_library

srcs 必须为二元列表，后缀分别为ll和yy
构建时自动调用flex和bison, 并且编译成对应的cc_library

```python
lex_yacc_library(
     name = 'parser',
     srcs = [
         'line_parser.ll',
         'line_parser.yy'
     ],
     deps = [
         ":xcubetools",
     ],
     recursive = True
)
```

- `recursive`: bool =True

  生成可重入的C scanner.

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

- `prefix`: str, 生成的动态库的文件名前缀，默认为 `lib`
- `suffix`: str，生成的动态库的文件名后缀，默认为 `.so`
- `allow_undefined`: bool, 链接时是否允许未定义的符号。因为很多插件库运行时依赖宿主进程提供的符号名，链接阶段并不存在这些符号的定义。
- `strip`: bool, 是否去除调试符号信息，开启后可以减少生成的库的大小，但是无法进行符号化调试。
- `linker_scripts`: list(string)，使用链接器脚本。
  [链接器脚本](https://sourceware.org/binutils/docs/ld/Scripts.html)是用来控制链接过程的脚本。
  它的作用主要是规定如何把输入文件内的 section 放入输出文件内，并控制输入文件内各部分在程序地址空间内的布局。
  链接器有个默认的内置链接脚本，可用 `ld --verbose` 查看。此选项将会替换系统的默认链接脚本。
  链接器脚本文件的扩展名一般为 `.ld` 或者 `.lds`。
  链接器脚本通常相当复杂，如果只是想控制符号的版本和可见性，请使用下面的 `version_script` 选项。
- `version_scripts`: list(string)，使用[链接器“版本”脚本](https://sourceware.org/binutils/docs/ld/VERSION.html)。
  链接器版本脚本用来控制符号的版本及可见性，内容仅限于完整的链接脚本里 `VERSION {};` 内的部分，如果不指定版本号，那么可以只用来控制符号的可见性。
  链接器版本脚本文件的扩展名一般为 `exp`、`sym`、`.ver` 或者 `.map`。

`prefix` 和 `suffix` 控制生成的动态库的文件名，假设 `name='file'`，默认生成的库为 `libfile.so`，设置`prefix=''`，则变为 `file.so`。

### 控制动态库中符号的可见性

要控制链接结果中符号是否对外可见，可以通过[源代码中的GCC 扩展属性或者命令行选项](https://gcc.gnu.org/wiki/Visibility)来进行。

用链接器版本文件，则可以在链接时控制或者覆盖源代码中的可见性设置：

```ld
{
global:  # 全局可见
    # 支持通配符
    Name1;
    _Name2*;
    extern "C++" {  # C++ 符号
        # 引号内的表示不匹配通配符
        "a()";
        "a(int)";
        "operator<<(std::ostream&, B const&)";

        # 引号外的匹配通配符
        B::*;
        typeinfo?for?magic::*;
        vtable?for?magic::*;"
    };
local:  # 其余为局部符号，对外不可见
    *;
};
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

## resource_library

把数据文件编译成静态资源，可以在程序中中读取。

我们经常会遇到过部署一个可执行程序，还需要附带一堆辅助文件才能运行起来的情况。

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

在程序中使用时以完整路径包含进来即可使用。需要包含 static_resource.h（带上相对于BLADE_ROOT的路径）和"common/base/static_resource.h"，
用 STATIC_RESOURCE 宏来引用数据：

```c
StringPiece data = STATIC_RESOURCE(poppy_static_favicon_ico);
```

STATIC_RESOURCE 的参数是从BLADE_ROOT目录开始的数据文件的文件名，把所有非字母数字和下划线的字符都替换为_。

得到的 data 在程序运行期间一直存在，只可读取，不可写入。

用 static resource 在某些情况下也有一点不方便：就是不能在运行期间更新，因此是否使用，需要根据具体场景自己权衡。

## cu_library

使用nvcc编译器编译包含CUDA代码的C++ library

语法和 `cc_library` 基本一致，额外添加两个属性 `cuda_path` 和 `extra_cuflags` 。  
`cuda_path` 指向cuda的工作区绝对路径，一般为当前仓库内置的cuda目录，可以摆脱对本地cuda环境的依赖。对应的cuda的binary `{cuda_path}/bin/nvcc` 和include目录 `{cuda_path}/include` 都会自动识别，下面介绍的环境变量指定cuda相关路径信息也会被直接忽略。  
`extra_cuflags` 添加仅cuda的参数，和cc通用的flag依然保存在 `extra_ccflags`。


编译cu_library需要使用 `NVCC` 环境变量指向 `nvcc binary` ，例如 `NVCC=/usr/local/cuda/bin/nvcc blade build`。  
使用 `CUDA_PATH` 环境变量指向本地cuda的安装路径，`CUDA_PATH/include` 和 `{CUDA_PATH}/samples/common/inc` 会自动加到include search path。

作用优先级: `cuda_path` > `NVCC`/`CUDA_PATH` 。

```python
cu_library(
    name = 'template_gpu',
    srcs = ['template_gpu.cu'],
    hdrs = [],
    # cuda_path = '//thirdparty/cuda',
)
```

## cu_binary

使用nvcc编译器编译包含CUDA代码的C++ binary

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

使用nvcc编译器编译包含CUDA代码的C++ UT

语法同 `cc_test` ，命令环境变量参考 `cu_library`

```python
cu_test(
    name = 'cu_test',
    srcs = ['cu_test.cu'],
    deps = [':template_cpu'],
    # cuda_path = '//thirdparty/cuda',
)
```
