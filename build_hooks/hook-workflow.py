"""Local PyInstaller hook override for P4-B1.

The contrib hook `hook-workflow.py` targets a third-party package named
`workflow`, but this project has its own top-level `workflow.py`. The
contrib hook fails to import its own hidden module and aborts the build,
so this local hook shadows it and does nothing: the project module is
collected as a normal source module.
"""
