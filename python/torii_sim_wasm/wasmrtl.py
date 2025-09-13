# SPDX-License-Identifier: BSD-2-Clause

from contextlib  import contextmanager
from os          import getenv
from tempfile    import NamedTemporaryFile

from torii.hdl.ast   import SignalSet
from torii.hdl.ir    import Fragment
from torii.hdl.xfrm  import LHSGroupFilter, StatementVisitor, ValueVisitor
from torii.sim._base import BaseProcess

from ._wasm_engine   import WASMRunner

__all__ = (
	'WASMFragmentCompiler',
	'WASMRTLProcess',
)

WASM_SET_SLOT = '''
	(func $slots_set (param $index i64) (param $value i64)
		(local $curr i64)
		(local $next i64)
		(local $next_off i64)
		(local.set $curr (i64.load (i64.mul (local.get $index) (i64.const 16))))
		(local.set $next_off (i64.mul (i64.add (i64.mul (local.get $index) (i64.const 2)) (i64.const 1)) (i64.const 8)))
		(local.set $next (i64.load (local.get $next_off)))
		(if (i64.ne (local.get $next) (local.get $value))
			(then
				(i64.store (local.get $next_off) (local.get $value))
				(call $slots_set_py (local.get $index) (local.get $value))
			)
		)
	)
'''

WASM_SIGN = '''
	(func $sign (param $value i64) (param $sign i64) (result i64)
		(if (result i64) (i64.ne (i64.and (local.get $value) (local.get $sign)) (i64.const 0))
			(then (return (i64.or (local.get $value) (local.get $sign))))
			(else (return (local.get $value)))
		)
	)
'''

# Signed floor div for integers
WASM_ZDIV = '''
	(func $zdiv (param $lhs i64) (param $rhs i64) (result i64)
		(local $res i64)
		(if (result i64) (i64.eq (local.get $rhs) (i64.const 0))
			(then (return (i64.const 0)))
			(else
				(local.set $res (i64.div_s (local.get $lhs) (local.get $rhs)))
				(if (i32.gt_u (i32.and
							(i64.lt_s (i64.xor (local.get $lhs) (local.get $rhs)) (i64.const 0))
							(i64.ne (i64.rem_s (local.get $lhs) (local.get $rhs)) (i64.const 0))
						)
						(i32.const 0)
					)
					(then (local.set $res (i64.sub (local.get $res) (i64.const 1))))
				)
				(return (local.get $res))
			)
		)
	)
'''

WASM_ZMOD = '''
	(func $zmod (param $lhs i64) (param $rhs i64) (result i64)
		(if (result i64) (i64.eq (local.get $rhs) (i64.const 0))
			(then (return (i64.const 0)))
			(else (return
				(i64.rem_s
					(i64.add
						(i64.rem_s (local.get $lhs) (local.get $rhs))
						(local.get $rhs)
					)
					(local.get $rhs)
				)
			))
		)
	)
'''

class WASMRTLProcess(BaseProcess):
	__slots__ = ('is_comb', 'runnable', 'passive', 'run')

	def __init__(self, *, is_comb) -> None:
		self.is_comb  = is_comb

		self.reset()

	def reset(self):
		self.runnable = self.is_comb
		self.passive  = True

