# Development

## How It Works

### Loading Configuration

After the Blade starts, it will try to load the configuration files in multiple paths through the `execfile` function. These configuration files are all Python source files, and the predefined configuration functions in the blade are called.
Update the configuration item to the configuration dict of blade.config for later use.

After the configuration file is loaded, the blade will also try to update the options in the command line options with the same name as global_config to the configuration, so that the configuration information from the command line has the highest priority.

### Loading BUILD files

Blade will be expanded from the build target specified by the command line, and the `BUILD` file will be executed one by one through the `execfile` function. When the code in the BUILD file is executed,
The predefined rule function inside the blade is called to register the target in the data structure inside the blade.

For targets that are directly or indirectly dependent on the target specified in the command line, the blade will load the BUILD file in the corresponding directory until all dependencies are loaded.

### Dependency Analysis

The Blade starts the topological sorting of the loaded target from the root specified by the command line, and obtains a list of targets to be built and the correct build order.

### Generating backend build files

After the Blade gets the target list to be built, it can gradually generate the target action of the corresponding build rule according to each target, and output it to the backend build script file.

### Executing the backend build system

Blade calls the backend build tool to perform the actual build, and after the execution is complete, deletes the backend build script file.

### Running tests

From the command line collected test target list, build execution environment test one by one, Blade supports multi-task concurrent test, then the background will be multiple threads to execute the test file.
After all tests have been performed, collect the test results and output a report.

## How To Contribute

Welcome to contribute code to Blade! Whether it is a bugfix or a feature. Large features can be mentioned first to avoid repeated iterations caused by poor communication.

### Pull Code

Modify and test with github's Fork function fork to your own repository.

### Modifying a File

We follow the Google Python code style and modify the code to check the code with pylint.

### Test Verification

In the source code development directory, Blade first runs the code in development. You can perform src/test/runalltests.sh for global verification.

### Commissioning and Diagnostics

Most subcommands support the `--stop-after` option. The optional parameters are {load, analyze, generate, build}, which can control the blade to end after the completion phase. such as

```bash
blade build --stop-after generate generate
```

This makes the blade end after generating the backend build system description file (such as `build.ninja`), which can be used to check the generated file.

### Performance Analysis

Most subcommands support the `--profiling` option, which outputs a performance analysis report after the blade ends. If you need a more detailed analysis, you can turn the blade.pstats left by the performance analysis into a map.

Combined with the --stop-after option, it can be used to analyze performance at different stages.

### Distribute

The `dist_blade` in the root directory of the code can be packaged into a zip for easy deployment, and can be placed together with the `blade`bash script and `blade.conf` in the same directory.

### Pull Request

After the code is modified locally, push to your own github repository and you can initiate a Pull Request to us. We will review quickly, but due to busy work, time is not guaranteed.
It's a good idea to check the code style to make sure that there are unnecessary and redundant comments to avoid unnecessary reviews.

## Other Information

There are also two other netizens' analysis of Blade's implementation principle, which is based on the earlier version of Blade. Although it is somewhat outdated, it still has reference value.

* [On the design and implementation of C++Build in Blade](https://tsgsz.github.io/2013/11/01/2013-11-01-thinking-in-design-of-blade-cpp-build/)
* [Where is the sharp blade in the end](http://blog.sina.com.cn/s/blog_4af176450101bg69.html)
