# Vault — Financial Tracker (Desktop App)

## First-time Setup

1. Make sure Node.js is installed (node --version should show v20+)
2. Double-click **SETUP.bat** — waits for it to finish
3. Double-click **START.bat** to launch the app

Your data saves automatically to:
  Documents\FinancialTracker\financial-tracker-data.json

## Enabling the AI Chatbot

1. Go to console.anthropic.com → API Keys → Create Key
2. Copy the key (starts with sk-ant-...)
3. Press Windows key, search "environment variables"
4. Click "Edit the system environment variables" → Environment Variables
5. Under User Variables click New:
   - Variable name:  ANTHROPIC_API_KEY
   - Variable value: (paste your key)
6. Click OK and restart the app
7. The chatbot will now work automatically

## Data Backup

Your data file lives at:
  C:\Users\[you]\Documents\FinancialTracker\financial-tracker-data.json

Back it up by copying it to Google Drive or any folder you want.
To use it on another computer, copy the whole FinancialTracker folder there.

## Importing Old App Data

Click "⇄ Import from Old App" in the sidebar and select your old JSON export.
