@echo off
REM Usage: commit.bat "type(scope): subject" [--no-push]
REM Stages all changes, commits with the supplied message, optionally pushes.
cd /d "%~dp0"

if "%~1"=="" (
  echo ERROR: commit message is required.
  echo Example: commit.bat "fix(api): handle empty payload"
  exit /b 1
)

git add -A
git commit -m %1
if errorlevel 1 exit /b %errorlevel%

if /I not "%~2"=="--no-push" (
  git push
)
