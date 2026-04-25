# 缓存系统

## 增量构建

Blade 构建是增量，只有需要更新时才会去构建相应的目标及其依赖。clean 通常是不需要的。

## 专用构建缓存系统

blade 支持 ccache，可以大幅度加快重新构建速度。Blade 能检查到安装了 ccache 并自动启用，通常无需配置。
如果通过配置 CCACHE_DIR 环境变量指定 ccache 目录，同一个用户的相同代码库的多个 workspace 或者多个用户之间就可以共享构建 cache。
具体请参阅[相关文档](https://ccache.dev/manual/3.7.9.html#_sharing_a_cache)，我们也提供了一个[辅助工具](../../tool/setup-shared-ccache.py)以方便设置。
