@echo off
chcp 65001 >nul
REM 撤销 信任HTTPS证书.bat 的效果：从当前用户信任根里删掉 PestGuard 自签证书
set CERT=%~dp0pestguard-https.crt

if not exist "%CERT%" (
  echo [错误] 找不到证书文件：%CERT%
  pause
  exit /b 1
)

certutil -user -delstore Root "PestGuard" >nul 2>&1
echo 已尝试移除 PestGuard 自签证书。
echo 如需确认，可在运行里输入 certmgr.msc 查看「受信任的根证书颁发机构 - 证书」。
pause
