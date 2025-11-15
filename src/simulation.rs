use std::sync::{Arc, Mutex};

use pyo3::{
    exceptions::PyValueError,
    prelude::*,
    types::{PyDict, PyNone, PySet},
};

use crate::memory::{WASMInstance, WASMValue};

#[pyclass]
pub struct WASMSignalState {
    /// size of signal in bits
    pub signal_size: u64,
    pub curr: WASMValue,
    pub next: WASMValue,
    pub waiters: Py<PyDict>,
    pub pending: Py<PySet>,
}

#[pymethods]
impl WASMSignalState {
    #[new]
    fn new(
        instance: &WASMInstance,
        index: usize,
        signal_size: u64,
        value: u64,
        pending: Py<PySet>,
    ) -> Self {
        Python::attach(|py| Self {
            pending,
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
    pub pending: Py<PySet>,
    pub signals: Py<PyAny>,
    pub slots: Vec<WASMSignalState>,
    // memory needs to be ArcMutex so we can have thread safe copies of
    // without having to rely on python references
    pub memory: Arc<Mutex<WASMInstance>>,
}

#[pymethods]
impl WASMSimulation {
    #[new]
    fn new(timeline: Py<PyAny>, signals: Py<PyAny>) -> Self {
        Python::attach(|py| Self {
            timeline,
            signals,
            slots: Vec::new(),
            // TODO: return error instead of unwrap
            pending: PySet::empty(py).unwrap().into(),
            memory: Arc::new(Mutex::new(WASMInstance::new())),
        })
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
                    &self.memory.lock().unwrap(),
                    index,
                    signal.bind(py).len()? as u64,
                    signal.bind(py).getattr("reset")?.extract::<u64>()?,
                    self.pending.clone_ref(py),
                ));
                self.signals
                    .bind(py)
                    .set_item(signal.clone_ref(py), index)?;
                Ok(index)
            }
        })
    }

    #[pyo3(signature = (changed = None))]
    fn commit(&mut self, changed: Option<Py<PySet>>) -> PyResult<bool> {
        Python::attach(|py| {
            let mut converged = true;
            for signal_state in self.pending.bind(py).iter() {
                if signal_state.call_method0("commit")?.extract::<bool>()? {
                    converged = false;
                }
            }

            if let Some(changed) = changed {
                // TODO: the update function should be added to Pyo3
                // changed.bind(py).update(self.pending.bind(py));
                changed
                    .bind(py)
                    .call_method1("update", (self.pending.bind(py),))?;
            }

            self.pending.bind(py).clear();
            Ok(converged)
        })
    }

    fn wait_interval(&mut self, process: Py<PyAny>, interval: Py<PyAny>) -> PyResult<()> {
        Python::attach(|py| {
            self.timeline
                .call_method1(py, "delay", (interval, process))?;
            Ok(())
        })
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

    // TODO: remove this callback from WASMRunner and handle it inside WASMRunner
    pub fn set_slot(&mut self, _index: u64, _value: u64) -> PyResult<()> {
        Ok(())
    }
}
