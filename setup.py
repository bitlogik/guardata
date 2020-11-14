#!/usr/bin/env python3
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS


from platform import system
from setuptools import setup, find_packages, distutils, Command
from setuptools.command.build_py import build_py


__version__ = None
exec(open("guardata/_version.py", encoding="utf-8").read())


def fix_pyqt_import():
    # PyQt5-sip is a distinct pip package that provides PyQt5.sip
    # However it setuptools handles `setup_requires` by downloading the
    # dependencies in the `./.eggs` directory without really installing
    # them. This causes `import PyQt5.sip` to fail given the `PyQt5` folder
    # doesn't contains `sip.so` (or `sip.pyd` on windows)...
    import sys
    import glob
    import importlib

    for module_name, path_glob in (
        ("PyQt5", ".eggs/*PyQt5*/PyQt5/__init__.py"),
        ("PyQt5.sip", ".eggs/*PyQt5_sip*/PyQt5/sip.*"),
    ):
        # If the module has already been installed in the environment
        # setuptools won't populate the `.eggs` directory and we have
        # nothing to do
        try:
            importlib.import_module(module_name)
        except ImportError:
            pass
        else:
            continue

        for path in glob.glob(path_glob):

            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                break

        else:
            raise RuntimeError("Cannot found module `%s` in .eggs" % module_name)


class GeneratePyQtResourcesBundle(Command):
    description = "Generates `guardata.client.gui._resource_rc` bundle module"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        fix_pyqt_import()
        try:
            from PyQt5.pyrcc_main import processResourceFile

            self.announce(
                "Generating `guardata.client.gui._resources_rc`", level=distutils.log.INFO
            )
            processResourceFile(
                ["guardata/client/gui/rc/resources.qrc"],
                "guardata/client/gui/_resources_rc.py",
                False,
            )
        except ImportError:
            print("PyQt5 not installed, skipping `guardata.client.gui._resources_rc` generation.")


class GeneratePyQtForms(Command):
    description = "Generates `guardata.client.ui.*` forms module"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import os
        import pathlib
        from collections import namedtuple

        fix_pyqt_import()
        try:
            from PyQt5.uic.driver import Driver
        except ImportError:
            print("PyQt5 not installed, skipping `guardata.client.gui.ui` generation.")
            return

        self.announce("Generating `guardata.client.gui.ui`", level=distutils.log.INFO)
        Options = namedtuple(
            "Options",
            ["output", "import_from", "debug", "preview", "execute", "indent", "resource_suffix"],
        )
        ui_dir = pathlib.Path("guardata/client/gui/forms")
        ui_path = "guardata/client/gui/ui"
        os.makedirs(ui_path, exist_ok=True)
        for f in ui_dir.iterdir():
            o = Options(
                output=os.path.join(ui_path, "{}.py".format(f.stem)),
                import_from="guardata.client.gui",
                debug=False,
                preview=False,
                execute=False,
                indent=4,
                resource_suffix="_rc",
            )
            d = Driver(o, str(f))
            d.invoke()


class ExtractTranslations(Command):
    description = "Extract translation strings"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import os
        import pathlib
        from unittest.mock import patch
        from babel.messages.frontend import CommandLineInterface

        fix_pyqt_import()
        try:
            from PyQt5.pylupdate_main import main as pylupdate_main
        except ImportError:
            print("PyQt5 not installed, skipping `guardata.client.gui.ui` generation.")
            return

        self.announce("Generating ui translation files", level=distutils.log.INFO)
        ui_dir = pathlib.Path("guardata/client/gui")
        tr_dir = ui_dir / "tr"
        os.makedirs(tr_dir, exist_ok=True)

        new_args = ["pylupdate", str(ui_dir / "guardata-gui.pro")]
        with patch("sys.argv", new_args):
            pylupdate_main()

        files = [str(f) for f in ui_dir.iterdir() if f.is_file() and f.suffix == ".py"]
        files.append(str(tr_dir / "guardata_en.ts"))
        args = [
            "_",
            "extract",
            "-s",
            "--no-location",
            "-F",
            ".babel.cfg",
            "--omit-header",
            "-o",
            str(tr_dir / "translation.pot"),
            *files,
        ]
        CommandLineInterface().run(args)
        languages = ["fr", "en"]
        for lang in languages:
            po_file = tr_dir / f"guardata_{lang}.po"
            if not po_file.is_file():
                po_file.touch()
            args = [
                "_",
                "update",
                "-i",
                str(tr_dir / "translation.pot"),
                "-o",
                str(po_file),
                "-l",
                lang,
            ]
            CommandLineInterface().run(args)


