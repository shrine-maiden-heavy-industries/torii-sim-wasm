use pyo3::{prelude::*, types::PyDict};

use crate::memory::WASMInstance;

#[pyclass]
pub struct WASMSimulation {
    pub timeline: Py<PyAny>,
    pub signals: Py<PyDict>,
    pub memory: WASMInstance,
}

#[pymethods]
impl WASMSimulation {
    #[new]
    fn new(timeline: Py<PyAny>) -> Self {
        Python::attach(|py| Self {
            timeline,
            signals: PyDict::new(py).into(),
            memory: WASMInstance::new(),
        })
    }
}
