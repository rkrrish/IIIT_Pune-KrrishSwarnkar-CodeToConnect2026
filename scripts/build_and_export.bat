@echo off
setlocal enabledelayedexpansion

echo ====================================================================
echo  S^&P 100 NLP Risk Engine - Docker Image Exporter (Windows)
echo ====================================================================
echo.

echo [*] Building all-in-one standalone Docker image: snp-nlp-engine:latest...
docker build -t snp-nlp-engine:latest -f Dockerfile.standalone .
if %ERRORLEVEL% neq 0 (
    echo [!] Docker build failed! Please ensure Docker Desktop is running.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [*] Saving Docker image to archive: snp_docker_image.tar...
docker save snp-nlp-engine:latest -o snp_docker_image.tar
if %ERRORLEVEL% neq 0 (
    echo [!] Failed to save image archive.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ====================================================================
echo [SUCCESS] Portable Docker package generated:
echo   File: %CD%\snp_docker_image.tar
echo.
echo To replicate on ANY other computer:
echo   1. Send 'snp_docker_image.tar' and 'scripts\import_and_run.bat'
echo   2. On the other computer, double-click 'import_and_run.bat'
echo      (Or run: docker load -i snp_docker_image.tar)
echo   3. Open http://localhost:8000 in any browser!
echo ====================================================================
pause
