# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH)
ICON_PATH = str(ROOT / "worktrace.ico")

datas = [
    (str(ROOT / "prompts"), "prompts"),
    (str(ROOT / "worktrace" / "ui" / "static"), "worktrace/ui/static"),
    (str(ROOT / "config.example.yaml"), "."),
    (str(ROOT / "config.lan.example.yaml"), "."),
]
datas += collect_data_files("webview")

hiddenimports = [
    "PIL._tkinter_finder",
    "win32timezone",
    "clr",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "webview.platforms.mshtml",
]
hiddenimports += collect_submodules("pythonnet")
hiddenimports += collect_submodules("clr_loader")
hiddenimports += collect_submodules("proxy_tools")

excludes = [
    "alabaster",
    "bcrypt",
    "cryptography",
    "docutils",
    "IPython",
    "ipywidgets",
    "invoke",
    "jupyter_client",
    "jupyter",
    "matplotlib",
    "notebook",
    "numpy",
    "numpy.f2py",
    "mypy",
    "nacl",
    "OpenSSL",
    "pandas",
    "paramiko",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "qtpy",
    "pip",
    "pytest",
    "scipy",
    "setuptools.tests",
    "sphinx",
    "tornado",
    "traitlets",
    "twisted",
    "tkinter.test",
    "unittest.test",
    "wheel",
    "zmq",
    "webview.platforms.android",
    "webview.platforms.cef",
    "webview.platforms.cocoa",
    "webview.platforms.gtk",
    "webview.platforms.qt",
]


a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WorkTrace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=ICON_PATH,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
cli_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WorkTrace-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=ICON_PATH,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    cli_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WorkTrace",
)
