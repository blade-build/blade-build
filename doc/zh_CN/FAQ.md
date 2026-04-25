# Blade 常见问题

## 运行环境问题

### 平台兼容性问题

**现象：** Blade 在目标平台无法执行，报 syntax error。

**排查流程：**

Blade 运行需要 Python 2.7 或 Python 3.6+。请先确认 Python 安装：

```bash
python -V  # 查看 Python 版本
```

**排查步骤：**

1. **版本确认：** 即便已安装 Python 2.7 仍然报错，先确认 `python -V` 实际看到的版本是否为预期版本
2. **PATH 环境：** 必要时调整 `PATH` 环境变量，或重新登录终端使配置生效
3. **解释器定位：** 使用 `env python` 或 `which python` 查看当前实际调用的 Python 解释器

### Vim 打开 BUILD 文件无语法高亮

**问题：** 在 Vim 中编辑 BUILD 文件时没有语法高亮。

**排查清单：**

1. **安装确认：** 确认 Blade 安装流程已完整执行
2. **语法文件检查：** 检查 `~/.vim/syntax/blade.vim` 是否存在，且指向正确的文件
3. **配置确认：** 确认 `~/.vimrc` 中包含：`autocmd! BufRead,BufNewFile BUILD set filetype=blade`

**进一步处理：** 若上述步骤都无效，请联系 Blade 团队获取支持。

### Alt 键功能异常

**问题：** Alt 键的功能未按预期工作。

**解决方案：**

1. **重新安装：** 重新执行一次 Blade 安装流程
2. **PATH 配置：** 将 `~/bin` 加入用户 profile，并重新登录

**说明：** 这类问题通常源于终端模拟器的配置，而非 Blade 本身。

## 构建系统问题

### 依赖顺序不同，编译结果不同

**现象：** `deps` 中的依赖顺序影响编译结果。例如 `//common/config/ini:ini` 在依赖列表中的位置不同，编译结果也不同。

**根因分析：**

1. **预编译库干扰：** 编译错误提示依赖之间夹着一个 `su.1.0` 预编译库
2. **行为差异：** `//common/config/ini:ini` 在 `su.1.0` 前后位置不同，编译行为不同
3. **依赖分析：** `su.1.0` 实际依赖 `//common/config/ini:ini`，但并未把该库打进其静态库
4. **符号解析失败：** 当 `//common/config/ini:ini` 放在 `su.1.0` 之后时，GCC 按顺序查找符号的机制找不到引用，于是报 undefined reference

**最佳实践：**

- **优先源码构建：** 尽量采用源码方式构建项目
- **最小化预编译库：** 控制预编译库的使用范围，确保其已包含完整依赖
- **依赖校验：** 使用预编译库时务必校验依赖关系

### ccache 疑似缓存了错误信息

**现象：** 源文件已经修改，重新编译仍然报同样的错误，怀疑是 ccache 缓存了警告或错误信息。

**排查过程：**

1. **文档核对：** 查阅 ccache 文档，direct mode 可能出现 internal error
2. **隔离验证：** 必要时调整配置重试，排除是否是缓存自身的问题
3. **预处理检查：** 查看预处理后的 `.cpp` 文件，发现头文件的修改并未反映在预处理结果中
4. **路径定位：** 原来 `build64_release` 目录下存在同名头文件，与源码目录冲突
5. **包含路径顺序：** 默认的 `-Ibuild64_release -I.` 顺序会优先使用 `build64_release` 中的头文件
6. **冲突根因：** 同事在输出目录里放了文件，而修改实际发生在项目源文件中

**解决方案：**

- **检查包含路径：** 严格审查 include path 的配置
- **构建目录管理：** 严格隔离源代码目录与构建输出目录
- **缓存失效策略：** 发生路径冲突时，适当地让 ccache 失效

### 手里只有不带源码的库，如何使用

**场景：** 需要使用没有源码的预编译库。

