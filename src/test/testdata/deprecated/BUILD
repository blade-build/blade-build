# Fixtures for the deprecated-dependency warning test (#667).
py_library(name = 'new', srcs = ['new.py'])

# A deprecated library; its first dep is suggested as the replacement.
py_library(name = 'old', srcs = ['old.py'], deps = [':new'], deprecated = True)

# Depends on the deprecated library -> should trigger a warning.
py_library(name = 'user', srcs = ['user.py'], deps = [':old'])
