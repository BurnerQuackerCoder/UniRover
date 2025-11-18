# Zuse-Opta 🤖📦

**An Autonomous Indoor Delivery System powered by ROS 2, FastAPI, and React.**

Zuse-Opta is a full-stack robotic application designed to manage indoor logistics. It coordinates a mobile robot (ROSbot 2.0) to autonomously deliver items between rooms. It features a multi-user web interface for sending requests, an admin command center with live telemetry, and public kiosk stations for recipients.

---

## 🌟 Key Features

* **Autonomous Navigation:** Uses **ROS 2 Humble** and the **Nav2** stack for intelligent path planning and obstacle avoidance.
* **Smart Scheduling:** Features a Python-based scheduler that batches delivery requests and optimizes the route using the **Traveling Salesperson Problem (TSP)** algorithm.
* **Live Monitoring:** Admin dashboard features a real-time **Live Map** visualizing the robot's position and the facility map via WebSockets.
* **Recipient Kiosks:** Public-facing station interface (`/station/:name`) for recipients to confirm pickups without logging in.
* **Audio Feedback:** The robot announces its arrival at destinations using text-to-speech via Bluetooth speakers.
* **Robust Error Handling:** Includes automated "Emergency Return-to-Base" logic, timeout handling for navigation/pickups, and battery monitoring.
* **Secure:** User authentication with JWT and secure password hashing (bcrypt).

---

## 🏗️ System Architecture

The system is distributed across two main computing units:

1.  **Central Server (PC):**
    * **OS:** Ubuntu with ROS 2 Humble (usually inside a Docker container).
    * **Role:** The "Brain". Runs the Navigation Stack (Nav2), the Database, the Scheduler, the API Server, and the Frontend.
2.  **Robot (Edge) - Raspberry Pi 4:**
    * **OS:** Ubuntu / ROS 2 Humble (Dockerized).
    * **Role:** The "Body". Runs motor controllers, Lidar driver, and the Audio system.

---

## 🛠️ Prerequisites

### Hardware
* **Robot:** Husarion ROSbot 2.0 (RPi version) or similar ROS 2-compatible mobile base.
* **Sensors:** Lidar (e.g., RPLidar).
* **Audio:** Bluetooth Speaker connected to the Robot.
* **Network:** A reliable Wi-Fi network (Mesh recommended) connecting the Robot and PC.

### Software
* **Docker & Docker Compose:** Essential for running ROS 2 environments.
* **Node.js:** Version 18 or higher (for the frontend).
* **Python:** Version 3.10 or higher (for the backend).

---

## 🚀 Installation & Setup Guide

Follow these steps in order to get the system running.

### Part 1: Robot Setup (On the Raspberry Pi)

**1. Access the Robot:**
SSH into your robot's Raspberry Pi.

**2. Time Synchronization (Critical):**
Install `ntp` for date sync. Nav2 will fail if clocks drift. Always connect internet before beginning.


**3. Start the ROS 2 Container: Launch the Docker container with access to hardware (sound, USB):**
docker run -it --net=host --privileged \
  --device=/dev/snd:/dev/snd \
  -v /run/user/1000/pulse:/run/user/1000/pulse \
  humble-rpi-image:latest bash

**4. Setup Audio Node: Inside the robot's container, create the audio listener script.**
Install dependencies: apt-get install espeak alsa-utils

Create audio_player_node.py in your workspace: In source code.

### Part 2: Central Server Setup (On Your PC)

**1. Clone the Repository:**

git clone <your-repo-url> \
cd UniRover

**2. Time Synchronization: Configure your PC as the NTP server for the robot.**

**3. Backend Setup: You must run the backend inside a ROS 2 Humble environment (e.g., a Docker container) so it can import rclpy.**

3.1 Enter your ROS 2 Docker container
docker run -it --net=host -v $(pwd):/app ros:humble bash
cd /app/backend

3.2 Create virtual environment
python3 -m venv venv
source venv/bin/activate

3.3 Install dependencies
pip install -r requirements.txt

3.4 Initialize the Database & Admin User
python create_admin.py
(Follow the prompts to set email/password)

**4. Frontend Setup: Run this on your host machine (no Docker needed).**

cd frontend \
npm install

---

## ▶️ Running the Application

To start the system, you will need 4 separate terminals.

Terminal 1: Navigation Stack (PC - ROS 2 Container)

This starts the brain of the robot (Mapping, Localization, Path Planning).
Bash

# Inside ROS 2 Docker
ros2 launch nav2_bringup bringup_launch.py map:=/path/to/your/map.yaml

Wait ~20 seconds for "Ready for navigation" message.

Terminal 2: Rosbridge Server (PC - ROS 2 Container)

This allows the Web Frontend to talk to ROS.
Bash

# Inside ROS 2 Docker
ros2 run rosbridge_server rosbridge_websocket

Terminal 3: Backend API (PC - ROS 2 Container)

This runs the logic, scheduler, and database.
Bash

# Inside ROS 2 Docker / backend directory
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Terminal 4: Frontend UI (PC - Host Machine)

This serves the web interface.
Bash

# Inside frontend directory
npm run dev

Terminal 5: Robot Audio (Robot - Pi Container)

This listens for audio commands.
Bash

# Inside Robot Docker
python3 path/to/audio_player_node.py

📖 User Guide

1. Sending a Delivery (Sender)

    Open browser to http://localhost:5173.

    Login with your User account.

    Go to "My Deliveries".

    Fill in the "Item" and "Destination" (must match a key in room_coordinates.json).

    Click Submit. The robot will start the delivery.

2. Receiving a Delivery (Kiosk Mode)

    On a tablet at the destination (e.g., "Lab A"), open: http://localhost:5173/station/Lab A

    When the robot arrives:

        The screen will show the delivery.

        The robot will announce: "Delivery has arrived at Lab A."

    Click "Confirm Pickup" to release the robot.

3. Admin & Emergency Control

    Login with your Admin account.

    Go to "Admin Dashboard".

    Live Map: Monitor the robot's position in real-time.

    Emergency: Click the red "RETURN TO BASE" button to immediately cancel all jobs and force the robot home.

⚙️ Configuration

Room Coordinates

Map locations are defined in backend/app/room_coordinates.json. You must measure these on your map in meters relative to the map origin.
JSON

{
  "Base Station": {"x": 0.0, "y": 0.0, "theta": 0.0},
  "Lab A": {"x": 10.5, "y": 3.2, "theta": 0.0}
}

Settings (backend/app/core/config.py)

    DELIVERY_BATCH_SIZE: How many deliveries to queue before starting (Default: 3). Set to 1 for testing.

    NAVIGATION_TIMEOUT_SECONDS: Max time to reach a goal (Default: 180s).

    ROSBRIDGE_URL: WebSocket URL for the frontend map (Default: ws://localhost:9090).

🔧 Troubleshooting

Issue	Solution
Map not loading	Ensure rosbridge_server is running. Perform a Hard Refresh (Ctrl+Shift+R) in the browser.
Robot "Zigzags"	Reduce controller_frequency in navigation.yaml to 1.0 Hz. Set expected_planner_frequency to 0.0.
Navigation Fails Immediately	Check time sync. Run chronyc sources on the robot. If not synced (*), restart chrony.
"Action Server Not Ready"	Restart Nav2 first, wait 20s, then restart the Backend (uvicorn).
Audio not playing	Ensure the robot Docker container was run with --device=/dev/snd and --privileged.

📜 License

Proprietary / Internal Project. Made in Ilmenau.
