# Build Cache

## Incremental build

Blade build is incremental and will only build the appropriate targets and their dependencies if they need to be updated. `clean` is usually not needed.

## CCache

Blade supports [ccache](https://ccache.dev/), which can greatly speed up the rebuild.

If multiple developers share one develop machine, they can improve cache hit rate by sharing the same build cache to.
Please refer to [related documents](https://ccache.dev/manual/3.7.9.html#sharing_a_cache), we also provide a [auxiliary tool](../../tool/setup-shared-ccache.py) for easy setup it.
