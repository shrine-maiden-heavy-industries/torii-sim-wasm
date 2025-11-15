use pyo3::{
    exceptions::PyValueError,
    prelude::*,
    types::{PyDict, PyNone},
};

use crate::memory::{WASMInstance, WASMValue};

#[pyclass]
pub struct WASMSignalState {
    /// size of signal in bits
    pub signal_size: u64,
    pub curr: WASMValue,
    pub next: WASMValue,
    pub waiters: Py<PyDict>,
    // TODO: pending
}

#[pymethods]
impl WASMSignalState {
    #[new]
    fn new(instance: &WASMInstance, index: usize, signal_size: u64, value: u64) -> Self {
        Python::attach(|py| Self {
            signal_size,
            waiters: PyDict::new(py).into(),
            curr: WASMValue::new(instance, signal_size, index * 2, value),
            next: WASMValue::new(instance, signal_size, index * 2 + 1, value),
        })
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

    #[pyo3(signature = (process, signal, *, trigger = None))]
    fn add_trigger(
        &mut self,
        process: Py<PyAny>,
        signal: Py<PyAny>,
        trigger: Option<Py<PyAny>>,
    ) -> PyResult<()> {
        let index = self.get_signal(signal)?;
        Python::attach(|py| {
            // we need to convert the option to python None
            let trigger = if let Some(trigger) = trigger {
                trigger
            } else {
                PyNone::get(py).as_any().clone().unbind()
            };

            let waiters = self.slots[index].waiters.bind(py);
            if waiters
                .get_item(process.clone_ref(py))?
                .is_some_and(|value| value.eq(trigger.clone_ref(py)).unwrap())
            {
                return Err(PyErr::new::<PyValueError, _>(
                    "Unable to add trigger for process!",
                ));
            }

            waiters.set_item(process, trigger.clone_ref(py))?;
            Ok(())
        })
    }

    fn set_slot(&mut self) -> PyResult<()> {
        Ok(())
    }
}
