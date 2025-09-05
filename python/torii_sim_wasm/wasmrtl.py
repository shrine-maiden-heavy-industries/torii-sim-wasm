# SPDX-License-Identifier: BSD-2-Clause

from torii.hdl.ast   import SignalSet
from torii.hdl.ir    import Fragment
from torii.hdl.xfrm  import LHSGroupFilter, StatementVisitor, ValueVisitor
from torii.sim._base import BaseProcess

__all__ = (
	'WASMFragmentCompiler',
	'WASMRTLProcess',
)

class WASMRTLProcess(BaseProcess):
	__slots__ = ('is_comb', 'runnable', 'passive', 'run')

	def __init__(self, *, is_comb) -> None:
		self.is_comb  = is_comb

		self.reset()

	def reset(self):
		self.runnable = self.is_comb
		self.passive  = True

class _Compiler:
	def __init__(self, state, emitter) -> None:
		self.state = state
		self.emitter = emitter

class _ValueCompiler(ValueVisitor, _Compiler):
	def on_value(self, value):
		raise NotImplementedError # :nocov:

	def on_ClockSignal(self, value):
		raise NotImplementedError # :nocov:

	def on_ResetSignal(self, value):
		raise NotImplementedError # :nocov:

	def on_AnyValue(self, value):
		raise NotImplementedError # :nocov:

	def on_Sample(self, value):
		raise NotImplementedError # :nocov:

	def on_Initial(self, value):
		raise NotImplementedError # :nocov:

class _RHSValueCompiler(_ValueCompiler):
	def __init__(self, state, emitter, *, mode, inputs = None) -> None:
		super().__init__(state, emitter)
		if mode not in ('curr', 'next'):
			raise ValueError(f'Expected mode to be \'curr\', or \'next\', not \'{mode!r}\'')
		self.mode = mode
		# If not None, `inputs` gets populated with RHS signals.
		self.inputs = inputs

	def on_Const(self, value):
		raise NotImplementedError # :nocov:

	def on_Signal(self, value):
		raise NotImplementedError # :nocov:

	def on_Operator(self, value):
		raise NotImplementedError # :nocov:

	def on_Slice(self, value):
		raise NotImplementedError # :nocov:

	def on_Part(self, value):
		raise NotImplementedError # :nocov:

	def on_Cat(self, value):
		raise NotImplementedError # :nocov:

	def on_ArrayProxy(self, value):
		raise NotImplementedError # :nocov:

class _LHSValueCompiler(_ValueCompiler):
	def __init__(self, state, emitter, *, rhs, outputs = None) -> None:
		super().__init__(state, emitter)
		# `rrhs` is used to translate rvalues that are syntactically a part of an lvalue, e.g.
		# the offset of a Part.
		self.rrhs = rhs
		# `lrhs` is used to translate the read part of a read-modify-write cycle during partial
		# update of an lvalue.
		self.lrhs = _RHSValueCompiler(state, emitter, mode = 'next', inputs = None)
		# If not None, `outputs` gets populated with signals on LHS.
		self.outputs = outputs

	def on_Const(self, value):
		raise NotImplementedError # :nocov:

	def on_Signal(self, value):
		raise NotImplementedError # :nocov:

	def on_Operator(self, value):
		raise NotImplementedError # :nocov:

	def on_Slice(self, value):
		raise NotImplementedError # :nocov:

	def on_Part(self, value):
		raise NotImplementedError # :nocov:

	def on_Cat(self, value):
		raise NotImplementedError # :nocov:

	def on_ArrayProxy(self, value):
		raise NotImplementedError # :nocov:

class _StatementCompiler(StatementVisitor, _Compiler):
	def __init__(self, state, emitter, *, inputs = None, outputs = None) -> None:
		super().__init__(state, emitter)
		self.rhs = _RHSValueCompiler(state, emitter, mode = 'curr', inputs = inputs)
		self.lhs = _LHSValueCompiler(state, emitter, rhs = self.rhs, outputs = outputs)

	def on_statements(self, stmts):
		for stmt in stmts:
			self(stmt)

	def on_Assign(self, stmt):
		gen_rhs_value = self.rhs(stmt.rhs) # check for oversized value before generating mask
		gen_rhs = f'(i64.and (i64.const {(1 << len(stmt.rhs)) - 1:#x}) {gen_rhs_value})'
		if stmt.rhs.shape().signed:
			gen_rhs = f'(call $sign {gen_rhs} (i64.const {-1 << (len(stmt.rhs) - 1):#x}))'
		return self.lhs(stmt.lhs)(gen_rhs)

	def on_Switch(self, stmt):
		raise NotImplementedError # :nocov:

	def on_Property(self, stmt):
		raise NotImplementedError # :nocov:

class WASMFragmentCompiler:
	def __init__(self, state) -> None:
		self.state = state

	def __call__(self, fragment: Fragment):
		processes = set()

		for domain_name, domain_signals in fragment.drivers.items():
			domain_stmts = LHSGroupFilter(domain_signals)(fragment.statements)
			domain_process = WASMRTLProcess(is_comb = domain_name is None)

			if domain_name is None:
				inputs = SignalSet()
				_StatementCompiler(self.state, None, inputs = inputs)(domain_stmts)
			else:
				_StatementCompiler(self.state, None)(domain_stmts)

			processes.add(domain_process)
