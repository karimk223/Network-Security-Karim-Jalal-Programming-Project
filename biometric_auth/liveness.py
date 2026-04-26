"""
Liveness / anti-spoofing detection using MediaPipe FaceMesh.

MediaPipe provides 468 face landmarks with a pure-Python prebuilt wheel
(no compilation required). We use a subset:

  • 6 landmarks per eye  → Eye Aspect Ratio for blink detection
  • 6 anchor landmarks   → solvePnP for 3D head pose estimation

Two independent challenges are combined per login:

1) BLINK DETECTION (Soukupová & Čech, 2016)
   EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
   A natural blink drops EAR below ~0.21 for a few frames.

2) RANDOMIZED HEAD POSE CHALLENGE
   Server picks {left, right, center} at challenge-issue time.
   Yaw angle is recovered from 2D landmarks via solvePnP.

Together these defeat:
   - Photo-print attacks (no blink, no head motion)
   - Replay-video attacks (wrong randomized direction)
   - Many deepfakes that don't handle pose changes cleanly
"""
import io
import base64
import numpy as np
import cv2
from PIL import Image
from scipy.spatial import distance as dist

import mediapipe as mp

from config import Config


# -------------------------------------------------------------------------
# MediaPipe FaceMesh singleton
# -------------------------------------------------------------------------
_MESH = None

def _get_mesh():
    global _MESH
    if _MESH is None:
        _MESH = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )
    return _MESH


# -------------------------------------------------------------------------
# Landmark indices in the 468-point MediaPipe FaceMesh model.
# -------------------------------------------------------------------------
# 6 points per eye, ordered like dlib's 68-landmark EAR convention
LEFT_EYE_IDX  = [33,  160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]

# Anchors for 3D head-pose (solvePnP)
POSE_IDX = {
    'nose_tip':        1,
    'chin':            152,
    'left_eye_outer':  33,
    'right_eye_outer': 263,
    'left_mouth':      61,
    'right_mouth':     291,
}

# Matching 3D model points (mm)
MODEL_POINTS_3D = np.array([
    (0.0,    0.0,    0.0),      # nose tip
    (0.0,   -63.6,  -12.5),     # chin
    (-43.3,  32.7,  -26.0),     # left eye, outer corner
    (43.3,   32.7,  -26.0),     # right eye, outer corner
    (-28.9, -28.9,  -24.1),     # left mouth corner
    (28.9,  -28.9,  -24.1),     # right mouth corner
], dtype=np.float64)


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
def _decode_image(image_data):
    if isinstance(image_data, str):
        if image_data.startswith('data:'):
            image_data = image_data.split(',', 1)[1]
        image_bytes = base64.b64decode(image_data)
    elif isinstance(image_data, (bytes, bytearray)):
        image_bytes = image_data
    else:
        raise ValueError('Unsupported image_data type')
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    return np.array(img)


def _landmarks_to_px(landmarks, w, h):
    """Turn normalized MediaPipe landmarks into pixel-space (x,y) tuples."""
    return [(lm.x * w, lm.y * h) for lm in landmarks]


def extract_face_landmarks(image_data):
    """
    Run FaceMesh on an image. Returns (pixel_landmarks[468], (h,w,3)) or (None, rgb).
    """
    rgb = _decode_image(image_data)
    h, w = rgb.shape[:2]
    result = _get_mesh().process(rgb)
    if not result.multi_face_landmarks:
        return None, rgb
    lm = result.multi_face_landmarks[0].landmark
    return _landmarks_to_px(lm, w, h), rgb


# -------------------------------------------------------------------------
# Eye aspect ratio
# -------------------------------------------------------------------------
def _ear_for_eye(pts):
    A = dist.euclidean(pts[1], pts[5])
    B = dist.euclidean(pts[2], pts[4])
    C = dist.euclidean(pts[0], pts[3])
    return (A + B) / (2.0 * C) if C else 0.0


def compute_ear(landmarks_px):
    left  = [landmarks_px[i] for i in LEFT_EYE_IDX]
    right = [landmarks_px[i] for i in RIGHT_EYE_IDX]
    return (_ear_for_eye(left) + _ear_for_eye(right)) / 2.0


# -------------------------------------------------------------------------
# Head pose via solvePnP
# -------------------------------------------------------------------------
def estimate_head_pose(landmarks_px, image_shape):
    """
    Returns (yaw_deg, pitch_deg) or (None, None).
    Positive yaw = user's right.
    """
    try:
        image_points = np.array([
            landmarks_px[POSE_IDX['nose_tip']],
            landmarks_px[POSE_IDX['chin']],
            landmarks_px[POSE_IDX['left_eye_outer']],
            landmarks_px[POSE_IDX['right_eye_outer']],
            landmarks_px[POSE_IDX['left_mouth']],
            landmarks_px[POSE_IDX['right_mouth']],
        ], dtype=np.float64)
    except (IndexError, KeyError):
        return None, None

    h, w = image_shape[:2]
    focal = w
    camera_matrix = np.array([
        [focal, 0,     w / 2],
        [0,     focal, h / 2],
        [0,     0,     1]
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))

    ok, rvec, _tvec = cv2.solvePnP(
        MODEL_POINTS_3D, image_points, camera_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not ok:
        return None, None

    rmat, _ = cv2.Rodrigues(rvec)
    sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
    if sy < 1e-6:
        pitch = np.degrees(np.arctan2(-rmat[1, 2], rmat[1, 1]))
        yaw   = np.degrees(np.arctan2(-rmat[2, 0], sy))
    else:
        pitch = np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2]))
        yaw   = np.degrees(np.arctan2(-rmat[2, 0], sy))
    return float(yaw), float(pitch)


# -------------------------------------------------------------------------
# Stateful liveness session
# -------------------------------------------------------------------------
class LivenessSession:
    """
    Tracks EAR + yaw across multiple frames for a single login attempt.
    """
    def __init__(self, challenge_direction='center'):
        self.ear_history = []
        self.blink_count = 0
        self.frames_below_threshold = 0
        self.challenge_direction = challenge_direction
        self.challenge_met = True
        self.frames_processed = 0

    def process_frame(self, ear, yaw):
        self.frames_processed += 1
        if ear is not None:
            self.ear_history.append(ear)
            if ear < Config.EAR_THRESHOLD:
                self.frames_below_threshold += 1
            else:
                if self.frames_below_threshold >= Config.EAR_CONSECUTIVE_FRAMES:
                    self.blink_count += 1
                self.frames_below_threshold = 0

        if yaw is not None and not self.challenge_met:
            if self.challenge_direction == 'left' and yaw < -Config.HEAD_POSE_YAW_THRESHOLD:
                self.challenge_met = True
            elif self.challenge_direction == 'right' and yaw > Config.HEAD_POSE_YAW_THRESHOLD:
                self.challenge_met = True
            elif self.challenge_direction == 'center' and abs(yaw) < Config.HEAD_POSE_YAW_THRESHOLD:
                self.challenge_met = True

    def is_complete(self):
        return (self.blink_count >= Config.BLINKS_REQUIRED
                and self.challenge_met)

    def status(self):
        return {
            'blinks': self.blink_count,
            'blinks_required': Config.BLINKS_REQUIRED,
            'challenge_direction': self.challenge_direction,
            'challenge_met': self.challenge_met,
            'frames_processed': self.frames_processed,
            'complete': self.is_complete(),
        }


# -------------------------------------------------------------------------
# Legacy API names used by app.py
# -------------------------------------------------------------------------
def compute_ear_from_landmarks(landmarks_px):
    """app.py calls this name; just delegate to compute_ear."""
    return compute_ear(landmarks_px)