class _WASMEmitter:
	def __init__(self):
		self._level = 0
		self._suffix = 0
		self._imports = []
		self._globals = []
		self._variables = []
		self._instructions = []

	def add_src(self, src_loc):
		if src_loc:
			self.append(';; {}:{}'.format(*src_loc))

	def append(self, code):
		self._instructions.append('\t\t' + '\t' * self._level)
		self._instructions.append(code)
		self._instructions.append('\n')

	def add_variable(self, name):
		self._variables.append('\t\t')
		self._variables.append(f'(local ${name} i64)')
		self._variables.append('\n')

	def def_var(self, name, code):
		name = f'{name}_{self._suffix}'
		self._suffix += 1
		self.add_variable(name)
		self.append(f'(local.set ${name} {code})')
		return name

	@contextmanager
	def indent(self):
		self._level += 1
		yield
		self._level -= 1

	def flush(self, result: bool = False):
		module = '(module\n'
		module += '\t(import "" "gmem" (memory $gmem i64 0 2 shared ))\n'
		module += '\t(func $slots_set_py (import "" "slots_set_py") (param i64) (param i64))\n'
		module += ''.join(self._globals)
		module += '\n'
		module += ''.join(self._imports)
		module += '\n'
		module += WASM_SET_SLOT
		module += '\n'
		module += WASM_SIGN
		module += '\n'
		module += WASM_ZDIV
		module += '\n'
		module += WASM_ZMOD
		module += '\n'
		module += '\t(func (export "run") (result i64)\n'
		module += ''.join(self._variables)
		module += ''.join(self._instructions)
		if not result:
			module += '\t\t(i64.const 0)\n'
		module += "\n\t)\n)\n"

		self._instructions.clear()
		return module

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
		return f'(i64.const {value.value})'

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
		and_shift = f'(i64.shr_u {self(value.value)} (i64.const {value.start}))'
		return f'(i64.and (i64.const {(1 << len(value)) - 1:#x}) {and_shift})'

	def on_Part(self, value):
		offset_mask = (1 << len(value.offset)) - 1
		offset = f'(i64.mul (i64.const {value.stride}) (i64.and (i64.const {offset_mask:#x}) {self(value.offset)}))'
		return f'(i64.and (i64.const {(1 << value.width) - 1}) (i64.shr_u {self(value.value)} {offset}))'

	def on_Cat(self, value):
		gen_parts = []
		offset = 0
		for part in value.parts:
			part_mask = (1 << len(part)) - 1
			gen_parts.append(f'(i64.shl (i64.and (i64.const {part_mask:#x}) {self(part)}) (i64.const {offset}))')
			offset += len(part)

		# we have to nest the or statements so time to do annoying paren stuff
		if gen_parts:
			return f'{"(i64.or ".join(gen_parts)}{")" * (len(gen_parts) - 1)}'
		return '(i64.const 0)'

	def on_ArrayProxy(self, value):
		index_mask = (1 << len(value.index)) - 1
		self.emitter.add_src(value.src_loc)
		gen_index = self.emitter.def_var('rhs_index', f'(i64.and (i64.const {index_mask:#x}) {self(value.index)})')
		gen_value = self.emitter.def_var('rhs_proxy', '(i64.const 0)')
		if value.elems:
			for index, elem in enumerate(value.elems):
				self.emitter.add_src(value.src_loc)
				check = f'(i64.eq (i64.const {index}) (local.get ${gen_index}))'
				if index == 0:
					self.emitter.append(f'(if {check} (then')
				else:
					self.emitter.append(f'(else (if {check} (then')
				with self.emitter.indent():
					self.emitter.append(f'(local.set ${gen_value} {self(elem)})')
				self.emitter.append(')')

			self.emitter.append('(else')
			with self.emitter.indent():
				self.emitter.append(f'(local.set ${gen_value} {self(value.elems[-1])})')

			self.emitter.append('))' + '))' * (len(value.elems) - 1))
			return f'(local.get ${gen_value})'
		else:
			return '(i64.const 0)'

	@classmethod
	def compile(cls, state, value, *, mode):
		emitter = _WASMEmitter()
		compiler = cls(state, emitter, mode = mode)
		emitter.append(compiler(value))

		output_code = emitter.flush(True)
		return output_code

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
		raise TypeError # :nocov:

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
			self.emitter.add_src(value.src_loc)
			self.emitter.append(f'(local.set $next_{self.state.get_signal(value)} {value_sign})')
		return gen

	def on_Operator(self, value):
		if value.operator in ('u', 's'):
			return self(value.operands[0])
		raise TypeError # :nocov:

	def on_Slice(self, value):
		def gen(arg):
			width_mask = (1 << (value.stop - value.start)) - 1
			self(value.value)(
				f'(i64.or '
				f'(i64.and {self.lrhs(value.value)} '
				f'(i64.const {~(width_mask << value.start):#x})) '
				f'(i64.shl (i64.and (i64.const {width_mask:#x}) {arg}) (i64.const {value.start}))'
				f')'
			)
		return gen

	def on_Part(self, value):
		def gen(arg):
			width_mask = (1 << value.width) - 1
			offset_mask = (1 << len(value.offset)) - 1
			offset_and = f'(i64.and (i64.const {offset_mask:#x}) {self.rrhs(value.offset)})'
			offset = f'(i64.mul (i64.const {value.stride}) {offset_and})'
			self(value.value)(
				f'(i64.and {self.lrhs(value.value)} '
				f'(i64.or '
				f'(i64.xor (i64.shl (i64.const {width_mask:#x}) {offset}) (i64.const 0xffffffffffffffff)) '
				f'(i64.shl (i64.and (i64.const {width_mask:#x}) {arg}) {offset}))'
				f')'
			)
		return gen

	def on_Cat(self, value):
		def gen(arg):
			self.emitter.add_src(value.src_loc)
			gen_arg = self.emitter.def_var('cat', arg)
			offset = 0
			for part in value.parts:
				part_mask = (1 << len(part)) - 1
				part_shift = f'(i64.shr_u (local.get ${gen_arg}) (i64.const {offset}))'
				self(part)(f'(i64.and (i64.const {part_mask:#x}) {part_shift})')
				offset += len(part)
		return gen

	def on_ArrayProxy(self, value):
		def gen(arg):
			self.emitter.add_src(value.src_loc)
			index_mask = (1 << len(value.index)) - 1
			gen_index = self.emitter.def_var('index', f'(i64.and {self.rrhs(value.index)} (i64.const {index_mask:#x}))')
			if value.elems:
				for index, elem in enumerate(value.elems):
					self.emitter.add_src(value.src_loc)
					check = f'(i64.eq (i64.const {index}) (local.get ${gen_index}))'
					if index == 0:
						self.emitter.append(f'(if {check} (then')
					else:
						self.emitter.append(f'(else (if {check} (then')
					with self.emitter.indent():
						self(elem)(arg)
					self.emitter.append(')')

				self.emitter.add_src(value.src_loc)
				self.emitter.append('(else')
				with self.emitter.indent():
					self(value.elems[-1])(arg)

				self.emitter.append('))' + '))' * (len(value.elems) - 1))
		return gen

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
		test_value = self.rhs(stmt.test) # check for oversized value before generating mask
		gen_test = self.emitter.def_var('test', f'(i64.and (i64.const {(1 << len(stmt.test)) - 1:#x}) {test_value})')

		for index, (patterns, stmts) in enumerate(stmt.cases.items()):
			self.emitter.add_src(stmt.src_loc)
			gen_checks = []
			if not patterns:
				gen_checks.append('(i32.eq (i32.const 1) (i32.const 1))')
			else:
				for pattern in patterns:
					if "-" in pattern:
						mask  = int(''.join('0' if b == '-' else '1' for b in pattern), 2)
						value = int(''.join('0' if b == '-' else b for b in pattern), 2)
						value_and = f'(i64.and (i64.const {mask}) (local.get ${gen_test}))'
						gen_checks.append(f'(i64.eq (i64.const {value}) {value_and})')
					else:
						value = int(pattern or '0', 2)
						gen_checks.append(f'(i64.eq (i64.const {value}) (local.get ${gen_test}))')

			if index == 0:
				self.emitter.append(f'(if {"".join(gen_checks)} (then')
			else:
				self.emitter.append(f'(else (if {"".join(gen_checks)} (then')

			with self.emitter.indent():
				self(stmts)

			self.emitter.append(')')

		# Close down all the nested if-elses
		if len(stmt.cases.items()) > 0:
			self.emitter.append(')' + '))' * (len(stmt.cases.items()) - 1))

	def on_Property(self, stmt):
		raise NotImplementedError # :nocov:

	@classmethod
	def compile(cls, state, stmt):
		output_indexes = [state.get_signal(signal) for signal in stmt._lhs_signals()]
		emitter = _WASMEmitter()
		for signal_index in output_indexes:
			emitter.add_variable(f'next_{signal_index}')
			emitter.append(f'(local.set $next_{signal_index} (i64.load (i64.const {(signal_index * 2 + 1) * 8})))')
		compiler = cls(state, emitter)
		compiler(stmt)
		for signal_index in output_indexes:
			emitter.append(f'(call $slots_set (i64.const {signal_index}) (local.get $next_{signal_index}))')

		output_code = emitter.flush()
		return output_code

