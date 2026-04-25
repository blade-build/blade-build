# Workspace

Blade requires that the project source code have an explicit root directory. The #include path in C++ also needs to be written from this directory. This directory becomes a workspace, which has several advantages:

* Effectively avoid problems caused by the duplicate name of the header file.
* Effectively avoid the duplicate name of the library file.
* It is easier to find the files you need.
* Improve build speed.

Considering that many old projects do not write include paths in this way, we provide a [auxiliary script](../../tool/fix-include-path.sh) to assist you in this transformation.

Blade does not read this information from a configuration file or environment variable, because developers often need to have multiple workspaces at the same time.
The way the Blade gets the current workspace is to look up the BLADE_ROOT file from the current directory no matter which level of the subdirectory it is currently running from. The directory with this file is the workspace.

In the development mode of a single code base, BLADE_ROOT is recommended to be unified in the code base. In the multi-warehouse development mode, you may need to create it yourself.

```console
touch BLADE_ROOT
```

Finally, a workspace looks like this:

```console
$ ls -1
BLADE_ROOT
common
thirdparty
xfs
xcube
torca
your_project
...
```
