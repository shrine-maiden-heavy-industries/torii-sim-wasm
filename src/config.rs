// SPDX-License-Identifier: BSD-2-Clause

use std::path::PathBuf;

use pyo3::prelude::*;

#[pyclass(eq, eq_int)]
#[derive(PartialEq, Clone)]
#[allow(non_camel_case_types, clippy::upper_case_acronyms)]
pub enum Backend {
    WINCH,
    CRANELIFT,
}

impl From<::wasmtime::Strategy> for Backend {
    fn from(value: ::wasmtime::Strategy) -> Self {
        match value {
            ::wasmtime::Strategy::Cranelift => Backend::CRANELIFT,
            _ => Backend::WINCH,
        }
    }
}

#[pyclass(eq, eq_int)]
#[derive(PartialEq, Clone)]
#[allow(non_camel_case_types, clippy::upper_case_acronyms)]
pub enum OptLevel {
    NONE,
    SPEED,
    SPEED_AND_SIZE,
}

impl From<::wasmtime::OptLevel> for OptLevel {
    fn from(value: ::wasmtime::OptLevel) -> Self {
        match value {
            ::wasmtime::OptLevel::None => OptLevel::NONE,
            ::wasmtime::OptLevel::Speed => OptLevel::SPEED,
            ::wasmtime::OptLevel::SpeedAndSize => OptLevel::SPEED_AND_SIZE,
            _ => OptLevel::SPEED,
        }
    }
}

#[pyclass(eq, eq_int)]
#[derive(PartialEq, Clone)]
#[allow(non_camel_case_types, clippy::upper_case_acronyms)]
pub enum Profiler {
    NONE,
    JITDUMP,
    PERFMAP,
}

impl From<::wasmtime::ProfilingStrategy> for Profiler {
    fn from(value: ::wasmtime::ProfilingStrategy) -> Self {
        match value {
            ::wasmtime::ProfilingStrategy::None => Profiler::NONE,
            ::wasmtime::ProfilingStrategy::JitDump => Profiler::JITDUMP,
            ::wasmtime::ProfilingStrategy::PerfMap => Profiler::PERFMAP,
            _ => Profiler::NONE,
        }
    }
}

#[pyclass]
#[derive(Clone)]
pub struct WASMConfig {
    backend: Backend,
    opt_level: OptLevel,
    profiler: Profiler,
    max_stack: usize,
    coredump_on_trap: bool,
    inlining: bool,
    cache_path: Option<PathBuf>,
}

#[pymethods]
impl WASMConfig {
    #[new]
    #[pyo3(signature = (
		backend = Backend::WINCH, opt_level = OptLevel::SPEED, profiler = Profiler::NONE, max_stack = 524288,
		coredump_on_trap = false, inlining = false, cache_path = None,
	))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        backend: Backend,
        opt_level: OptLevel,
        profiler: Profiler,
        max_stack: usize,
        coredump_on_trap: bool,
        inlining: bool,
        cache_path: Option<PathBuf>,
    ) -> Self {
        WASMConfig {
            backend,
            opt_level,
            profiler,
            max_stack,
            coredump_on_trap,
            inlining,
            cache_path,
        }
    }
}

impl Default for WASMConfig {
    fn default() -> Self {
        Self {
            backend: Backend::WINCH,
            opt_level: OptLevel::SPEED,
            profiler: Profiler::NONE,
            max_stack: 524288, // 512KiB
            coredump_on_trap: false,
            inlining: false,
            cache_path: None,
        }
    }
}

impl From<WASMConfig> for ::wasmtime::Config {
    fn from(value: WASMConfig) -> Self {
        ::wasmtime::Config::new()
            .max_wasm_stack(value.max_stack)
            .wasm_memory64(true)
            .strategy(match value.backend {
                Backend::WINCH => ::wasmtime::Strategy::Winch,
                Backend::CRANELIFT => ::wasmtime::Strategy::Cranelift,
            })
            .profiler(match value.profiler {
                Profiler::NONE => ::wasmtime::ProfilingStrategy::None,
                Profiler::JITDUMP => ::wasmtime::ProfilingStrategy::JitDump,
                Profiler::PERFMAP => ::wasmtime::ProfilingStrategy::PerfMap,
            })
            .cranelift_opt_level(match value.opt_level {
                OptLevel::NONE => ::wasmtime::OptLevel::None,
                OptLevel::SPEED => ::wasmtime::OptLevel::Speed,
                OptLevel::SPEED_AND_SIZE => ::wasmtime::OptLevel::SpeedAndSize,
            })
            .cranelift_regalloc_algorithm(::wasmtime::RegallocAlgorithm::SinglePass)
            .coredump_on_trap(value.coredump_on_trap)
            .compiler_inlining(value.inlining)
            .cache(value.cache_path.map(|v| {
                ::wasmtime::Cache::new(::wasmtime::CacheConfig::new().with_directory(v).to_owned())
                    .unwrap()
            }))
            .to_owned()
    }
}
