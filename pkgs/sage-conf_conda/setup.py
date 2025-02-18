import os
import sys
import shutil
import sysconfig
import platform
import fnmatch

from pathlib import Path

from setuptools import setup
from distutils.command.build_scripts import build_scripts as distutils_build_scripts
from setuptools.command.build_py import build_py as setuptools_build_py
from setuptools.command.editable_wheel import editable_wheel as setuptools_editable_wheel
from setuptools.errors import SetupError


class build_py(setuptools_build_py):

    def run(self):

        HERE = os.path.dirname(__file__)
        if self.editable_mode:
            SAGE_ROOT = os.path.join(HERE, 'sage_root')
        else:
            SAGE_ROOT = self._create_writable_sage_root()

        if not os.environ.get('CONDA_PREFIX', ''):
            raise SetupError('No conda environment is active. '
                             'See https://doc.sagemath.org/html/en/installation/conda.html on how to get started.')

        cmd = f"cd {SAGE_ROOT} && ./configure --enable-build-as-root --with-system-python3=force --disable-notebook --disable-sagelib --disable-sage_conf --disable-doc"
        cmd += ' --with-python=$CONDA_PREFIX/bin/python --prefix="$CONDA_PREFIX"'
        cmd += ' $(for pkg in $(PATH="build/bin:$PATH" build/bin/sage-package list :standard: --exclude rpy2 --has-file spkg-configure.m4 --has-file distros/conda.txt); do echo --with-system-$pkg=force; done)'
        print(f"Running {cmd}")
        sys.stdout.flush()
        if os.system(cmd) != 0:
            if os.path.exists(os.path.join(SAGE_ROOT, 'config.status')):
                print("Warning: A configuration has been written, but the configure script has exited with an error. "
                      "Carefully check any messages above before continuing.")
            else:
                print("Error: The configure script has failed; this may be caused by missing build prerequisites.")
                sys.stdout.flush()
                PREREQ_SPKG = "_prereq bzip2 xz libffi"  # includes python3 SPKG_DEPCHECK packages
                os.system(f'cd {SAGE_ROOT} && export PACKAGES="$(build/bin/sage-get-system-packages conda {PREREQ_SPKG})" && [ -n "$PACKAGES" ] && echo "You can install the required build prerequisites using the following shell command" && echo "" && build/bin/sage-print-system-package-command conda --verbose --sudo install $PACKAGES && echo ""')
                raise SetupError("configure failed")

        # In this mode, we never run "make".

        # Copy over files generated by the configure script
        # (see configure.ac AC_CONFIG_FILES)
        if self.editable_mode:
            pass  # same file
        else:
            shutil.copyfile(os.path.join(SAGE_ROOT, 'pkgs', 'sage-conf', '_sage_conf', '_conf.py'),
                            os.path.join(HERE, '_sage_conf', '_conf.py'))
        shutil.copyfile(os.path.join(SAGE_ROOT, 'src', 'bin', 'sage-env-config'),
                        os.path.join(HERE, 'bin', 'sage-env-config'))

        setuptools_build_py.run(self)

    def _create_writable_sage_root(self):
        HERE = os.path.dirname(__file__)
        DOT_SAGE = os.environ.get('DOT_SAGE', os.path.join(os.environ.get('HOME'), '.sage'))
        with open(os.path.join(HERE, 'VERSION.txt')) as f:
            sage_version = f.read().strip()
        # After #30534, SAGE_LOCAL no longer contains any Python.  So we key the SAGE_ROOT only to Sage version
        # and architecture.
        system = platform.system()
        machine = platform.machine()
        arch_tag = f'{system}-{machine}'
        # TODO: Should be user-configurable with config settings
        SAGE_ROOT = os.path.join(DOT_SAGE, f'sage-{sage_version}-{arch_tag}-conda')

        def ignore(path, names):
            # exclude all embedded src trees
            if fnmatch.fnmatch(path, '*/build/pkgs/*'):
                return ['src']
            ### ignore more stuff --- .tox etc.
            return [name for name in names
                    if name in ('.tox', '.git', '__pycache__',
                                'prefix', 'local', 'venv', 'upstream',
                                'config.status', 'config.log', 'logs')]

        if not os.path.exists(os.path.join(SAGE_ROOT, 'config.status')):
            # config.status and other configure output has to be writable.
            # So (until the Sage distribution supports VPATH builds - #21469), we have to make a copy of sage_root.
            try:
                shutil.copytree('sage_root', SAGE_ROOT,
                                ignore=ignore)  # will fail if already exists
            except Exception as e:
                raise SetupError(f"the directory SAGE_ROOT={SAGE_ROOT} already exists but it is not configured ({e}). "
                                 "Please either remove it and try again, or install in editable mode (pip install -e).")

        return SAGE_ROOT


class build_scripts(distutils_build_scripts):

    def run(self):
        self.distribution.scripts.append(os.path.join('bin', 'sage-env-config'))
        if not self.distribution.entry_points:
            self.entry_points = self.distribution.entry_points = dict()
        distutils_build_scripts.run(self)


class editable_wheel(setuptools_editable_wheel):
    r"""
    Customized so that exceptions raised by our build_py
    do not lead to the "Customization incompatible with editable install" message
    """
    _safely_run = setuptools_editable_wheel.run_command


setup(
    cmdclass=dict(build_py=build_py,
                  build_scripts=build_scripts,
                  editable_wheel=editable_wheel)
)
