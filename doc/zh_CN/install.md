# 安装

## 自动安装

在终端中执行如下命令：

```console
curl https://blade-build.github.io/install.sh | bash
```

Blade 就会被下载到 `~/.cache/blade-build` 目录下。它还会创建一个 `~/bin/blade` 符号连接，这样就可以直接使用 `blade` 命令。

## 手动安装

下载代码仓库后，执行 `install` 脚本即可安装到 `~/bin` 下，install 后不能删除checkout出来的原始目录。

Blade 用 ninja 做后端，还需要安装ninja。
Blade 支持 Python 2.7.x 和 Python 3.6+（其中 Python 3.x 在 3.6 和 3.9 上测试通过），将来会逐步停止对 Python 2.7 的支持。

install使得可以在任何目录下直接执行：

```bash
$ blade
usage: blade [-h] [--version] {build,run,test,clean,query,dump} ...
blade: error: too few arguments
Blade(error): Failure
```

命令。
如果不行，确保~/bin在你的PATH环境变量里，否则修改 ~/.profile，加入

```bash
export PATH=~/bin:$PATH
```

然后重新登录即可。
