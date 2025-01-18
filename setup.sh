#!/bin/bash

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "❌ Python is not installed. Please install Python 3.8 or higher"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 16 or higher"
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install npm"
    exit 1
fi

echo "
*******************************************
*                                         *
*   🎉 Welcome to Director Setup! 🎉      *
*                                         *
*******************************************
"

# Collect API keys
echo "🔑 VideoDB API Key (https://console.videodb.io/) (Press Enter to skip)"
read VIDEO_DB_API_KEY

echo "🔑 OpenAI API Key (https://platform.openai.com/api-keys) (Press Enter to skip)"
read OPENAI_API_KEY

echo "🔑 Bland AI API Key (https://www.bland.ai/dashboard) (Press Enter to skip)"
read BLAND_AI_API_KEY

# Create a .env file and add the content
echo "📝 Creating .env file with provided API keys..."
cat <<EOT > .env
VIDEO_DB_API_KEY=$VIDEO_DB_API_KEY
OPENAI_API_KEY=$OPENAI_API_KEY
BLAND_AI_API_KEY=$BLAND_AI_API_KEY
EOT

cd ..

make install-be
make init-sqlite-db

# Frontend setup
cd frontend

echo "
🌳 Using Node@$(node -v): $(which node)"
echo "🌳 Using npm@$(npm -v): $(which npm)"

cat <<EOT > .env
VITE_APP_BACKEND_URL=http://127.0.0.1:8000
VITE_PORT=8080
VITE_OPEN_BROWSER=true
EOT
cd ../

make install-fe
make update-fe

echo "
*******************************************
*                                         *
*   🎉 Setup Completed Successfully! 🎉   *
*                                         *
*      🚀 IMPORTANT: Next Steps 🚀        *
*                                         *
* 1. Review and Update .env File:         *
*    - Check the newly created .env file  *
*    - Add any missing API keys:          *
*      - VIDEO_DB_API_KEY                 *
*      - OPENAI_API_KEY                   *
*      - BLAND_AI_API_KEY                 *
*                                         *
* 2. Start the Application:               *
*    Run the following command:           *
*    $ make run                           *
*                                         *
*******************************************"