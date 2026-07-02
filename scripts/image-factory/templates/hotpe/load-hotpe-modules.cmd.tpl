@echo off
setlocal EnableExtensions
rem SynaBoot HotPE HPM loader.
rem It opens reviewed HPM files from the mounted M: drive. HotPE decides how to import them.

if not exist "M:\" (
  echo [WARN] HotPE module drive M: is not mounted.
  exit /b 0
)

{{MODULE_LOAD_LINES}}

start "" "M:\"
exit /b 0
