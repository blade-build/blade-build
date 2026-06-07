# console：构建进度面板与 ninja 状态流水线

`console.py` 掌管 Blade 所有终端修饰——颜色、光标,以及实时的**构建进度面板**。
有意思的是这个面板**怎么来的**:官方 ninja 没有结构化的进度 API,所以 Blade
从 ninja 的纯文本状态流里把面板重建出来。本文讲这条流水线。

| 文件 | 作用 |
| --- | --- |
| `src/blade/console.py` | 颜色、光标、进度面板渲染 + 擦除路径 |
| `src/blade/ninja_runner.py` | 运行 ninja、捕获输出、解析状态流 |
| `src/blade/ninja_rule.py` | `NinjaRule.emit()`——把(带色的)`description` 烤进每条 rule |
| `src/blade/gen_rule_target.py`、`src/blade/windows_resources_target.py` | 每目标本地 rule;须自己给 `description` 上色 |

## 1. 为什么解析 ninja 的 stdout（而不是事件 API）

上游 ninja **没有**结构化进度通道。protobuf 的「frontend」接口(ninja PR #1210)
从未合入主线,为它单独绑一个 fork + protobuf 依赖不值当。所以唯一的实时信号
就是 ninja 的状态文本。

关于这段文本的两个事实(见 ninja `src/status_printer.cc`)决定了设计:

- **智能终端**:ninja 在 edge *开始*和*结束*各打一行状态,用 `\r` 原地覆盖,
  并把最后一行留屏——这就是 Blade 以前残留的 `[226/226] LINK …`。
- **管道 / dumb**(Blade 用的):ninja **只在 edge 结束时**打印,每完成一条一行、
  以换行结尾;出错另有 `FAILED:` / `ninja: …` 块。edge *开始*不打印。

所以 Blade 一旦用管道,就得到一条干净可解析的流:每完成一条一行
`[finished/total](running) <desc>`,外加独立的报错块。格式由
`NINJA_STATUS='[%f/%t](%r) '` 固定(`%f`/`%t`/`%r` = 完成/总数/在跑)。因为
dumb 模式只在结束时打印,Blade 能显示在跑的**数量**(`%r`),却拿不到**是哪几条**
在跑——逐个在跑任务的身份需要(不可用的)frontend 协议。

## 2. 两种运行模式（`ninja_runner._run_ninja_build`）

- **verbose**(`-v`):把终端直接交给 ninja(`_run_ninja_command`),完整打印每条
  命令。无面板。
- **其它**(默认 + quiet):把 ninja 的 stdout+stderr 重定向到
  `blade-bin/ninja_output.log`,用 `_show_progress` 追读。重定向正是让 ninja 进入
  dumb 模式、给出上面那条「只在结束时」的流。

## 3. 解析循环（`ninja_runner._show_progress`）

单个读取循环对每行分类:

- 匹配 `^\[(\d+)/(\d+)\]\((\d+)\)\s+(.*)$` → 一条完成的 edge:更新
  完成/总数/在跑,把描述压入有界的 `deque(maxlen=_PANEL_MAX_RECENT)`,算出 ETA,
  调 `console.render_build_panel(...)`。(`%r` 减一——ninja 在给在跑计数减一之前
  就打印了正在结束的这条。)
- 其它 → `console.output(line)`:**永久**行(警告、错误、`ninja: …`)。保留前导缩进。
- 退出时:擦掉面板;干净成功则打印 `"<N> build steps completed"` 取代面板——
  不留 `[N/N]` 残行。

## 4. 瞬态面板 vs 永久输出

整个设计建立在一个区分上:

- **面板**是*瞬态*的——它待在屏幕底部,原地重绘 / 擦除。
- 其它都是*永久*的——带换行打印,滚上去并留住。

`console.output()` → `_do_print()` 会在打印**之前**调 `_clear_progress_bar_locked()`。
所以报错/警告一到,先擦掉面板,消息永久打印在上方,下一条进度行再在其下方重画面板。
于是**被擦的永远只是 Blade 自己的面板——真正的报错绝不会被覆盖**。这正是让
「最后一行可能是报错」不再成为问题的关键。

## 5. 渲染面板（`console.render_build_panel`）

面板是一组行:表头(进度条)+ 最近完成窗口。原地绘制:

- 记 `_region_height` = 当前在屏行数。
- 重绘:光标上移 `_region_height` 行(`\033[{n}A`),再 `\r\033[J`(回车 +
  清到屏幕末尾)擦掉旧面板及其下方一切,然后打印新行,并把光标停在面板*下方*的
  空行——这样下次重绘正好上移 `_region_height`。
- 面板在屏时隐藏光标(`_hide_cursor_locked`),并在擦除时及 `atexit` 钩子里恢复,
  所以被中断的构建不会留下没有光标的终端。
- 重绘有节流(`_PROGRESS_REFRESH_INTERVAL`),但最后的 100% 帧一定画。

擦除路径是统一的:`_clear_progress_bar_locked()` 在 `_region_height > 0` 时擦多行
面板,否则擦单行进度条(`\r` + 清到行尾)。两者都会重新显示光标。

## 6. 三段灰度进度条（`console._tri_state_bar`）

`%f`/`%r`/`%t` 给出三段:**已完成**、**进行中**、**未开始**
(`total - finished - running`)。进度条用三档灰度——亮 / 中 / 暗
(`\033[38;5;{252,245,238}m` 的方块字符)——一眼看出构建状态。段宽用**累积取整**,
保证三段之和恒等于条宽:

```python
done_w = width * finished // total
run_w  = width * (finished + running) // total - done_w
rem_w  = width - done_w - run_w
```

无颜色时退回三种可辨的方块字符(`█` / `▒` / `░`)。条宽按「表头一行放得下」来定
(`finished/total pct% ·running running  ETA …`),最近窗口的行按终端宽度截断——
两者都重要,因为一旦折行就会打乱「上移 N 行」的计算。

## 7. rule 的 description 在生成期就上好色

`[N/N]` 后面显示的是 rule 的 ninja `description`,由 ninja 展开。颜色是
**在生成 ninja 文件时**烤进那个字符串的,而非打印时:`NinjaRule.emit()` 用
`console.colored(desc, 'dimpurple')` 包起来(颜色关闭时返回纯文本)。每目标的
*本地* rule 必须照做,否则它在面板里没颜色、而其它步骤都有色——这就是
`gen_rule` 和 `windows_resources`(`RC` rule)要给自己的 `description` 上色的原因。

## 8. 退化

- **非 TTY / 重定向**(`_cursor_control` 为假):`render_build_panel` 直接空操作——
  不往管道/日志里漏控制码;只出现永久行 + 汇总。
- **颜色关闭**(`_color_enabled` 为假):进度条用方块字符档位,描述为纯文本。
- **quiet**(`is_quiet()`):去掉最近完成窗口——只显示聚合进度条,不显示逐条描述。
- **verbose**:完全没有面板;ninja 独占终端。
