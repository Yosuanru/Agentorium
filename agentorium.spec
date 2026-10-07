# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve()
runtime_data = [
    # 整个 assets 目录一起带上。
    # 原来是一个文件一个文件列的——我后来加了四个展开箭头（branch-*.svg），
    # 忘了往这儿补，打出来的包缺图标。按目录带就不会再有这种漏。
    (str(project_root / "assets"), "assets"),
    (str(project_root / "VERSION"), "."),
    (str(project_root / "licenses"), "licenses"),
    (str(project_root / "LICENSE"), "."),
    (str(project_root / "PRIVACY.md"), "."),
    (str(project_root / "README.md"), "."),
    (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project_root / "config.example.json"), "."),
]

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=runtime_data,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Agentorium",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Agentorium",
)
