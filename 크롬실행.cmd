@echo off
chcp 65001 >nul
rem 금융결제원 전용 크롬. 공동인증서 로그인은 사용자가 직접 진행합니다.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome-kftc" --no-first-run --no-default-browser-check "https://audit.kftc.or.kr/"
