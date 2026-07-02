@echo off
setlocal EnableExtensions
rem SynaBoot HotPE automatic SMB mount script.
rem Generated runtime copy may contain credentials and must stay outside Git and /images.

set "SYNABOOT_SMB_HOST={{SMB_HOST}}"
set "SYNABOOT_SMB_USER={{SMB_USER}}"
set "SYNABOOT_IMAGES_SHARE={{IMAGES_SHARE}}"
set "SYNABOOT_MODULES_SHARE={{MODULES_SHARE}}"
set "SYNABOOT_WINDOWS_SHARE={{WINDOWS_SHARE}}"
set "SYNABOOT_PASSWORD={{SMB_PASSWORD}}"

call :MountShare Z: "\\%SYNABOOT_SMB_HOST%\%SYNABOOT_IMAGES_SHARE%" "SynaBoot image repository"
call :MountShare M: "\\%SYNABOOT_SMB_HOST%\%SYNABOOT_MODULES_SHARE%" "HotPE runtime modules"
call :MountShare W: "\\%SYNABOOT_SMB_HOST%\%SYNABOOT_WINDOWS_SHARE%" "Windows install media"

if exist "%SystemDrive%\Users\Public\Desktop" (
  > "%SystemDrive%\Users\Public\Desktop\SynaBoot-Open-Modules.cmd" echo @echo off
  >> "%SystemDrive%\Users\Public\Desktop\SynaBoot-Open-Modules.cmd" echo start "" "M:\"
)

call "%~dp0load-hotpe-modules.cmd"
echo SynaBoot HotPE SMB setup completed.
exit /b 0

:MountShare
set "DRIVE=%~1"
set "UNC=%~2"
set "LABEL=%~3"
net use %DRIVE% /delete /y >nul 2>nul
net use %DRIVE% "%UNC%" /user:%SYNABOOT_SMB_USER% "%SYNABOOT_PASSWORD%" /persistent:no
if errorlevel 1 (
  echo [WARN] Failed to mount %LABEL% at %DRIVE% from %UNC%.
) else (
  echo [OK] Mounted %LABEL% at %DRIVE%.
)
exit /b 0