**解决方案：** 请参考 [[#cc_library]] 中关于 prebuilt 的部分。

### 预编译库只有 `.so` 文件

**问题描述：**
预编译库只提供了 `.so` 文件，而我需要编译动态库。

**技术分析：**

1. 对于需要编译成动态库的 `cc_library` 目标，仅需提供动态库文件
2. `cc_plugin` 目标则需要静态库文件

**建议：**

- 预编译库最好同时提供静态库与动态库两种版本
- 使用最新版本的 Blade 以获得更好的兼容性

### 把静态库转换为动态库

**场景：**
只有静态库（`.a`），但需要编译出动态库（`.so`）。

**技术方案：**

静态库 `.a` 实际上是若干 `.o` 文件的归档。转换过程如下：

```bash
# 从静态库提取目标文件
ar -x mylib.a
# 使用 .o 文件生成共享库
gcc -shared *.o -o mylib.so
```

**补充说明：**

- Blade 提供了自动化脚本 `tool/atoso`
- 动态库无法反过来转换为静态库
- 对于第三方代码，建议尽量同时获取静态和动态两种版本

### 使用环境变量指定特定版本的 GCC

**需求：**
使用特定版本的 GCC 编译项目。

**实现方式：**
通过环境变量指定编译器路径：

```bash
CC=/usr/bin/gcc CXX=/usr/bin/g++ CPP=/usr/bin/cpp LD=/usr/bin/g++ blade targets
```

**最佳实践：**

- 使用最新版的 Blade
- 所有编译器相关的环境变量保持一致
- 编译器与链接器使用匹配的版本

### 代码改过之后 Blade 仍然编译报错

**问题描述：**
在 CI 机器上，Blade 报编译错误；修复后再次从 SVN 拉取代码，报错依旧。

**根因分析：**

- 检查文件修改时间，发现可能未成功覆盖
- CI 机器上原文件属主是 root，而当前同事并非 root，没有权限覆盖
- 因此报错的实际上是旧文件

**解决方案：**

- 权限切换时务必小心文件属主问题
- 确保开发环境与 CI 环境之间的文件同步

### 编译出来的 `.so` 库带有路径信息

**问题描述：**
Blade 编译出的 `.so` 库带有路径信息，使用起来较繁琐，能否通过配置修改？

**设计原理：**

在包含多个子项目的大型工程中，不同子项目之间的库完全可能重名。人工协调这种命名冲突不现实。

Blade 在库文件中嵌入路径信息，从根本上消除了命名冲突问题。使用时只需按照完整路径引用即可。

### 新加的 error flag 不生效

**问题描述：**
升级了 Blade 版本，但新加的 error flag 在编译时未生效。

**排查步骤：**

- 确认 Blade 安装已更新至最新版本
- 确认 C++ 编译器没有过滤掉相关选项
- Blade 会根据编译器是否支持选择性启用 error flag，避免编译失败
- 确认 GCC 版本是否满足新选项的最低要求

**解决方案：**

- 将 GCC 升级到支持相关 error flag 的版本

### `blade clean` 未能清理生成的文件

**问题描述：**
`blade clean` 命令未能清理项目生成的文件。

**解决方案：**

确保 `build` 与 `clean` 命令使用一致的参数：

- `blade build -prelease` 生成的文件，请使用 `blade clean -prelease` 清理
- `blade build -pdebug` 生成的文件，请使用 `blade clean -pdebug` 清理

**核实：**

仔细核对命令参数，确保两次命令能够匹配。

### 如何显示构建命令行

想查看构建过程中执行的完整命令。
在构建时加上 `--verbose` 参数，即可显示完整的命令行。

### 发布预编译库

**场景：**
有些保密的代码希望以预编译库形式发布，但同时还依赖了一些开源组件。

**原始库配置：**

```python
cc_library(
    name = 'security',
    srcs = 'security.cpp',
    hdrs = ['security.h'],
    deps = [
        '//common/base/string:string',
        '//thirdparty/glog:glog',
    ]
)
```

**发布为预编译库的配置：**

```python
cc_library(
    name = 'security',
    hdrs = ['security.h'],
    prebuilt = True,  # 以 prebuilt 替代 srcs
    deps = [
        '//common/base/string:string',
        '//thirdparty/glog:glog',
    ]
)
```

**关键注意事项：**

- 对外的头文件保持不变
- `deps` 必须完整保留
- 只发布自己有权发布的库，不要把不属于你的依赖打包进去
- 按照 `cc_library` 文档中关于 prebuilt 库的方式组织目录结构

### 出现 unrecognized options 错误

**错误示例：** `unrecognized options {'link_all_symbols': 1}`

**根因：**
不同类型的目标支持不同的参数集合。当使用某目标类型不支持的参数时，就会出现此错误。

**常见原因：**

- 在错误的目标类型上误用了参数
- 参数名拼写错误

**调试提示：**
Blade 的 Vim 语法高亮可以在编辑阶段帮助快速发现此类参数错误。

### 源文件被多个目标共用

**错误示例：**
`Source file cp_test_config.cc belongs to both cc_test xcube/cp/jobcontrol:job_controller_test and cc_test xcube/cp/jobcontrol:job_context_test`

**设计原因：**

这违反了 C++ 的[一次定义规则（ODR）](http://en.wikipedia.org/wiki/One_Definition_Rule)，而允许共用会带来以下风险：

- 不必要的重复编译
- 编译参数不一致导致的潜在问题

**最佳实践：**

每个源文件应仅归属于一个目标。若存在共享需求，请：

1. 把公共代码抽取为独立的 `cc_library`
2. 在需要的目标中通过 `deps` 引用该库
3. 保持组件之间清晰的归属边界

### 开启 C++11 支持

**配置方式：**
在配置文件中加入：

```python
cc_config(
    cxxflags='-std=gnu++11'
)
```

**版本兼容性：**

- 其他方言选项请参考 [GCC 在线文档](https://gcc.gnu.org/onlinedocs/gcc/C-Dialect-Options.html)
- 对于 C++11 标准化之前发布的 GCC 版本，可使用 `"gnu++0x"` 代替
- 较新版本的 GCC（例如 GCC 6+）默认即为 C++14，此配置可省略

### 优化磁盘空间占用

**挑战：**
采用 Blade 构建的项目往往规模较大，构建产物会占用大量磁盘空间。

**空间优化策略：**

#### 调整调试信息级别

Blade 默认会带上调试符号，便于使用 GDB 等工具进行调试；但调试符号往往是二进制文件中体积最大的部分。

**配置：**

```python
# 降低调试信息开销
global_config(
    debug_info_level = 'no'
)
```

**各级别含义：**

- `no`：不生成调试信息，二进制最小，GDB 中看不到符号
- `low`：只保留函数名和全局变量
- `mid`：标准调试级别，包含局部变量与函数参数（默认）
- `high`：最完整的调试信息，包括宏等

**权衡：** 调试级别越低，二进制体积越小，但调试能力相应减弱。

#### 启用 DebugFission

**功能：** DebugFission 将调试信息与可执行文件分离，既能减小二进制体积，又保留调试能力。

**配置参考：**

- [`cc_config.fission`](config.md#cc_config) —— 开启 DebugFission 功能
- [`cc_config.dwp`](config.md#cc_config) —— 将 `.dwo` 文件打包为 `.dwp` 调试包
- [在 package 中使用 dwp 文件](build_rules/cc.md#使用-dwp-文件) —— 将调试包纳入部署产物

#### 压缩调试信息

**思路：** 使用 GCC 的 [`-gz`](https://gcc.gnu.org/onlinedocs/gcc/Debugging-Options.html) 选项对调试信息进行压缩。

**使用策略：**

- 编译和链接阶段均可启用
- 如果只想减小最终可执行文件的体积，只在链接阶段启用即可
- 压缩/解压本身会带来一定的构建开销

**全局配置：**

```python
cc_config(
    ...
    cppflags = [..., '-gz', ...],
    linkflags = [..., '-gz', ...],
    ...
)
```

**单目标配置：**

```python
cc_binary(
    name = 'xxx_server',
    ...
    extra_linkflags = ['-gz'],
)
```

**兼容性说明：**

- 需要 [GDB 支持读取压缩的调试符号](https://sourceware.org/gdb/current/onlinedocs/gdb/Requirements.html)
- 过老的 GDB 或未编译 zlib 支持的 GDB 将无法读取压缩后的调试信息

#### 分离调试符号

**问题：** 降低调试级别或 strip 虽然能减小体积，但会影响调试能力。

**方案：** 采用[分离调试符号](https://sourceware.org/gdb/onlinedocs/gdb/Separate-Debug-Files.html)，在减小可执行文件体积的同时保留调试能力。

**收益：**

- 保留完整的调试能力
- 显著减小部署产物体积
- 便于调试符号的高效分发

**实现：** 将调试符号单独存储到独立文件中，由主可执行文件引用。

#### 测试程序使用动态链接

**配置：**

```python
cc_test_config(
    dynamic_link = True
)
```

**原理：**

- 测试程序不会发布到生产环境
- 动态链接可以显著减少磁盘占用
- 对于需要静态链接的个别测试，可单独设置 `dynamic_link = False`

**收益：**

- 测试产物的磁盘空间显著节省
- 链接耗时降低，构建更快
- 针对特定测试仍可灵活配置

#### 生成 thin 静态库

**能力：** GNU ar 支持生成「thin」类型的静态库。与常规静态库不同，它只记录 `.o` 文件的路径，而不打包实际内容。

**收益：**

- 显著降低磁盘占用
- 保持构建系统的效率

**局限：**

- 不适合对外发布
- 与 Blade 内部使用的库形态兼容

**配置：**

```python
cc_library_config(
    arflags = 'rcsT'  # 加上 'T' 标志以生成 thin 静态库
)
```

**适用场景：** 构建系统内部使用、无需外部分发的静态库。

### `cannot find -lstdc++`

**错误：** `cannot find -lstdc++`

**解决方案：** 安装 libstdc++ 的静态版本：

```bash
yum install libstdc++-static
```

**背景：** 为了部署方便，Blade 选择静态链接 libstdc++（以及 libgcc），这与 Go 等新兴语言的策略一致；某些系统默认未安装对应的静态库。

### `g++: Fatal error: Killed signal terminated program cc1plus`

**错误：** `g++: Fatal error: Killed signal terminated program cc1plus`

**根因：** 系统资源不足，Blade 自动计算的默认并发数超过机器承载能力。

**解决方案：** 通过 `-j` 选项降低并行任务数：

```bash
blade build -j4  # 在 8 核机器上使用 4 个并行任务
```

**建议：** 结合可用内存与 CPU 资源合理设置并行度，避免 OOM。

### `No space left on device`

**错误：** `No space left on device`

**可能原因：**

- 构建输出目录的磁盘空间不足
- 临时目录空间不足

**解决方案：**

- 清理构建产物与临时文件
- 通过 [TMPDIR](https://gcc.gnu.org/onlinedocs/gcc/Environment-Variables.html) 环境变量指定其他临时目录

**预防：** 大规模构建期间持续监控磁盘使用，并引入自动化清理策略。

### 忽略带有外部构建文件的目录

**场景：** 跳过包含其他构建系统（例如 Bazel）配置文件的目录。

**方案：** 在目标目录中放置一个空的 `.bladeskip` 文件。

**效果：** Blade 会排除该目录及其全部子目录。

**适用场景：** 混合构建系统环境的管理、排除构建规则不兼容的第三方代码。
