# SPDX-License-Identifier: BSD-2-Clause

from inspect         import getfile, getlineno, iscoroutine, isgenerator

from torii.hdl       import ClockDomain, Const, Value
from torii.hdl.ast   import SignalSet, Statement, ValueCastable
from torii.sim._base import BaseProcess
from torii.sim.core  import Active, Delay, Passive, Settle, Tick
from .wasmrtl        import _RHSValueCompiler, _StatementCompiler
from ._wasm_engine   import WASMRunner

__all__ = (
	'WASMCoroProcess',
)

def foo(one, two):
	assert False

class WASMCoroProcess(BaseProcess):
	def __init__(self, state, domains, constructor, *, default_cmd = None) -> None:
		self.state = state
		self.domains = domains
		self.constructor = constructor
		self.default_cmd = default_cmd

		self.reset()

	def reset(self):
		self.runnable = True
		self.passive = False

		self.coroutine = self.constructor()
		self.waits_on = SignalSet()

	def src_loc(self):
		coroutine = self.coroutine
		if coroutine is None:
			return None
		while coroutine.gi_yieldfrom is not None and isgenerator(coroutine.gi_yieldfrom):
			coroutine = coroutine.gi_yieldfrom
		if isgenerator(coroutine):
			frame = coroutine.gi_frame
		if iscoroutine(coroutine):
			frame = coroutine.cr_frame
		return f'{getfile(frame)}:{getlineno(frame)}'

	def add_trigger(self, signal, trigger = None):
		self.state.add_trigger(self, signal, trigger = trigger)
		self.waits_on.add(signal)

	def clear_triggers(self):
		for signal in self.waits_on:
			self.state.remove_trigger(self, signal)
		self.waits_on.clear()

	def run(self):
		if self.coroutine is None:
			return

		self.clear_triggers()

		response = None
		exception = None
		while True:
			try:
				if exception is None:
					command = self.coroutine.send(response)
				else:
					command = self.coroutine.throw(exception)
			except StopIteration:
				self.passive = True
				self.coroutine = None
				return

			try:
				if command is None:
					command = self.default_cmd
				response = None
				exception = None

				if isinstance(command, ValueCastable):
					command = Value.cast(command)
				if isinstance(command, Value):
					module_code = _RHSValueCompiler.compile(self.state, command, mode = 'curr')
					run = WASMRunner(module_code, self.state.memory, self.state.set_slot)
					result = run()
					response = Const.normalize(result, command.shape())

				elif isinstance(command, Statement):
					module_code = _StatementCompiler.compile(self.state, command)
					run = WASMRunner(module_code, self.state.memory, self.state.set_slot)
					run()

				elif type(command) is Tick:
					domain = command.domain
					if isinstance(domain, ClockDomain):
						pass
					elif domain in self.domains:
						domain = self.domains[domain]
					else:
						raise NameError(
							f'Received command {command!r} that refers to a nonexistent '
							f'domain {command.domain!r} from process {self.src_loc()!r}'
						)
					self.add_trigger(domain.clk, trigger = 1 if domain.clk_edge == 'pos' else 0)
					if domain.rst is not None and domain.async_reset:
						self.add_trigger(domain.rst, trigger = 1)
					return

				elif type(command) is Settle:
					self.state.wait_interval(self, None)
					return

				elif type(command) is Delay:
					# Internal timeline is in 1ps integral units, intervals are public API and in floating point
					interval = int(command.interval * 1e12) if command.interval is not None else None
					self.state.wait_interval(self, interval)
					return

				elif type(command) is Passive:
					self.passive = True

				elif type(command) is Active:
					self.passive = False

				elif command is None: # only possible if self.default_cmd is None
					raise TypeError(
						f'Received default command from process {self.src_loc()!r} that was added '
						'with add_process(); did you mean to add this process with '
						'add_sync_process() instead?'
					)

				else:
					raise TypeError(f'Received unsupported command {command!r} from process {self.src_loc()!r}')

			except Exception as exn:
				response = None
				exception = exn