class CompileTranslations(Command):
    description = "Compile translations"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import os
        import pathlib
        from babel.messages.frontend import CommandLineInterface

        self.announce("Compiling ui translation files", level=distutils.log.INFO)
        ui_dir = pathlib.Path("guardata/client/gui")
        tr_dir = ui_dir / "tr"
        rc_dir = ui_dir / "rc" / "translations"
        os.makedirs(rc_dir, exist_ok=True)
        languages = ["fr", "en"]
        for lang in languages:
            args = [
                "_",
                "compile",
                "-i",
                str(tr_dir / f"guardata_{lang}.po"),
                "-o",
                str(rc_dir / f"guardata_{lang}.mo"),
            ]
            CommandLineInterface().run(args)


class build_py_with_pyqt(build_py):
    def run(self):
        self.run_command("generate_pyqt_forms")
        self.run_command("compile_translations")
        self.run_command("generate_pyqt_resources_bundle")
        return super().run()


class build_py_with_pyqt_resource_bundle_generation(build_py):
    def run(self):
        self.run_command("generate_pyqt_resources_bundle")
        return super().run()


with open("README.rst") as readme_file:
    readme = readme_file.read()


pyQT5_version = "5.14.2"
if system() == "Darwin":
    pyQT5_version = "5.13.1"
PYQT_DEPS = [f"PyQt5=={pyQT5_version}", "pyqt5-sip==12.8.0"]
BABEL_DEP = "Babel==2.6.0"


requirements = [
    "attrs==19.2.0",
    "click==7.0",
    "msgpack==0.6.2",
    "wsproto==0.15.0",
    "toastedmarshmallow==0.2.6",
    "pendulum==2.1.2",
    "PyNaCl==1.4.0",
    "trio==0.16.0",
    "async_generator>=1.9",
    'contextvars==2.1;python_version<"3.7"',
    "structlog==19.2.0",
    "importlib_resources==1.0.2",
    "colorama==0.4.0",
    "async_exit_stack==1.0.1",
    "outcome==1.0.0",
    "packaging==20.4",
    *PYQT_DEPS,
    BABEL_DEP,
    'fusepy==3.0.1;platform_system=="Linux" or platform_system=="Darwin"',
    'winfspy==0.8.0;platform_system=="Windows"',
    "zxcvbn==4.4.28",
    "psutil==5.6.3",
]


test_requirements = [
    "jinja2==2.11.2",
    "pytest==5.4.3",
    "pytest-xdist==1.32.0",
    "pytest-trio==0.5.2",
    "pytest-qt==3.3.0",
    "pytest-rerunfailures==9.0",
    "hypothesis==5.3.0",
    "hypothesis-trio==0.5.0",
    "trustme==0.6.0",
    'pywin32==227;platform_system=="Windows"',
    "pbr==4.0.2",
    "triopg==0.5.0",
    "trio-asyncio==0.11.0",
]


WHEEL_DEP = "wheel==0.34.2"

extra_requirements = {"dev": test_requirements}
extra_requirements["all"] = extra_requirements["dev"]

setup(
    name="guardata",
    version=__version__,
    description="Desktop client for a modern and trustless data cloud storage service",
    long_description=readme + "\n\n",
    author="BitLogiK",
    author_email="contact@bitlogik.fr",
    url="https://guardata.app",
    python_requires=">=3.6",
    packages=find_packages(include=["guardata", "guardata.*"]),
    package_dir={"guardata": "guardata"},
    setup_requires=[WHEEL_DEP, *PYQT_DEPS, BABEL_DEP],
    install_requires=requirements,
    extras_require=extra_requirements,
    cmdclass={
        "generate_pyqt_resources_bundle": GeneratePyQtResourcesBundle,
        "generate_pyqt_forms": GeneratePyQtForms,
        "extract_translations": ExtractTranslations,
        "compile_translations": CompileTranslations,
        "generate_pyqt": build_py_with_pyqt,
        "build_py": build_py_with_pyqt,
    },
    package_data={"guardata.client.resources": ["*.ico", "*.icns", "*.ignore"]},
    entry_points={
        "console_scripts": ["guardata = guardata.cli:cli"],
        "babel.extractors": ["extract_qt = misc.babel_qt_extractor.extract_qt"],
    },
    license="AGPLv3",
    zip_safe=False,
    keywords="cloud data storage sharing cryptography",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: Microsoft :: Windows :: Windows 8",
        "Operating System :: Microsoft :: Windows :: Windows 8.1",
        "Operating System :: Microsoft :: Windows :: Windows 10",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Topic :: Communications :: File Sharing",
        "Topic :: Office/Business",
        "Topic :: Security :: Cryptography",
        "Topic :: System :: Archiving :: Backup",
    ],
    long_description_content_type="text/x-rst",
)
