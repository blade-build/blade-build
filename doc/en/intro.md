# What is Blade

Software projects use a variety of tools to build code, the most common is probably GNU Make. However, although GNU Make has its own functions, it is difficult to use it directly.

Many people still write Makefiles by hand, and they don't write the correct dependencies, which makes them feel clean every time they have to make clean, and the meaning of Make is greatly reduced.
This is no problem under the small projects of several files, and it is very inconvenient for large projects.

Autotools is called auto, but it still needs to write a lot of things manually. Running a series of commands is still more complicated, and the threshold for developers to learn and use is very high.

Blade is aimed at these issues, and is the ["Typhoon" cloud computing platform of Tencent's Infrastructure Department](http://storage.it168.com/a2011/1203/1283/000001283196.shtml)
The new generation of build tools developed by the project hopes to become the "Swiss Army Knife" in the hands of developers. We are now open sourced out, hoping to make more people more convenient.