class WASMFragmentCompiler:
	def __init__(self, state) -> None:
		self.state = state

	def __call__(self, fragment: Fragment):
		processes = set()

		for domain_name, domain_signals in fragment.drivers.items():
			domain_stmts = LHSGroupFilter(domain_signals)(fragment.statements)
			domain_process = WASMRTLProcess(is_comb = domain_name is None)

			emitter = _WASMEmitter()
			if domain_name is None:
				for signal in domain_signals:
					signal_index = self.state.get_signal(signal)
					emitter.add_variable(f'next_{signal_index}')
					emitter.append(f'(local.set $next_{signal_index} (i64.const {signal.reset}))')

				inputs = SignalSet()
				_StatementCompiler(self.state, emitter, inputs = inputs)(domain_stmts)

				for input in inputs:
					self.state.add_trigger(domain_process, input)
			else:
				domain = fragment.domains[domain_name]
				clk_trigger = 1 if domain.clk_edge == 'pos' else 0
				self.state.add_trigger(domain_process, domain.clk, trigger = clk_trigger)
				if domain.rst is not None and domain.async_reset:
					rst_trigger = 1
					self.state.add_trigger(domain_process, domain.rst, trigger = rst_trigger)

				for signal in domain_signals:
					signal_index = self.state.get_signal(signal)
					emitter.add_variable(f'next_{signal_index}')
					index_const = f'(i64.const {(signal_index * 2 + 1) * 8})'
					emitter.append(f'(local.set $next_{signal_index} (i64.load {index_const}))')

				_StatementCompiler(self.state, emitter)(domain_stmts)

			for signal in domain_signals:
				signal_index = self.state.get_signal(signal)
				emitter.append(f'(call $slots_set (i64.const {signal_index}) (local.get $next_{signal_index}))')

			module_code = emitter.flush()
			if getenv('TORII_WASMSIM_DUMP'):
				file = NamedTemporaryFile('w', prefix = 'torii_wasmsim_', delete = False)
				file.write(module_code)

			domain_process.run = WASMRunner(module_code, self.state.memory, self.state.set_slot)
			processes.add(domain_process)

		for subfragment_index, (subfragment, subfragment_name) in enumerate(fragment.subfragments):
			if subfragment_name is None:
				subfragment_name = f'U${subfragment_index}'
			processes.update(self(subfragment))

		return processes
