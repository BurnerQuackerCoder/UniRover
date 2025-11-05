#!/usr/bin/env python3

"""
This script creates a ROS 2 node that subscribes to the /clicked_point topic.
RViz2 publishes to this topic when you use the 'Publish Point' tool.
The script will print the coordinates of the clicked point to the console.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PointStamped

class ClickSubscriber(Node):
    """
    A ROS 2 node that subscribes to /clicked_point and logs the coordinates.
    """
    def __init__(self):
        """
        Initializes the node and creates the subscriber.
        """
        # Initialize the Node with the name 'rviz_click_subscriber'
        super().__init__('rviz_click_subscriber')
        
        # Create a subscriber to the /clicked_point topic.
        # The message type is PointStamped.
        # The callback function 'listener_callback' will be executed when a message is received.
        # The queue size is 10.
        self.subscription = self.create_subscription(
            PointStamped,
            '/clicked_point',
            self.listener_callback,
            10)
        
        self.get_logger().info('RViz Click Subscriber node started.')
        self.get_logger().info('Waiting for a click in RViz using the "Publish Point" tool...')
        self.get_logger().info('---------------------------------------------------------')

    def listener_callback(self, msg):
        """
        Callback function for the subscriber.
        This function is called every time a message is received on /clicked_point.
        """
        # Log the received message details to the console
        self.get_logger().info(f'Received clicked point in frame "{msg.header.frame_id}":')
        self.get_logger().info(f'  x: {msg.point.x:.4f}')
        self.get_logger().info(f'  y: {msg.point.y:.4f}')
        self.get_logger().info(f'  z: {msg.point.z:.4f}')
        self.get_logger().info('---------------------------------------------------------')

def main(args=None):
    """
    Main function to initialize rclpy, create the node, and spin it.
    """
    # Initialize the ROS 2 client library
    rclpy.init(args=args)
    
    # Create an instance of the ClickSubscriber node
    click_subscriber = ClickSubscriber()
    
    try:
        # Keep the node alive to receive messages
        # rclpy.spin() blocks until the node is shut down (e.g., by Ctrl+C)
        rclpy.spin(click_subscriber)
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        self.get_logger().info('KeyboardInterrupt received, shutting down...')
    finally:
        # Destroy the node explicitly
        # (optional - otherwise it will be done automatically
        #  when the garbage collector destroys the node object)
        click_subscriber.destroy_node()
        # Shutdown the ROS 2 client library
        rclpy.shutdown()

if __name__ == '__main__':
    # This is the entry point of the script
    main()
