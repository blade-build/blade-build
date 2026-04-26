# 安装指南

## 自动安装

在终端中执行以下命令即可自动安装 Blade：

```console
curl https://blade-build.github.io/install.sh | bash
```

**安装流程：**

- **源码下载：** Blade 会被克隆到 `~/.cache/blade-build`
- **创建符号链接：** 在 `~/bin/blade` 创建符号链接
- **命令生效：** 系统范围内即可使用 `blade` 命令

## 手动安装

### 安装方式

执行安装脚本，将 Blade 安装到 `~/bin` 下：

**安装特点：**

- **符号链接方式：** 采用符号链接以便灵活更新
- **保留源目录：** 原始 checkout 目录必须保留，不能删除
- **构建后端依赖：** 需要 [Ninja](https://ninja-build.org/) 作为构建后端

### 支持的 Python 版本

**支持的版本：**

- **Python 3.10+：** 最低要求版本（在 3.10 到 3.14 上测试）

更老的版本（Python 2.7 及 3.10 之前的 Python 3）Blade v3 已不再支持。如需在遗留环境中使用，请使用 `2.x` LTS 分支。

## 安装后验证

### 命令执行测试

不带参数运行 Blade，以验证安装是否成功：

```bash
$ blade
usage: blade [-h] [--version] {build,run,test,clean,query,dump} ...
blade: error: too few arguments
Blade(error): Failure
```

### PATH 配置

如果提示命令找不到，请确认 `~/bin` 已加入 `PATH` 环境变量。

在 `~/.profile` 中加入下面一行：

```bash
export PATH=~/bin:$PATH
```

**生效方式：** 重新登录或重启终端会话

## 系统需求

### 必需依赖

- **Ninja：** 用作构建后端
- **Python 解释器：** Python 3.10 或更新版本
- **开发工具链：** 标准 C/C++ 工具链（GCC 或 Clang）

### 可选依赖

- **ccache：** 通过缓存加速构建
- **argcomplete：** 提供增强的命令行补全

## 故障排查

### 常见问题

- **命令未找到：** 检查 `PATH` 配置与符号链接是否创建成功
- **权限错误：** 确认 `~/bin` 目录拥有合适的权限
- **Python 版本冲突：** 确认系统中存在兼容的 Python 版本

### 支持资源

- **文档：** 参考 Blade 文档中的详细排错章节
- **社区支持：** 在 GitHub Issues 中寻求社区帮助
- **版本兼容性：** 在安装前核对特定版本的前置要求
