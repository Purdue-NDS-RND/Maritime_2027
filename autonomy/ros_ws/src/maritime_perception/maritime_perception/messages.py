"""Translate pixel rectangles to the standard ROS detection interface."""

from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose


def detection_array(header, boxes):
    result = Detection2DArray(header=header)
    for box in boxes:
        detection = Detection2D(header=header)
        detection.bbox.center.position.x = box.center_x
        detection.bbox.center.position.y = box.center_y
        detection.bbox.size_x = box.width
        detection.bbox.size_y = box.height
        hypothesis = ObjectHypothesisWithPose()
        hypothesis.hypothesis.class_id = box.category
        # Binary dictionary recognition, not a calibrated confidence estimate.
        # The message's default 3D pose/covariance fields are unused.
        hypothesis.hypothesis.score = 1.0
        detection.results.append(hypothesis)
        result.detections.append(detection)
    return result
