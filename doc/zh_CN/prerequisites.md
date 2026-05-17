# 系统前置要求与依赖

## 必要依赖

Blade 的基本运行需要以下核心依赖：

### 操作系统支持

- **Linux：** 主流发行版（Ubuntu、CentOS、Debian 等）
- **macOS：** macOS 10.12+，并安装 Xcode Command Line Tools
- **Windows：** Windows 10/11，需安装 Visual Studio Build Tools（MSVC 工具链）
  - 建议启用**开发人员模式**（设置 → 隐私和安全性 → 开发者选项）以支持 NTFS 符号链接
  - 如未启用开发人员模式，部分功能（如 `blade-bin` 符号链接）将降级为警告并跳过

### 核心运行时依赖

- **Python：** 3.10 或更新版本
- **Ninja：** 1.8+ （作为构建后端，必需）

## 可选的性能增强

Blade 可与以下工具集成，从而提升构建性能：

- **ccache：** 3.1+，提供编译缓存加速
- **distcc：** 分布式编译，面向大规模构建场景

## 分语言的构建要求

### C/C++ 开发

- **GCC：** 4.0+ 或兼容的编译器（也支持 Clang），Linux/macOS
- **MSVC：** Visual Studio 2019/2022 Build Tools，Windows
- **标准库：** C++ 标准库开发包

### Java 开发

- **JDK：** Java Development Kit 1.6+（OpenJDK 或 Oracle JDK）
- **构建工具：** 可选的 Maven 或 Gradle，用于 Java 项目协同

### Scala 开发

- **Scala：** 2.10+，提供 Scala 语言支持
- **SBT：** 可选的 Scala 构建工具集成

### 代码生成工具

- **SWIG：** 2.0+（`swig_library` 目标必需）
- **Flex：** 2.5+（`lex_yacc` 目标必需）
- **Bison：** 2.1+（`lex_yacc` 目标必需）

## 平台相关说明

### Linux 安装

- **包管理器：** 使用系统包管理器（`apt`、`yum`、`dnf`）
- **开发工具：** 安装 `build-essential` 或等价的构建工具包
- **Python 包：** 确保 `pip` 与 `setuptools` 可用

### macOS 安装

- **Xcode：** 安装 Xcode Command Line Tools（`xcode-select --install`）
- **Homebrew：** 推荐用于包管理
- **Python：** 使用 Homebrew 提供的 Python，或系统自带 Python 配合 `pip`

### Windows 安装

- **MSVC 工具链：** 安装 [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)，勾选 "MSVC v143" 和 "Windows SDK"
- **开发人员模式：** 建议启用（设置 → 隐私和安全性 → 开发者选项 → 开发人员模式），以支持 NTFS 符号链接。未启用时 `blade-bin` 符号链接会跳过，不影响正常构建
- **Python：** 从 [python.org](https://www.python.org/downloads/) 安装 Python 3.10+
- **Ninja：** 从 [ninja-build.org](https://ninja-build.org/) 下载或通过 `pip install ninja` 安装
- **Git：** 用于版本控制集成（SCM 信息嵌入）
- **WinFlexBison** *（可选，仅 `lex_yacc_library` 目标需要）*：通过 `winget install -e --id WinFlexBison.win_flex_bison` 安装
- 将 Blade 目录加入 `PATH`，或直接使用 `blade.bat` 启动

## 版本兼容性对照表

| 组件 | 最低版本 | 推荐版本 | 备注 |
|------|----------|----------|------|
| Python | 3.10 | 3.12+ | v3 要求 Python 3.10 或更新 |
| Ninja | 1.8 | 1.10+ | 核心构建后端 |
| GCC | 4.0 | 7.0+ | 也支持 Clang 6.0+ |
| JDK | 1.6 | 11+ | 推荐使用 LTS 版本 |

## 环境校验命令

用于校验关键依赖的安装情况：

```bash
# 检查 Python 版本
python --version

# 验证 Ninja 是否安装
ninja --version

# 确认 GCC 是否可用
gcc --version

# 检查 Java 是否可用
java -version
```
