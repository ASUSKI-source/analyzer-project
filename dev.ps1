# Stocks/Crypto Analyzer - Unified Dev Starter
Write-Host "----------------------------------------------------" -ForegroundColor Cyan
Write-Host "Starting Stocks/Crypto Analyzer Dev Environment..." -ForegroundColor Cyan
Write-Host "----------------------------------------------------" -ForegroundColor Cyan

# 1. Start Backend in a new window
Write-Host "[1/2] Launching Backend (FastAPI) on http://localhost:8000" -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "title Backend; cd backend; .\venv\Scripts\Activate.ps1; uvicorn main:app --reload --port 8000"

# 2. Start Frontend in the current window
Write-Host "[2/2] Launching Frontend (Next.js) on http://localhost:3000" -ForegroundColor Green
Write-Host "Press Ctrl+C in this window to stop the frontend." -ForegroundColor DarkGray
cd frontend
npm run dev
