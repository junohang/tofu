""" A tomography library for fusion devices

See:
https://github.com/ToFuProject/tofu
"""
import os
import sys
import glob
import shutil
import logging
import platform
import subprocess
from codecs import open
import Cython as cth
from Cython.Distutils import build_ext
from Cython.Build import cythonize
import numpy as np

from distutils.command.clean import clean as Clean


print("cython version =", cth.__version__)
print("numpy  version =", np.__version__)
print("cython version =", cth.__file__)
print("numpy  version =",  np.__file__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tofu.setup")

# Always prefer setuptools over distutils
try:
    from setuptools import setup, find_packages
    from setuptools import Extension
    stp = True
except:
    from distutils.core import setup
    from distutils.extension import Extension
    stp = False
import _updateversion as up

is_platform_windows = False
if platform.system() == "Windows":
    is_platform_windows = True

if platform.system() == "Darwin":
    # make sure you are using Homebrew's compiler
    os.environ['CC'] = 'gcc-8'
    os.environ['CXX'] = 'g++-8'
else:
    os.environ['CC'] = 'gcc'
    os.environ['CXX'] = 'g++'

# ==============================================================================
class CleanCommand(Clean):
    description = "Remove build artifacts from the source tree"

    def expand(self, path_list):
        """Expand a list of path using glob magic.
        :param list[str] path_list: A list of path which may contains magic
        :rtype: list[str]
        :returns: A list of path without magic
        """
        path_list2 = []
        for path in path_list:
            if glob.has_magic(path):
                iterator = glob.iglob(path)
                path_list2.extend(iterator)
            else:
                path_list2.append(path)
        return path_list2

    def find(self, path_list):
        """Find a file pattern if directories.
        Could be done using "**/*.c" but it is only supported in Python 3.5.
        :param list[str] path_list: A list of path which may contains magic
        :rtype: list[str]
        :returns: A list of path without magic
        """
        import fnmatch
        path_list2 = []
        for pattern in path_list:
            for root, _, filenames in os.walk('.'):
                for filename in fnmatch.filter(filenames, pattern):
                    path_list2.append(os.path.join(root, filename))
        return path_list2

    def run(self):
        Clean.run(self)

        cython_files = self.find(["*.pyx"])
        cythonized_files = [path.replace(".pyx", ".c") for path in cython_files]
        cythonized_files += [path.replace(".pyx", ".cpp") for path in cython_files]
        so_files = self.find(["*.so"])
        # really remove the directories
        # and not only if they are empty
        to_remove = [self.build_base]
        to_remove = self.expand(to_remove)
        to_remove += cythonized_files
        to_remove += so_files

        if not self.dry_run:
            for path in to_remove:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    logger.info("removing '%s'", path)
                except OSError:
                    pass
# ==============================================================================


# ==============================================================================
# Check if openmp available
# see http://openmp.org/wp/openmp-compilers/
omp_test = \
r"""
#include <omp.h>
#include <stdio.h>
int main() {
#pragma omp parallel
printf("Hello from thread %d, nthreads %d\n", omp_get_thread_num(),
       omp_get_num_threads());
}
"""

def check_for_openmp(cc_var):
    import tempfile
    tmpdir = tempfile.mkdtemp()
    curdir = os.getcwd()
    os.chdir(tmpdir)

    filename = r'test.c'
    with open(filename, 'w') as file:
        file.write(omp_test)
    with open(os.devnull, 'w') as fnull:
        result = subprocess.call([cc_var, '-fopenmp', filename],
                                 stdout=fnull, stderr=fnull)

    os.chdir(curdir)
    #clean up
    shutil.rmtree(tmpdir)
    return result

# ....... Using function
print("................ checking if openmp installed...")
if is_platform_windows:
    openmp_installed = False
else:
    openmp_installed = not check_for_openmp(os.environ['CC'])
print("................ checking if openmp installed... > ", openmp_installed)

# To compile the relevant version
if sys.version[:3] in ['2.7','3.6','3.7']:
    gg = '_GG0%s' % sys.version[0]
    poly = 'polygon%s' % sys.version[0]
else:
    raise Exception("Pb. with python version in setup.py file: "+sys.version)


if sys.version[0] == '2':
    extralib = ['funcsigs']
else:
    extralib = []
# ==============================================================================




_HERE = os.path.abspath(os.path.dirname(__file__))

def get_version_tofu(path=_HERE):

    # Try from git
    isgit = '.git' in os.listdir(path)
    if isgit:
        try:
            if sys.version[0]=='2':
                git_branch = subprocess.check_output(["git",
                                                      "rev-parse",
                                                      "--symbolic-full-name",
                                                      "--abbrev-ref",
                                                      "HEAD"]).rstrip()
            elif sys.version[0]=='3':
                git_branch = subprocess.check_output(["git",
                                                      "rev-parse",
                                                      "--symbolic-full-name",
                                                      "--abbrev-ref",
                                                      "HEAD"]).rstrip().decode()
            if git_branch in ['master']:
                version_tofu = up.updateversion(os.path.join(path,'tofu'))
            else:
                isgit = False
        except Exception as err:
            isgit = False

    if not isgit:
        version_tofu = os.path.join(path,'tofu')
        version_tofu = os.path.join(version_tofu,"version.py")
        with open(version_tofu,'r') as fh:
            version_tofu = fh.read().strip().split("=")[-1].replace("'",'')

    version_tofu = version_tofu.lower().replace('v','')
    return version_tofu

version_tofu = get_version_tofu(path=_HERE)

print("")
print("Version for setup.py : ", version_tofu)
print("")


# Getting relevant compilable files
if sys.version[0]=='3':
    #if not '_GG03.pyx' in os.listdir(os.path.join(_HERE,'tofu/geom/')):
    shutil.copy2(os.path.join(_HERE,'tofu/geom/_GG02.pyx'),
                 os.path.join(_HERE,'tofu/geom/_GG03.pyx'))

# Get the long description from the README file
with open(os.path.join(_HERE, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

#  ... Compiling files .........................................................
if openmp_installed :
    extra_compile_args=["-O0", "-Wall", "-fopenmp", "-fno-wrapv"]
    extra_link_args = ["-fopenmp"]
else:
    extra_compile_args=["-O0", "-Wall", "-fno-wrapv"]
    extra_link_args = []

extensions = [ Extension(name="tofu.geom."+gg,
                         sources=["tofu/geom/"+gg+".pyx"],
                         extra_compile_args=extra_compile_args,
                         extra_link_args=extra_link_args),
              Extension(name="tofu.geom._basic_geom_tools",
                        sources=["tofu/geom/_basic_geom_tools.pyx"],
                        extra_compile_args=extra_compile_args,
                        extra_link_args=extra_link_args),
              Extension(name="tofu.geom._distance_tools",
                        sources=["tofu/geom/_distance_tools.pyx"],
                        extra_compile_args=extra_compile_args,
                        extra_link_args=extra_link_args),
              Extension(name="tofu.geom._sampling_tools",
                        sources=["tofu/geom/_sampling_tools.pyx"],
                        extra_compile_args=extra_compile_args,
                        extra_link_args=extra_link_args),
              Extension(name="tofu.geom._raytracing_tools",
                        sources=["tofu/geom/_raytracing_tools.pyx"],
                        extra_compile_args=extra_compile_args,
                        extra_link_args=extra_link_args),
              Extension(name="tofu.geom._vignetting_tools",
                        sources=["tofu/geom/_vignetting_tools.pyx"],
                        language="c++",
                        extra_compile_args=extra_compile_args,
                        extra_link_args=extra_link_args),
              ]

extensions = cythonize(extensions, annotate=True)


setup(
    name='tofu',
    #version="1.2.27",
    version="{ver}".format(ver=version_tofu),
    # Use scm to get code version from git tags
    # cf. https://pypi.python.org/pypi/setuptools_scm
    # Versions should comply with PEP440. For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    # The version is stored only in the setup.py file and read from it (option 1
    # in https://packaging.python.org/en/latest/single_source_version.html)
    use_scm_version=False,
    #setup_requires=['setuptools_scm'],

    description='A python library for Tomography for Fusion',
    long_description=long_description,

    # The project's main homepage.
    url='https://github.com/ToFuProject/tofu',

    # Author details
    author='Didier VEZINET',
    author_email='didier.vezinet@gmail.com',


    # Choose your license
    license='MIT',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        # 3 - Alpha
        # 4 - Beta
        # 5 - Production/Stable
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: Physics',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',

        # In which language most of the code is written ?
        'Natural Language :: English',
    ],

    # What does your project relate to?
    keywords='tomography geometry 3D inversion synthetic fusion',

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages = find_packages(exclude=['doc', '_Old', '_Old_doc','plugins',
                                      'plugins.*','*.plugins.*','*.plugins',
                                      '*.tests10_plugins','*.tests10_plugins.*',
                                      'tests10_plugins.*','tests10_plugins',]),
    #packages = ['tofu','tofu.geom'],

    # Alternatively, if you want to distribute just a my_module.py, uncomment
    # this:
    # py_modules=["my_module"],

    # List run-time dependencies here. These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=[
            'numpy',
            'scipy',
            'matplotlib',
            poly,
            'cython>=0.26',
            ] + extralib,

    python_requires = '>=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,!=3.4.*,!=3.5.*',


    # List additional groups of dependencies here (e.g. development
    # dependencies). You can install these using the following syntax,
    # for example:
    # $ pip install -e .[dev,test]
    extras_require={
        'dev': ['check-manifest'],
        'test': ['coverage','nose==1.3.4'],
    },

    # If there are data files included in your packages that need to be
    # installed, specify them here. If using Python 2.6 or less, then these
    # have to be included in MANIFEST.in as well.
    #package_data={
    #    # If any package contains *.txt, *.rst or *.npz files, include them:
    #    '': ['*.txt', '*.rst', '*.npz'],
    #    # And include any *.csv files found in the 'ITER' package, too:
    #    'ITER': ['*.csv'],
    #},
    package_data={'tofu.tests.tests01_geom.tests03core_data':['*.py','*.txt'],
                  'tofu.geom.inputs':['*.txt']},

    include_package_data=True,

    # Although 'package_data' is the preferred approach, in some case you may
    # need to place data files outside of your packages. See:
    # http://docs.python.org/3.4/distutils/setupscript.html
    #installing-additional-files # noqa
    # In this case, 'data_file' will be installed into '<sys.prefix>/my_data'
    #data_files=[('my_data', ['data/data_file'])],

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    #entry_points={
    #    'console_scripts': [
    #        'sample=sample:main',
    #    ],
    #},

    ext_modules = extensions,
    cmdclass={'build_ext':build_ext,
              'clean':CleanCommand},
    include_dirs=[np.get_include()],
)
