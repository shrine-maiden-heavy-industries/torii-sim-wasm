# SPDX-License-Identifier: BSD-2-Clause

from os           import getenv
from pathlib      import Path

import nox
from nox.sessions import Session

ROOT_DIR  = Path(__file__).parent

BUILD_DIR = ROOT_DIR  / 'build'
CNTRB_DIR = ROOT_DIR  / 'contrib'
DOCS_DIR  = ROOT_DIR  / 'docs'
DIST_DIR  = BUILD_DIR / 'dist'

IN_CI           = getenv('GITHUB_WORKSPACE') is not None
ENABLE_COVERAGE = IN_CI or getenv('TORII_TEST_COVERAGE') is not None

# Default sessions to run
nox.options.sessions = (
	'test',
	'lint',
	'typecheck-mypy'
)

# Try to use `uv`, if not fallback to `virtualenv`
nox.options.default_venv_backend = 'uv|virtualenv'

@nox.session(reuse_venv = True)
def test(session: Session) -> None:
	OUTPUT_DIR = BUILD_DIR / 'tests'
	OUTPUT_DIR.mkdir(parents = True, exist_ok = True)

	unittest_args = ('-m', 'unittest', 'discover', '-s', str(ROOT_DIR / 'python'))

	session.install('-e', '.')

	if ENABLE_COVERAGE:
		session.log('Coverage support enabled')
		session.install('coverage')
		coverage_args = ('-m', 'coverage', 'run', '-p', f'--rcfile={ROOT_DIR / "pyproject.toml"}',)
		session.env['COVERAGE_CORE'] = 'sysmon'
	else:
		coverage_args = tuple[str]()

	with session.chdir(OUTPUT_DIR):
		session.log('Running core test suite...')
		session.run('python', *coverage_args, *unittest_args, *session.posargs)

		if ENABLE_COVERAGE:
			session.log('Combining Coverage data..')
			session.run('python', '-m', 'coverage', 'combine')

			session.log('Generating XML Coverage report...')
			session.run('python', '-m', 'coverage', 'xml', f'--rcfile={ROOT_DIR / "pyproject.toml"}')

# TODO(aki): Figure out how the documentation will be handled. (Part of Torii itself?)

@nox.session(name = 'typecheck-mypy', reuse_venv = True)
def typecheck_mypy(session: Session) -> None:
	OUTPUT_DIR = BUILD_DIR / 'typing' / 'mypy'
	OUTPUT_DIR.mkdir(parents = True, exist_ok = True)

	session.install('mypy')
	session.install('lxml')
	session.install('-e', '.')

	session.run(
		'mypy', '--non-interactive', '--install-types', '--pretty',
		'--disallow-any-generics',
		'--cache-dir', str((OUTPUT_DIR / '.mypy-cache').resolve()),
		'-p', 'torii_sim_wasm', '--html-report', str(OUTPUT_DIR.resolve())
	)

@nox.session(name = 'typecheck-pyright', reuse_venv = True)
def typecheck_pyright(session: Session) -> None:
	OUTPUT_DIR = BUILD_DIR / 'typing' / 'pyright'
	OUTPUT_DIR.mkdir(parents = True, exist_ok = True)

	session.install('pyright')
	session.install('types-Pygments', 'types-setuptools')
	session.install('-e', '.')

	with (OUTPUT_DIR / 'pyright.log').open('w') as f:
		session.run('pyright', *session.posargs, stdout = f)

@nox.session(reuse_venv = True)
def lint(session: Session) -> None:
	session.install('flake8')
	session.install('ruff')

	session.run(
		'flake8', '--config', str((CNTRB_DIR / '.flake8').resolve()),
		'./python/torii_sim_wasm', './python/tests',
	)
	session.run('ruff', 'check', './python/torii_sim_wasm', './python/tests')

@nox.session(reuse_venv = True)
def dist(session: Session) -> None:
	session.install('build')

	session.run('python', '-m', 'build', '-o', str(DIST_DIR))
