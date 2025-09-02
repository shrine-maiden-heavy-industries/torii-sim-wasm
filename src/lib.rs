// SPDX-License-Identifier: BSD-2-Clause

use pyo3::prelude::*;

#[pymodule]
#[pyo3(name = "_wasm_engine")]
mod wasm_engine {
    use pyo3::prelude::*;

    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add("__version__", env!("CARGO_PKG_VERSION"))?;

        Ok(())
    }
}
