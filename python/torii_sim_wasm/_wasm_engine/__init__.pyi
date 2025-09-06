# SPDX-License-Identifier: BSD-2-Clause

__version__: str

class WASMInstance():
	def __init__(self) -> None:
		...

class WASMValue():
	def __init__(self, instance: WASMInstance, length: int, offset: int, value: int) -> None:
		...

	def set(self, value: int) -> None:
		...

	def get(self) -> int:
		...

class WASMRunner():
	def __init__(self, src: str, instance: WASMInstance, callback) -> None:
		...

	def __call__(self) -> int:
		...
