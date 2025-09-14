# Torii WASM Simulation Engine

This package provides a WASM Simulation engine backend based on [wasmtime] for [Torii].

The WASM simulation engine provides faster simulation for huge designs at the cost of initial spool up time for the runtime, as such, it does not make much sense to enable it for lots of smaller simulation tests.

Here are some examples from the [SOL] Test Suite:

| Test Name                                               | PySIM   | WASM   |
|---------------------------------------------------------|---------|--------|
| `SPIRegisterInterfaceTest.test_aborted_write_behavior`  | 0.095   | 0.574  |
| `USBAnalyzerOverflowTest.test_fast_traffic`             | 183.509 | 83.142 |
| `USBAnalyzerTest.test_overrun`                          | 0.926   | 2.835  |
| `TestHyperRAMInterface.test_register_read`              | 0.129   | 0.095  |
| `TestHyperRAMInterface.test_register_write`             | 0.023   | 0.048  |
| `USBAnalyzerTest.test_short_packet`                     | 0.358   | 0.431  |
| `USBAnalyzerStackTest.test_simple_analysis`             | 0.407   | 0.452  |
| `USBAnalyzerTest.test_single_packet`                    | 0.338   | 0.430  |
| `SPIDeviceInterfaceTest.test_spi_interface`             | 0.017   | 0.088  |
| `SPIDeviceInterfaceTest.test_spi_transmit_second_word`  | 0.016   | 0.083  |
| `SPIRegisterInterfaceTest.test_undefined_read_behavior` | 0.041   | 0.277  |
| `SPIRegisterInterfaceTest.test_write_behavior`          | 0.075   | 0.378  |

As you can see, the WASM overhead makes the smaller tests a bit slower, but that overhead is acceptable for much larger tests.

For a simulation test suite that hard a handful or large along running tests in combination with many smaller tests, this overhead is amortized by the speed increase for the very large tests. In the case of SOL this is a runtime of `83.768` seconds with the WASM backend vs `188.070` seconds with PySIM.

There are still many improvements that can be made within the implementation of both the way the Torii simulation interface works and the WASM backend itself, but even as it stands the speed up is considerable.

## Usage and Installation

Below is a very rough quick-start, the more detailed and in-depth usage and installation instructions live in the [Torii Documentation].

These instructions assume you already have [installed Torii].

### Installation

```console
$ pip install torii-sim-wasm
```

It is important to note, that this package ships as a native module, and might not be built for your platform. If you think it should be supported, please file a report in the [issue tracker].

You can also build the package from source using the `sdist`, you will need a Rust toolchain set up in order to do so.

### Usage

To use the WASM runtime, import `WASMSimEngine` and pass it as the `engine` parameter to the Torii `Simulator`, like below.

```py

from torii_sim_wasm import WASMSimEngine

sim = Simulator(module, engine = WASMSimEngine)
```

That is all that you need to do to enable the WASM backend.

## Community

The two primary community spots for Torii are the `#torii` IRC channel on [libera.chat] (`irc.libera.chat:6697`) which you can join via your favorite IRC client or the [web chat], and the [discussion forum] on GitHub.

Please do join and share your projects using Torii, ask questions, get help with problems, or discuss Torii's development.

## Reporting Issues and Requesting Features

The reporting of bugs and suggestion of features are done GitHub via the [issue tracker], there are pre-defined templates for both of them that will walk you though all the information you need to provide.

Be sure to read the [reporting issues] or the [suggesting features] sections of the [Contribution Guidelines] as appropriate as they go into more important details on the finer points.

## License

The Torii WASM simulation engine is released under the [BSD-2-Clause], the full text of which can be found in the [`LICENSE`] file in the root of the [git repository].

[wasmtime]: https://github.com/bytecodealliance/wasmtime
[Torii]: https://github.com/shrine-maiden-heavy-industries/torii-hdl
[Torii Documentation]: https://torii.shmdn.link/latest/
[installed Torii]: https://torii.shmdn.link/latest/install.html
[SOL]: https://github.com/shrine-maiden-heavy-industries/sol
[issue tracker]: https://github.com/shrine-maiden-heavy-industries/torii-sim-wasm/issues
[reporting issues]: https://github.com/shrine-maiden-heavy-industries/torii-sim-wasm/blob/main/CONTRIBUTING.md#reporting-issues
[suggesting features]: https://github.com/shrine-maiden-heavy-industries/torii-sim-wasm/blob/main/CONTRIBUTING.md#suggesting-features
[Contribution Guidelines]: https://github.com/shrine-maiden-heavy-industries/torii-sim-wasm/blob/main/CONTRIBUTING.md
[libera.chat]: https://libera.chat/
[web chat]: https://web.libera.chat/#torii
[discussion forum]: https://github.com/shrine-maiden-heavy-industries/torii-hdl/discussions
[BSD-2-Clause]: https://spdx.org/licenses/BSD-2-Clause.html
[`LICENSE`]: https://github.com/shrine-maiden-heavy-industries/torii-sim-wasm/blob/main/LICENSE
[git repository]: https://github.com/shrine-maiden-heavy-industries/torii-sim-wasm
