# Editor Support

## Visual Studio Code

The official **[Blade extension](https://marketplace.visualstudio.com/items?itemName=blade-build.vscode-blade)**
([source](https://github.com/blade-build/vscode-blade)) gives first-class Blade
support in VS Code:

- a **targets explorer** (directory tree) with inline **build / run / test /
  debug**, and recursive build/test of a directory (`//path/...`);
- **build / run / test / clean** through the VS Code Tasks API — compiler errors
  land in the Problems panel, and a failed build never silently runs a stale
  binary;
- a **build-profile** (release / debug) selector;
- **BUILD-file language features** — syntax highlighting, an outline of targets,
  go-to-definition on dependency labels (`//path:name`, `:name`), completion,
  hover, and diagnostics;
- one-click **C/C++ IntelliSense** via `compile_commands.json` and clangd.

Targets are read from Blade itself (`blade dump --targets`), so every rule kind
(C++, Java, Scala, Python, proto, …) is understood accurately.

Install it from the Marketplace, open a workspace that contains a `BLADE_ROOT`,
and (if `blade` is not on your `PATH`) set `blade.executable`.

## C/C++ IntelliSense in any editor

The extension's IntelliSense is built on a feature you can use from **any**
editor: Blade can emit a
[compilation database](https://clang.llvm.org/docs/JSONCompilationDatabase.html).

```bash
blade dump --compdb --to-file compile_commands.json
```

Point [clangd](https://clangd.llvm.org/) at the resulting
`compile_commands.json` and you get accurate completion, go-to-definition, and
diagnostics — in Vim, Emacs, CLion, or any [LSP](https://langserver.org/)
client. Because Blade knows the exact compile command for every translation
unit, this is more accurate than re-deriving include paths by hand.

!!! tip
    Regenerate `compile_commands.json` after adding sources or changing deps.
    The VS Code extension can do this automatically on every target refresh.
