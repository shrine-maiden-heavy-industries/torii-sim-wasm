# SPDX-License-Identifier: BSD-2-Clause

from torii.hdl.ir import Fragment

__all__ = (
	'WASMFragmentCompiler',
)

class WASMFragmentCompiler:
	def __init__(self, state) -> None:
		self.state = state

	def __call__(self, fragment: Fragment):
		pass
