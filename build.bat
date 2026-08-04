@echo off
chcp 65001 >nul 2>&1
title FAPEMIG PDFs - Build

echo ============================================
echo   FAPEMIG PDFs - Gerador de Executavel
echo ============================================
echo.

:: Verificar se Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale o Python 3.10+ e tente novamente.
    pause
    exit /b 1
)

:: Verificar se PyInstaller esta instalado
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller nao encontrado. Instalando...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar PyInstaller.
        pause
        exit /b 1
    )
)

:: Verificar dependencias
echo [1/3] Verificando dependencias...
pip install flask PyMuPDF >nul 2>&1

:: Limpar build anterior
echo [2/3] Limpando build anterior...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "FAPEMIG_PDFs.spec" del "FAPEMIG_PDFs.spec"

:: Gerar executavel
echo [3/3] Gerando executavel...
echo.

pyinstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "FAPEMIG_PDFs" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    app.py

echo.
if exist "dist\FAPEMIG_PDFs.exe" (
    echo ============================================
    echo   BUILD CONCLUIDO COM SUCESSO!
    echo   Executavel: dist\FAPEMIG_PDFs.exe
    echo ============================================
) else (
    echo ============================================
    echo   [ERRO] Build falhou. Verifique os logs.
    echo ============================================
)

echo.
pause
