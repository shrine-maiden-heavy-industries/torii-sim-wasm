use pyo3::{prelude::*, types::PyDict};

use crate::memory::{WASMInstance, WASMValue};

#[pyclass]
pub struct WASMSignalState {
    /// size of signal in bits
    pub signal_size: u64,
    pub curr: WASMValue,
    pub next: WASMValue,
    // TODO: pending
    // TODO: waiters
}

#[pymethods]
impl WASMSignalState {
    #[new]
    fn new(instance: &WASMInstance, index: usize, signal_size: u64, value: u64) -> Self {
        Self {
            signal_size,
            curr: WASMValue::new(instance, signal_size, index * 2, value),
            next: WASMValue::new(instance, signal_size, index * 2 + 1, value),
        }
    }
}

#[pyclass]
pub struct WASMSimulation {
    #[pyo3(get)]
    pub timeline: Py<PyAny>,
    pub signals: Py<PyAny>,
    pub slots: Vec<WASMSignalState>,
    pub memory: WASMInstance,
}

#[pymethods]
impl WASMSimulation {
    #[new]
    fn new(timeline: Py<PyAny>, signals: Py<PyAny>) -> Self {
        Self {
            timeline,
            signals,
            slots: Vec::new(),
            memory: WASMInstance::new(),
        }
    }

    fn get_signal(&mut self, signal: Py<PyAny>) -> PyResult<usize> {
        Python::attach(|py| {
            let index = self.signals.bind(py).get_item(signal.clone_ref(py));
            if let Ok(index) = index {
                index.extract()
            } else {
                // assuming the error is always keyerror
                let index = self.signals.bind(py).len()?;
                self.slots.push(WASMSignalState::new(
                    &self.memory,
                    index,
                    signal.bind(py).len()? as u64,
                    signal.bind(py).getattr("reset")?.extract::<u64>()?,
                ));
                self.signals
                    .bind(py)
                    .set_item(signal.clone_ref(py), index)?;
                Ok(index)
            }
        })
    }

    #[pyo3(signature = (_changed = None))]
    fn commit(&mut self, _changed: Option<Py<PyAny>>) -> PyResult<()> {
        Ok(())
    }

    fn wait_interval(&mut self, _process: Py<PyAny>, _signal: Py<PyAny>) -> PyResult<()> {
        Ok(())
    }

    fn add_trigger(&mut self, _process: Py<PyAny>, _signal: Py<PyAny>) -> PyResult<()> {
        Ok(())
    }

    fn set_slot(&mut self) -> PyResult<()> {
        Ok(())
    }
}
