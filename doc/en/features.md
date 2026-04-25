# Features

* Source file updates cause a rebuild. This gnu make can be solved very well.
* The build command is complex, and the developer may need to understand the command line and various parameters.
* The header file is updated, so the source files that depend on this header file need to be rebuilt. This gnu make is not directly supported and needs to be used with gcc to generate and update dependencies.
* Library file update, after the library file depends on the update, the program should be reconnected, GNU Make can do it.
* Even if I only build my own target, if the source code of the library changes, the library should be regenerated, and GNU Make can't do it with Recursive Make.
* Dependencies between library files are automatically passed, one library depends on another library, and the end users of the library don't need to care.
* Warnings and errors during the build process should be prominently displayed.
* It can automatically support the proto buffer used by the typhoon system in a large amount, and it is convenient to expand to support new tools that may be introduced by foreigners.
* Should be able to integrate automatic testing, code checking and other commonly used functions.
