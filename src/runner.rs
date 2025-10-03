use pyo3::prelude::*;
use wasmtime::{Caller, Func, Instance, Module, TypedFunc};

use crate::simulation::WASMSimulation;

#[pyclass]
pub struct WASMRunner {
    /// wasm function that gets extracted from the compiled module
    runner: TypedFunc<(), u64>,
    instance: Py<WASMSimulation>,
}

#[pymethods]
impl WASMRunner {
    #[new]
    fn new(src: &str, instance: Py<WASMSimulation>, callback: Py<PyAny>) -> Self {
        let runner = Python::attach(|py| {
            let wasm = &mut instance.try_borrow_mut(py).unwrap().memory;
            let module = Module::new(wasm.store.engine(), src).unwrap();

            let py_callback = Func::wrap(
                &mut wasm.store,
                move |_: Caller<'_, ()>, index: u64, value: u64| {
                    Python::attach(|py| {
                        callback.call1(py, (index, value)).unwrap();
                    });
                },
            );

            let imports = [wasm.memory.into(), py_callback.into()];
            let inst = Instance::new(&mut wasm.store, &module, &imports).unwrap();
            inst.get_typed_func(&mut wasm.store, "run").unwrap()
        });

        Self { runner, instance }
    }

    fn __call__(&mut self) -> u64 {
        Python::attach(|py| {
            let wasm = &mut self.instance.try_borrow_mut(py).unwrap().memory;
            self.runner.call(&mut wasm.store, ()).unwrap()
        })
    }
}
