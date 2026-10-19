@echo off
chcp 65001 > nul
cd /d "%~dp0"

where python > nul 2> nul
if errorlevel 1 (
  echo 파이썬이 설치되어 있지 않습니다. README의 설치 방법을 확인해 주세요.
  pause
  exit /b 1
)

if not exist .venv (
  echo 처음 실행: 필요한 프로그램을 설치합니다. 몇 분 걸릴 수 있습니다...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt

rem Streamlit 첫 실행 시 이메일 입력 질문을 건너뛴다
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  mkdir "%USERPROFILE%\.streamlit" 2> nul
  (echo [general]& echo email = "") > "%USERPROFILE%\.streamlit\credentials.toml"
)

echo 브라우저에서 앱이 열립니다. 종료하려면 이 창을 닫으세요.
streamlit run app.py
pause
