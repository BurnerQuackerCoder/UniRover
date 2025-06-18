import React, { useEffect, useRef } from 'react';
import ROSLIB from 'roslib';
// We do not import ROS2D here. It is loaded globally from index.html

const LiveMap: React.FC = () => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const rosRef = useRef<ROSLIB.Ros | null>(null);

  useEffect(() => {
    // This effect runs only once to set up the connection and cleanup
    if (!mapContainerRef.current) return;
    const ROS2D = window.ROS2D;
    if (!ROS2D) {
      console.error("ros2d.js script not loaded correctly. ROS2D is not available on the window object.");
      return;
    }

    const rosbridgeUrl = `ws://${window.location.hostname}:8000/ws/ros`;
    if (rosRef.current) return;

    const ros = new ROSLIB.Ros({ url: rosbridgeUrl });
    rosRef.current = ros;

    const initializeMap = (ros_connection: ROSLIB.Ros) => {
      if (!mapContainerRef.current) return;
      mapContainerRef.current.innerHTML = '';
      
      const viewer = new ROS2D.Viewer({
        divID: mapContainerRef.current.id,
        width: 410,
        height: 710,
      });

      const gridClient = new ROS2D.OccupancyGridClient({
        ros: ros_connection,
        rootObject: viewer.scene,
        continuous: true,
      });

      gridClient.on('change', () => {
        // --- THIS IS THE FIX ---
        // We must also invert the y-coordinate for the shift operation
        // to match the canvas's coordinate system.
        viewer.scaleToDimensions(gridClient.currentGrid.width, gridClient.currentGrid.height);
        viewer.shift(gridClient.currentGrid.pose.position.x, -gridClient.currentGrid.pose.position.y);
        console.log("Map view has been scaled and centered.");
      });

      const robotMarker = new window.ROS2D.ArrowShape({
        size: 0.5,
        strokeSize: 0.05,
        fillColor: '#ff0000',
        pulse: true,
      });
      viewer.scene.addChild(robotMarker);

      const poseClient = new ROSLIB.Topic({
        ros: ros_connection,
        name: '/amcl_pose',
        messageType: 'geometry_msgs/PoseWithCovarianceStamped',
      });

      poseClient.subscribe((message: any) => {
        const pose = message.pose.pose;
        robotMarker.x = pose.position.x;
        robotMarker.y = -pose.position.y;
        const q = pose.orientation;
        const angle = Math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z));
        robotMarker.rotation = -angle * (180 / Math.PI);
      });
    };

    ros.on('connection', () => {
      console.log('LiveMap: Successfully connected to ROS proxy.');
      initializeMap(ros);
    });
    
    ros.on('error', (error) => console.error('LiveMap: Error connecting to ROS proxy:', error));
    ros.on('close', () => console.log('LiveMap: Connection to ROS proxy closed.'));

    return () => {
      if (rosRef.current && rosRef.current.isConnected) {
        rosRef.current.close();
        rosRef.current = null;
      }
    };
  }, []);

  return (
    <div className="bg-gray-200 p-4 rounded-lg shadow-inner flex justify-center items-center">
      <div>
        <h3 className="text-xl font-bold mb-2 text-center">Live Robot Position</h3>
        <div id="live-map-container" ref={mapContainerRef} />
      </div>
    </div>
  );
};

export default LiveMap;