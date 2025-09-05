# SPDX-License-Identifier: BSD-2-Clause

from torii.hdl.ir    import Fragment
from torii.sim._base import BaseEngine

from ._wasm_engine   import __version__
from .wasmrtl        import WASMFragmentCompiler

__all__ = (
	'WASMSimEngine',
)

__version__ = __version__

class WASMSimEngine(BaseEngine):
	def __init__(self, fragment: Fragment) -> None:
		self._frag = fragment
		self._processes = WASMFragmentCompiler(None)(self._frag)

	def add_coroutine_process(self, process, *, default_cmd):
		pass

	def add_clock_process(self, clock, *, phase, period):
		pass

	def reset(self):
		pass

	def advance(self):
		return True

	@property
	def now(self):
		return 0
