# 编辑器支持

## Visual Studio Code

官方 **[Blade 扩展](https://marketplace.visualstudio.com/items?itemName=blade-build.vscode-blade)**
（[源码](https://github.com/blade-build/vscode-blade)）为 VS Code 提供一流的 Blade
支持：

- **目标浏览器**（目录树），带行内 **构建 / 运行 / 测试 / 调试**，并可递归构建/测试
  某个目录（`//path/...`）；
- 通过 VS Code Tasks API 的 **构建 / 运行 / 测试 / 清理** —— 编译错误会出现在“问题”
  面板中，构建失败也不会误运行旧的可执行文件；
- **构建配置**（release / debug）切换；
- **BUILD 文件语言特性** —— 语法高亮、目标大纲、对依赖标签（`//path:name`、
  `:name`）的跳转到定义、补全、悬停与诊断；
- 借助 `compile_commands.json` 与 clangd 的一键 **C/C++ 智能感知**。

目标信息读取自 Blade 本身（`blade dump --targets`），因此每一种规则（C++、Java、
Scala、Python、proto……）都能被准确理解。

从应用市场安装，打开一个包含 `BLADE_ROOT` 的工作区；若 `blade` 不在 `PATH` 中，
设置 `blade.executable` 即可。

## 在任意编辑器中获得 C/C++ 智能感知

扩展的智能感知建立在一个你可以在**任意**编辑器中使用的能力之上：Blade 能生成
[编译数据库](https://clang.llvm.org/docs/JSONCompilationDatabase.html)。

```bash
blade dump --compdb --to-file compile_commands.json
```

让 [clangd](https://clangd.llvm.org/) 指向生成的 `compile_commands.json`，即可在
Vim、Emacs、CLion 或任意 [LSP](https://langserver.org/) 客户端中获得准确的补全、
跳转到定义与诊断。由于 Blade 知道每个翻译单元的精确编译命令，这比手动推导 include
路径更准确。

!!! tip
    新增源文件或改动依赖后，请重新生成 `compile_commands.json`。VS Code 扩展可在
    每次刷新目标时自动完成这一步。
