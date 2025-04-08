" This is the Vim syntax file for Blade.
" Author: Yafei Zhang <kimmyzhang@tencent.com>

if version < 600
    syntax clear
elseif exists("b:current_syntax")
    finish
endif

" Read the python syntax to start with
if version < 600
    so <sfile>:p:h/python.vim
else
    runtime! syntax/python.vim
    unlet b:current_syntax
endif

syn case match

" Keywords
" NOTE: Please keep alphabatical order

" Global
syn keyword bladeTarget global_config
syn keyword bladeArg backend_builder
syn keyword bladeArg build_jobs
syn keyword bladeArg build_path_template
syn keyword bladeArg debug_info_level
syn keyword bladeArg default_visibility
syn keyword bladeArg duplicated_source_action
syn keyword bladeArg glob_error_severity
syn keyword bladeArg legacy_public_targets
syn keyword bladeArg restricted_dsl
syn keyword bladeArg run_unrepaired_tests
syn keyword bladeArg test_jobs
syn keyword bladeArg test_timeout
syn keyword bladeArg unrestricted_dsl_dirs

" C/C++
syn keyword bladeTarget cc_config
syn keyword bladeArg allowed_undeclared_hdrs
syn keyword bladeArg arflags
syn keyword bladeArg benchmark_libs
syn keyword bladeArg benchmark_main_libs
syn keyword bladeArg c_warnings
syn keyword bladeArg cflags
syn keyword bladeArg cppflags
syn keyword bladeArg cxx_warnings
syn keyword bladeArg cxxflags
syn keyword bladeArg extra_incs
syn keyword bladeArg hdr_dep_missing_severity
syn keyword bladeArg hdr_dep_missing_suppress
syn keyword bladeArg linkflags
syn keyword bladeArg optimize
syn keyword bladeArg ranlibflags
syn keyword bladeArg secretcc
syn keyword bladeArg warnings

syn keyword bladeTarget cc_library_config
syn keyword bladeArg generate_dynamic
syn keyword bladeArg hdrs_missing_severity
syn keyword bladeArg hdrs_missing_suppress
syn keyword bladeArg prebuilt_libpath_pattern

syn keyword bladeTarget cc_binary_config
syn keyword bladeArg extra_libs
syn keyword bladeArg run_lib_paths

syn keyword bladeTarget cc_test_config
syn keyword bladeArg dynamic_link
syn keyword bladeArg gperftools_debug_libs
syn keyword bladeArg gperftools_libs
syn keyword bladeArg gtest_libs
syn keyword bladeArg gtest_main_libs
syn keyword bladeArg heap_check
syn keyword bladeArg pprof_path

syn keyword bladeTarget link_config
syn keyword bladeArg link_jobs

syn keyword bladeTarget cuda_config
syn keyword bladeArg cuflags

" Java
syn keyword bladeTarget java_config
syn keyword bladeArg java_home
syn keyword bladeArg fat_jar_conflict_severity
syn keyword bladeArg maven
syn keyword bladeArg maven_central
syn keyword bladeArg maven_download_concurrency
syn keyword bladeArg maven_jar_allowed_dirs
syn keyword bladeArg maven_jar_allowed_dirs_exempts
syn keyword bladeArg maven_snapshot_update_interval
syn keyword bladeArg maven_snapshot_update_policy
syn keyword bladeArg source_encoding
syn keyword bladeArg source_version
syn keyword bladeArg target_version
syn keyword bladeArg version
syn keyword bladeArg warnings

syn keyword bladeTarget java_binary_config
syn keyword bladeArg one_jar_boot_jar

syn keyword bladeTarget java_test_config
syn keyword bladeArg coverage_reporter
syn keyword bladeArg jacoco_home
syn keyword bladeArg junit_libs

" Scala
syn keyword bladeTarget scala_config
syn keyword bladeArg scala_home
syn keyword bladeArg source_encoding
syn keyword bladeArg target_platform
syn keyword bladeArg warnings

syn keyword bladeTarget scala_test_config
syn keyword bladeArg scalatest_libs

" Go
syn keyword bladeTarget go_config
syn keyword bladeArg go
syn keyword bladeArg go_home

" Thrift
syn keyword bladeTarget thrift_config
syn keyword bladeTarget thrift_library_config
syn keyword bladeArg thrift
syn keyword bladeArg thrift_libs
syn keyword bladeArg thrift_incs

syn keyword bladeTarget fbthrift_config
syn keyword bladeTarget fbthrift_library_config
syn keyword bladeArg fbthrift1
syn keyword bladeArg fbthrift2
syn keyword bladeArg fbthrift_libs
syn keyword bladeArg fbthrift_incs

" Protobuf
syn keyword bladeTarget proto_library_config
syn keyword bladeArg protobuf_go_path
syn keyword bladeArg protobuf_incs
syn keyword bladeArg protobuf_cc_warning
syn keyword bladeArg protobuf_java_incs
syn keyword bladeArg protobuf_java_libs
syn keyword bladeArg protobuf_libs
syn keyword bladeArg protobuf_path
syn keyword bladeArg protobuf_php_path
syn keyword bladeArg protobuf_python_libs
syn keyword bladeArg protoc
syn keyword bladeArg protoc_direct_dependencies
syn keyword bladeArg protoc_go_plugin
syn keyword bladeArg protoc_java
syn keyword bladeArg protoc_php_plugin
syn keyword bladeArg well_known_protos

syn keyword bladeTarget protoc_plugin
syn keyword bladeArg code_generation
syn keyword bladeArg name
syn keyword bladeArg path

" Other helpers
syn keyword bladeTarget build_target
syn keyword bladeArg arch
syn keyword bladeArg bits
syn keyword bladeArg is_debug

syn keyword bladeTarget load_value

if version >= 508 || !exists("did_blade_config_syn_inits")
    if version < 508
        let did_blade_config_syn_inits = 1
        command! -nargs=+ HiLink hi link <args>
    else
        command! -nargs=+ HiLink hi def link <args>
    endif

    HiLink bladeTarget   Function
    HiLink bladeArg      Special
    delcommand HiLink
endif

let b:current_syntax = "blade_config"
