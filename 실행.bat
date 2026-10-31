@echo off
chcp 65001 > nul
cd /d "%~dp0"

rem 이미 앱이 켜져 있으면 새로 켜지 않고 브라우저만 연다 (중복 실행 방지)
netstat -ano | findstr ":8501" | findstr "LISTENING" > nul
if not errorlevel 1 (
  echo 앱이 이미 켜져 있습니다. 브라우저 창을 엽니다.
  start "" http://localhost:8501
  timeout /t 3 > nul
  exit /b 0
)

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

rem requirements.txt가 바뀌었을 때만 부품을 설치한다
python -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())" > .venv\req.new
fc /b .venv\req.new .venv\req.hash > nul 2> nul
if errorlevel 1 (
  echo 필요한 부품을 설치합니다...
  python -m pip install -q -r requirements.txt
  if errorlevel 1 (
    echo 부품 설치에 실패했습니다. 인터넷 연결을 확인해 주세요.
    pause
    exit /b 1
  )
  copy /y .venv\req.new .venv\req.hash > nul
)

rem Streamlit 첫 실행 시 이메일 입력 질문을 건너뛴다
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  mkdir "%USERPROFILE%\.streamlit" 2> nul
  (echo [general]& echo email = "") > "%USERPROFILE%\.streamlit\credentials.toml"
)

echo 브라우저에서 앱이 열립니다. 종료하려면 이 창을 닫으세요.
streamlit run app.py
pause
