// SPDX-License-Identifier: BSD-2-Clause

use pyo3::prelude::*;

mod memory;

#[pymodule]
#[pyo3(name = "_wasm_engine")]
mod wasm_engine {
    use crate::memory;
    use pyo3::{prelude::*, py_run};

    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add("__version__", env!("CARGO_PKG_VERSION"))?;
        m.add_class::<memory::WASMValue>()?;
        m.add_class::<memory::WASMInstance>()?;
        Ok(())
    }
}
