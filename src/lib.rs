// SPDX-License-Identifier: BSD-2-Clause

use pyo3::prelude::*;

mod memory;
mod runner;

#[pymodule]
#[pyo3(name = "_wasm_engine")]
mod wasm_engine {
    use crate::memory;
    use crate::runner;
    use pyo3::prelude::*;

    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add("__version__", env!("CARGO_PKG_VERSION"))?;
        m.add_class::<memory::WASMValue>()?;
        m.add_class::<memory::WASMInstance>()?;
        m.add_class::<runner::WASMRunner>()?;
        Ok(())
    }
}
