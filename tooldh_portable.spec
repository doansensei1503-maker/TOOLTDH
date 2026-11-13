# -*- mode: python ; coding: utf-8 -*-
# P4-B1 portable build: PyInstaller --onedir, no browser profile/data bundled.
block_cipher = None

a = Analysis(
    ['tooldh_portable.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('web', 'web'),
        ('config.yaml', '.'),
    ],
    hiddenimports=[
        'dashboard_server', 'dashboard_service', 'project_store',
        'p3_publish', 'storage', 'history', 'task_queue', 'scheduler',
        'brain', 'discover', 'discovery_live', 'candidate_analysis',
        'local_analyzer', 'local_vision', 'review_stage', 'reviewer',
        'ingest', 'library', 'snaptik', 'tiktok_metrics', 'eligibility',
        'p2_lab', 'workflow', 'main',
        'yaml', 'dotenv', 'apscheduler', 'apscheduler.schedulers.background',
        'playwright',
    ],
    hookspath=['build_hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TOOLTDH',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TOOLTDH',
)
