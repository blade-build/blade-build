@echo off

set python=python.exe
set blade_file=%~dp0src

%python% %blade_file% %*
