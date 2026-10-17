import tensorflow as tf
import numpy as np
import cv2
from typing import List, Optional
import os
import urllib.request

class MoveNet:
    """MoveNet pose detection model wrapper"""
    
    # Model URLs
    MODEL_URLS = {
        'thunder': 'https://storage.googleapis.com/tfhub-modules/tensorflow/movenet/thunder/4.tar.gz',
        'lightning': 'https://storage.googleapis.com/tfhub-modules/tensorflow/movenet/lightning/4.tar.gz'
    }
    
    def __init__(self, config):
        self.config = config
        self.model_type = 'thunder'  # or 'lightning'
        
        # Set input size based on model
        self.input_size = 256 if self.model_type == 'lightning' else 256  # Actually thunder uses 256 as well
        
        # Load model
        model_path = os.path.join(config.movenet_weights_path, f'movenet_{self.model_type}.tflite')
        
        if not os.path.exists(model_path):
            self.download_weights(config.movenet_weights_path)
        
        self.interpreter = tf.lite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        
        # Keypoint names in COCO order
        self.keypoint_names = [
            'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
            'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
            'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
            'left_knee', 'right_knee', 'left_ankle', 'right_ankle'
        ]
    
    @staticmethod
    def download_weights(path: str):
        """Download pretrained weights"""
        os.makedirs(path, exist_ok=True)
        
        # For simplicity, we'll assume weights are provided
        # In production, you'd download from TF Hub
        print(f"⚠️ Please download MoveNet weights to {path}")
        print("Download from: https://tfhub.dev/tensorflow/movenet/thunder/4")
    
    def predict(self, image: np.ndarray) -> np.ndarray:
        """
        Predict 2D pose keypoints
        
        Returns:
            Array of shape (17, 3) with [y, x, confidence] for each keypoint
        """
        # Preprocess
        input_image = self._preprocess(image)
        
        # Run inference
        self.interpreter.set_tensor(self.input_details[0]['index'], input_image)
        self.interpreter.invoke()
        
        # Get keypoints
        keypoints = self.interpreter.get_tensor(self.output_details[0]['index'])
        
        # Reshape and convert to [x, y, confidence]
        keypoints = keypoints.reshape((1, 1, 17, 3))[0, 0]
        
        # MoveNet returns [y, x, confidence], convert to [x, y, confidence]
        keypoints = keypoints[:, [1, 0, 2]]
        
        return keypoints
    
    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for MoveNet"""
        # Resize
        h, w = image.shape[:2]
        scale = self.input_size / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        
        resized = cv2.resize(image, (new_w, new_h))
        
        # Pad to square
        pad_h = self.input_size - new_h
        pad_w = self.input_size - new_w
        
        pad_top = pad_h // 2
        pad_bottom = pad_h - pad_top
        pad_left = pad_w // 2
        pad_right = pad_w - pad_left
        
        padded = cv2.copyMakeBorder(
            resized,
            pad_top, pad_bottom, pad_left, pad_right,
            cv2.BORDER_CONSTANT,
            value=[0, 0, 0]
        )
        
        # Normalize to [-1, 1]
        padded = padded.astype(np.float32) / 127.5 - 1
        
        # Add batch dimension
        return np.expand_dims(padded, axis=0)
    
    def draw_keypoints(self, image: np.ndarray, keypoints: np.ndarray) -> np.ndarray:
        """Draw keypoints on image for visualization"""
        result = image.copy()
        h, w = image.shape[:2]
        
        for i, (x, y, conf) in enumerate(keypoints):
            if conf > 0.3:  # Only draw confident keypoints
                x = int(x * w)
                y = int(y * h)
                cv2.circle(result, (x, y), 5, (0, 255, 0), -1)
                cv2.putText(
                    result,
                    str(i),
                    (x + 5, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 0, 0),
                    1
                )
        
        return result
