@echo off
chcp 65001 >nul
REM ============================================================
REM  PestGuard 自签 HTTPS 证书 —— 一键信任（当前用户，无需管理员）
REM
REM  作用：让本机浏览器访问你的自签 HTTPS 地址（如 https://<服务器IP>:8000）
REM        时不再出现「你的连接不是专用连接」警告，摄像头等需要安全
REM        上下文的功能（拍照识别）才能正常使用。
REM
REM  撤销：运行 撤销HTTPS证书信任.bat
REM ============================================================

set CERT=%~dp0pestguard-https.crt

if not exist "%CERT%" (
  echo [错误] 找不到证书文件：%CERT%
  echo 请把 pestguard-https.crt 放到本脚本同一目录下再运行。
  pause
  exit /b 1
)

echo 正在把证书加入当前用户的「受信任的根证书颁发机构」...
certutil -user -addstore -f Root "%CERT%" >nul 2>&1

if errorlevel 1 (
  echo [失败] 导入未成功，请以普通用户身份重新运行本脚本。
  pause
  exit /b 1
)

echo.
echo [完成] 证书已信任。
echo 请完全关闭浏览器后重新打开你的 HTTPS 地址（如 https://^<服务器IP^>:8000）
echo 地址栏应显示正常连接，点「拍照」即可调用摄像头。
echo.
pause
