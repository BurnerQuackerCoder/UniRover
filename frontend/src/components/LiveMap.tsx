import React, { useEffect, useRef, useState } from 'react';
import ROSLIB from 'roslib'; // We import roslib as a module

// Define interfaces for the ROS messages we'll receive
interface MapMetaData {
  resolution: number;
  width: number;
  height: number;
  origin: {
    position: { x: number; y: number; };
  };
}
interface OccupancyGridMessage {
  header: { frame_id: string; };
  info: MapMetaData;
  data: number[]; // Array of -1, 0, or 100
}
interface PoseMessage {
  position: { x: number; y: number; };
  orientation: { z: number; w: number; };
}

// --- Helper Functions for Drawing ---

/**
 * Draws the map data onto the canvas.
 */
const drawMap = (
  ctx: CanvasRenderingContext2D,
  map: OccupancyGridMessage
) => {
  // --- FIX was here: 'data' is on 'map', 'info' has width/height ---
  const { info, data } = map;
  const { width, height } = info;
  // --- END FIX ---
  const imageData = ctx.createImageData(width, height);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const mapY = (height - 1) - y;
      const mapIndex = (mapY * width) + x;
      const dataIndex = (y * width + x) * 4;

      const occupancyValue = data[mapIndex];
      let r = 205, g = 205, b = 205; // Default: Light gray for unknown (-1)

      if (occupancyValue === 0) { // Free space
        r = 254; g = 254; b = 254; // White
      } else if (occupancyValue === 100) { // Occupied (wall)
        r = 0; g = 0; b = 0; // Black
      }

      imageData.data[dataIndex] = r;
      imageData.data[dataIndex + 1] = g;
      imageData.data[dataIndex + 2] = b;
      imageData.data[dataIndex + 3] = 255; // Alpha
    }
  }
  ctx.putImageData(imageData, 0, 0);
  console.log('Map drawn to canvas');
};

/**
 * Draws the robot's pose on the canvas.
 */
const drawRobot = (
  ctx: CanvasRenderingContext2D,
  mapInfo: MapMetaData,
  pose: PoseMessage
) => {
  const { resolution, origin, height } = mapInfo;

  // 1. Convert ROS coordinates (meters) to map grid coordinates (pixels)
  const mapX = (pose.position.x - origin.position.x) / resolution;
  const mapY = (pose.position.y - origin.position.y) / resolution;

  // 2. Convert map grid coordinates (bottom-left) to canvas (top-left)
  const canvasX = mapX;
  const canvasY = height - mapY;

  // 3. Get robot orientation (yaw) from quaternion
  const q = pose.orientation;
  const yaw = Math.atan2(2 * (q.w * q.z + 0 * 0), 1 - 2 * (0 * 0 + q.z * q.z));
  const canvasAngle = -yaw;

  ctx.save();
  ctx.translate(canvasX, canvasY);
  ctx.rotate(canvasAngle);

  ctx.beginPath();
  ctx.arc(0, 0, 5, 0, 2 * Math.PI, false); // 5-pixel radius circle
  ctx.fillStyle = 'red';
  ctx.fill();

  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(8, 0); // 8-pixel direction line
  ctx.strokeStyle = 'red';
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.restore();
};

// --- The React Component ---

const LiveMap: React.FC = () => {
  const [ros, setRos] = useState<ROSLIB.Ros | null>(null);
  const [mapData, setMapData] = useState<OccupancyGridMessage | null>(null);
  const [robotPose, setRobotPose] = useState<PoseMessage | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Effect 1: Establish ROS Connection (runs once)
  useEffect(() => {
    const rosConnection = new ROSLIB.Ros({
      url: `ws://localhost:8000/ws/ros`,
    });

    rosConnection.on('connection', () => {
      console.log('LiveMap (ROS 2): Successfully connected to ROS proxy.');
      setRos(rosConnection);
    });

    rosConnection.on('error', (error) => {
      console.error('LiveMap (ROS 2): Error connecting to ROS proxy:', error);
    });

    rosConnection.on('close', () => {
      console.log('LiveMap (ROS 2): Connection to ROS proxy closed.');
      setRos(null);
    });

    return () => {
      rosConnection.close();
    };
  }, []);

  // Effect 2: Subscribe to Topics (runs when 'ros' connection is established)
  useEffect(() => {
    if (!ros) return;

    // --- Subscribe to Map Topic ---
    const mapClient = new ROSLIB.Topic({
      ros: ros,
      name: '/map',
      messageType: 'nav_msgs/msg/OccupancyGrid',
      //compression: 'png',
      qos: {
        reliability: 'reliable',
        durability: 'transient_local',
      },
    } as any); // <-- FIX: Add 'as any' to bypass the old type definitions

    const mapCallback = (message: any) => {
      console.log('Received map data');
      setMapData(message as OccupancyGridMessage);
      mapClient.unsubscribe();
      console.log('Unsubscribed from map topic');
    };
    mapClient.subscribe(mapCallback);

    // --- Subscribe to Pose Topic ---
    const poseClient = new ROSLIB.Topic({
      ros: ros,
      name: '/amcl_pose',
      messageType: 'geometry_msgs/msg/PoseWithCovarianceStamped',
    });

    const poseCallback = (message: any) => {
      setRobotPose(message.pose.pose as PoseMessage);
    };
    poseClient.subscribe(poseCallback);

    return () => {
      mapClient.unsubscribe();
      poseClient.unsubscribe();
    };
  }, [ros]);

  // Effect 3: Drawing Effect (runs when map or pose changes)
  useEffect(() => {
    if (!canvasRef.current || !mapData) {
      return;
    }

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = mapData.info.width;
    canvas.height = mapData.info.height;

    // 1. Draw the map
    drawMap(ctx, mapData);

    // 2. Draw the robot
    if (robotPose) {
      drawRobot(ctx, mapData.info, robotPose);
    }
  }, [mapData, robotPose]);

  // --- Render ---
  return (
    <div className="bg-gray-200 p-4 rounded-lg shadow-inner flex justify-center items-center">
      <div>
        <h3 className="text-xl font-bold mb-2 text-center">Live Robot Position (ROS 2)</h3>
        <canvas
          ref={canvasRef}
          id="live-map-canvas-ros2"
          style={{ width: '100%', maxWidth: '410px', height: 'auto', imageRendering: 'pixelated' }}
        />
        {!mapData && <p>Waiting for map data from /map...</p>}
      </div>
    </div>
  );
};

export default LiveMap;