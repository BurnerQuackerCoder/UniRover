# UniRover - Indoor Delivery System

UniRover is a minimal yet functional full-stack application for managing an indoor delivery system, suitable for environments like hospitals, offices, or campuses. It features a modern tech stack with a Python/FastAPI backend and a TypeScript/React frontend.

## Tech Stack

-   **Backend**: Python 3.11, FastAPI, SQLAlchemy, SQLite
-   **Frontend**: TypeScript, React, Vite, Tailwind CSS
-   **Authentication**: JWT (JSON Web Tokens)
-   **Database**: SQLite for simplicity
-   **Development**: Visual Studio Code

## Project Structure
UniRover/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py
│   │   ├── auth.py
│   │   ├── crud.py
│   │   ├── database.py
│   │   ├── dependencies.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── create_admin.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── context/
│   │   ├── hooks/
│   │   └── pages/
│   ├── package.json
│   └── ...
└── .vscode/
└── launch.json

## Prerequisites

-   **Python**: Version 3.10 or 3.11.
-   **Node.js**: Version 18.x or 20.x.
-   **Build Tools (Optional)**: For some systems, certain Python packages may require compilation. Ensure you have the necessary build tools (like Microsoft Visual C++ Build Tools on Windows or build-essentials on Linux) and [Rust](https://www.rust-lang.org/tools/install) installed to avoid potential errors.

## Setup and Installation

### 1. Backend Setup


# Navigate to the backend directory
cd backend

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

### 2. Create an Admin User
To manage the system, you need an admin account. Run the interactive script to create one.

# Make sure your backend virtual environment is active
python create_admin.py

Follow the prompts to set the admin's email and password.

### 3. Frontend Setup

# Navigate to the frontend directory from the root
cd frontend

# Install dependencies
npm install

### 4. Running the Application
Method 1: Using VS Code (Recommended)
Open the project's root UniRover folder in VS Code.
Go to the "Run and Debug" panel (Ctrl+Shift+D).
Select "Run All (Backend + Frontend)" from the dropdown menu at the top.
Press the green play button (F5).
This will start both servers and open the application in your browser.

Method 2: Manual Start
You can run the backend and frontend manually in two separate terminals.

Terminal 1: Start Backend
# Navigate to the backend folder
cd backend

# Activate the virtual environment
# (e.g., venv\Scripts\activate)

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Terminal 2: Start Frontend
# Navigate to the frontend folder
cd frontend

# Run the dev server
npm run dev

### 5. Accessing the Application
Frontend UI: http://localhost:5173 (or whichever port Vite assigns)
Backend API Docs: http://localhost:8000/docs