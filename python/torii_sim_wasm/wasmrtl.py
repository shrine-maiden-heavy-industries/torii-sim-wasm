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
		# Wasm currently only supports 63 bit wide values
		if len(value) > 63:
			if value.src_loc:
				src = '{}:{}'.format(*value.src_loc)
			else:
				src = 'unknown location'
			raise OverflowError(
				f'Value defined at {src} is {len(value)} bits wide, and wasm backend only supports '
				'signals that are less than 64 bits wide'
			)

		val = super().on_value(value)
		return val

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
		if self.inputs is not None:
			self.inputs.add(value)

		if self.mode == 'curr':
			return f'(i64.load (i64.const {self.state.get_signal(value) * 16}))'
		else:
			return f'(local.get $next_{self.state.get_signal(value)})'

	def on_Operator(self, value):
		def mask(value):
			value_mask = (1 << len(value)) - 1
			return f'(i64.and (i64.const {value_mask:#x}) {self(value)})'

		def sign(value):
			if value.shape().signed:
				return f'(call $sign {mask(value)} (i64.const {-1 << (len(value) - 1):#x}))'
			else: # unsigned
				return mask(value)
			return mask(value)

		if len(value.operands) == 1:
			arg, = value.operands
			if value.operator == '~':
				return f'(i64.xor {mask(arg)} (i64.const 0xffffffffffffffff))'
			if value.operator == '-':
				return f'(i64.mul {sign(arg)} (i64.const -1))'
			if value.operator == 'b':
				return f'(i64.extend_i32_u (i64.gt_u {mask(arg)} (i64.const 0)))'
			if value.operator == 'r|':
				return f'(i64.extend_i32_u (i64.ne {mask(arg)} (i64.const 0)))'
			if value.operator == 'r&':
				return f'(i64.extend_i32_u (i64.eq {mask(arg)} (i64.const {(1 << len(arg)) - 1})))'
			if value.operator == 'r^':
				return f'(i64.rem_u (i64.popcnt {mask(arg)}) (i64.const 2))'
			if value.operator in ('u', 's'):
				# These operators don't change the bit pattern, only its interpretation.
				return self(arg)
		elif len(value.operands) == 2:
			lhs, rhs = value.operands
			if value.operator == '+':
				return f'(i64.add {sign(lhs)} {sign(rhs)})'
			if value.operator == '-':
				return f'(i64.sub {sign(lhs)} {sign(rhs)})'
			if value.operator == '*':
				return f'(i64.mul {sign(lhs)} {sign(rhs)})'
			if value.operator == '//':
				return f'(call $zdiv {sign(lhs)} {sign(rhs)})'
			if value.operator == '%':
				return f'(call $zmod {sign(lhs)} {sign(rhs)})'
			if value.operator == '&':
				return f'(i64.and {sign(lhs)} {sign(rhs)})'
			if value.operator == '|':
				return f'(i64.or {sign(lhs)} {sign(rhs)})'
			if value.operator == '^':
				return f'(i64.xor {sign(lhs)} {sign(rhs)})'
			if value.operator == '<<':
				return f'(i64.shl {sign(lhs)} {sign(rhs)})'
			if value.operator == '>>':
				return f'(i64.shr_u {sign(lhs)} {sign(rhs)})'
			if value.operator == '!=':
				# i64.eq will push i32 into a stack so we need to extend it to i64
				return f'(i64.extend_i32_u (i64.ne {sign(lhs)} {sign(rhs)}))'
			if value.operator == '<':
				return f'(i64.extend_i32_u (i64.lt_s {sign(lhs)} {sign(rhs)}))'
			if value.operator == '<=':
				return f'(i64.extend_i32_u (i64.le_s {sign(lhs)} {sign(rhs)}))'
			if value.operator == '>':
				return f'(i64.extend_i32_u (i64.gt_s {sign(lhs)} {sign(rhs)}))'
			if value.operator == '>=':
				return f'(i64.extend_i32_u (i64.ge_s {sign(lhs)} {sign(rhs)}))'
			if value.operator == '==':
				return f'(i64.extend_i32_u (i64.eq {sign(lhs)} {sign(rhs)}))'
		elif len(value.operands) == 3:
			if value.operator == 'm':
				sel, val1, val0 = value.operands
				return f'(if (result i64) (i64.gt_u {mask(sel)} (i64.const 0)) (then {sign(val1)}) (else {sign(val0)}))'
		raise NotImplementedError(f'Operator \'{value.operator}\' not implemented') # :nocov:

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
		if self.outputs is not None:
			self.outputs.add(value)

		def gen(arg):
			value_mask = (1 << len(value)) - 1
			if value.shape().signed:
				value_const = f'(i64.const {-1 << (len(value) - 1):#x})'
				value_sign = f'(call $sign (i64.and (i64.const {value_mask:#x}) {arg}) {value_const})'
			else: # unsigned
				value_sign = f'(i64.and (i64.const {value_mask:#x}) {arg})'
			self.emitter.append(f'(local.set $next_{self.state.get_signal(value)} {value_sign})')
		return gen

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
