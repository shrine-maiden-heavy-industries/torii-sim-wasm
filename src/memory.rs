// SPDX-License-Identifier: BSD-2-Clause

use pyo3::prelude::*;
use wasmtime::{Config, Engine, Memory, MemoryTypeBuilder, Store};

#[pyclass]
pub struct WASMInstance {
    pub memory: Memory,
    pub store: Store<()>,
}

#[pymethods]
impl WASMInstance {
    #[new]
    fn new() -> Self {
        let mut config = Config::new();
        config.strategy(wasmtime::Strategy::Winch);
        let engine = Engine::new(&config).unwrap();
        let mut store = Store::new(&engine, ());

        let mem_type = MemoryTypeBuilder::new()
            .memory64(true)
            .shared(true)
            .min(2)
            .max(Some(2))
            .build()
            .unwrap();
        let memory = Memory::new(&mut store, mem_type).unwrap();
        Self { memory, store }
    }
}

#[pyclass]
pub struct WASMValue {
    /// Pointer to the wasm value, unsafely as usize as *mut u8 makes pyo3 unhappy
    ptr: usize,
    /// Value length in bits
    length: u64,
}

#[pymethods]
impl WASMValue {
    #[new]
    pub fn new(instance: &WASMInstance, length: u64, offset: usize, value: u64) -> Self {
        let ptr = unsafe { instance.memory.data_ptr(&instance.store).add(offset * 8) as usize };
        let new = Self { ptr, length };
        new.set(value);
        new
    }

    pub fn set(&self, value: u64) {
        // make sure the value is always fits the bits
        let value = value & ((1 << self.length) - 1);
        // TODO: fix for big as wasm values are always little endian
        unsafe { *(self.ptr as *mut u64) = value };
    }

    pub fn get(&self) -> u64 {
        // TODO: fix for big endian as value here is always little endian
        unsafe { *(self.ptr as *mut u64) }
    }
}
