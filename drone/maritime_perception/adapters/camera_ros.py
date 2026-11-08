"""Optional ROS publication for image capture, independent of flight control."""
import cv2
import numpy as np
import time

from ..replay import line
from .image_grabber import CaptureRecorder, CaptureSession


def resized_camera_info(info, size):
    result = dict(info, width=size[0], height=size[1])
    if info["k"][0] == 0:
        return result
    sx, sy = size[0]/info["width"], size[1]/info["height"]
    matrix = np.array([[sx, 0., (sx-1)/2], [0., sy, (sy-1)/2], [0., 0., 1.]])
    k = matrix @ np.asarray(info["k"]).reshape(3, 3)
    result.update(k=k.reshape(-1).tolist(), p=np.column_stack((k, np.zeros(3))).reshape(-1).tolist())
    return result


def run_ros(settings, ros_args):
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
        from sensor_msgs.msg import Image, CameraInfo
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit("Camera ROS publication unavailable: source a compatible ROS 2 environment") from exc

    class ImageGrabber(Node):
        def __init__(self):
            super().__init__("image_grabber")
            self.session = self.recorder = None
            self.failure, self.done, self.processed = None, False, 0
            try:
                if settings.output:
                    from pathlib import Path
                    if Path(settings.output).exists():
                        raise FileExistsError(settings.output)
                self.session = CaptureSession(settings)
                if settings.output:
                    self.recorder = CaptureRecorder(self.session)
                qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
                topic = "/camera/image_rect" if settings.rectify else "/camera/image_raw"
                self.image_pub = self.create_publisher(Image, topic, qos)
                self.info_pub = self.create_publisher(CameraInfo, "/camera/camera_info", qos)
                self.metadata_pub = self.create_publisher(String, "/camera/frame_metadata", qos)
                self.preview_pub = self.preview_info_pub = None
                if settings.preview_width:
                    self.preview_pub = self.create_publisher(Image, "/camera/preview/image", qos)
                    self.preview_info_pub = self.create_publisher(CameraInfo, "/camera/preview/camera_info", qos)
                self.started_ns = time.monotonic_ns()
                self.timer = self.create_timer(1/settings.publish_hz, self.tick)
                self.get_logger().info(f"Publishing {topic}; header is host arrival time, not verified exposure time. Use /camera/frame_metadata for source PTS.")
            except Exception:
                self.close()
                self.destroy_node()
                raise

        def image_message(self, image, header):
            msg = Image()
            msg.header = header
            msg.height, msg.width = image.shape[:2]
            msg.encoding, msg.is_bigendian, msg.step = "bgr8", 0, msg.width*3
            msg.data = image.tobytes()
            return msg

        def info_message(self, info, stamp_ns):
            msg = CameraInfo()
            msg.header.frame_id = settings.frame_id
            msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp_ns, 10**9)
            for key, value in info.items():
                setattr(msg, key, value)
            return msg

        def tick(self):
            try:
                if settings.duration_s and time.monotonic_ns()-self.started_ns >= round(settings.duration_s*1e9):
                    self.done = True
                    self.timer.cancel()
                    return
                packet = self.session.read()
                stamp = packet.metadata["arrival_unix_ns"]
                packet.metadata.update(ros_header_stamp_ns=stamp, ros_header_stamp_semantics="host_arrival_unverified")
                info = self.info_message(packet.camera_info, stamp)
                self.image_pub.publish(self.image_message(packet.image, info.header))
                self.info_pub.publish(info)
                self.metadata_pub.publish(String(data=line(packet.metadata).strip()))
                if self.preview_pub is not None:
                    size = [settings.preview_width, settings.preview_height]
                    preview = cv2.resize(packet.image, tuple(size), interpolation=cv2.INTER_LINEAR)
                    self.preview_pub.publish(self.image_message(preview, info.header))
                    self.preview_info_pub.publish(self.info_message(resized_camera_info(packet.camera_info, size), stamp))
                if self.recorder is not None:
                    self.recorder.handle(packet)
                self.processed += 1
                if settings.max_frames and self.processed >= settings.max_frames:
                    self.done = True
                    self.timer.cancel()
            except Exception as exc:
                self.failure = exc
                self.timer.cancel()
                self.get_logger().error(f"Camera stopped: {exc}")

        def close(self):
            try:
                if self.recorder is not None:
                    self.recorder.close()
            finally:
                if self.session is not None:
                    self.session.close()

    rclpy.init(args=ros_args)
    node = None
    try:
        node = ImageGrabber()
        while rclpy.ok() and not node.done and node.failure is None:
            rclpy.spin_once(node)
        if node.failure is not None:
            raise node.failure
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if node is not None:
                try:
                    node.close()
                finally:
                    node.destroy_node()
        finally:
            if rclpy.ok():
                rclpy.shutdown()
