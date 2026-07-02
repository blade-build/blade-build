# Build Functions

Some Functions can be called in BUILD files.

## glob

```python
glob(include, exclude=[], allow_empty=False)
```

Glob is a helper function that finds all files that match certain path patterns in the source dir, and returns a list of their paths.
Patterns may contain shell-like wildcards, such as * , ? , or [charset]. Additionally, the path element '**' matches any subpath.
You can use `exclude` to exclude some files.

Example:

```python
...
    srcs = glob(['*.java', 'src/main/java/**/*.java'], exclude=['*Test.java'])
...
```

Usually, it is an error for glob to return an empty result, but you can specify `allow_empty=True` to eliminate this error if it is surely you expected.

## fail

```python
fail(*args, sep=' ')
```

Aborts loading the current `BUILD` (or extension) file with a fatal,
source-located error. Use it to reject invalid input — it is how a `BUILD` file
raises a hard error (the sandbox has no `assert` / `raise`). Positional args are
joined by `sep`.

Example:

```python
if len(srcs) != 1:
    fail('this rule accepts exactly one source, got', len(srcs))
```
