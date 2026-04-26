"""
Configuration for Biometric Authentication System
CSC 437 - Network Security Project
"""
import os

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-in-production-csc437-biometric')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 1800  # 30 min

    # Face recognition settings (ArcFace / InsightFace -> cosine distance)
    # Cosine distance is in [0, 2]; same person typically d < 0.40.
    # Lower tolerance = stricter matching.
    FACE_MATCH_TOLERANCE = 0.40
    # Max pairwise distance allowed between the 3 enrollment samples.
    # For ArcFace cosine distance, same-person pairs are usually < ~0.30.
    ENROLL_MAX_PAIRWISE = 0.45

    # Liveness detection thresholds
    EAR_THRESHOLD = 0.21          # Slightly more lenient for varying lighting
    EAR_CONSECUTIVE_FRAMES = 1    # Single-frame dip is enough (we run at ~4fps)
    BLINKS_REQUIRED = 3           # Number of blinks user must perform during liveness
    LIVENESS_TIMEOUT_SECONDS = 60 # More realistic timeout

    # Head-pose challenge: directions user might be asked to turn
    HEAD_POSE_CHALLENGES = ['blink-only']
    HEAD_POSE_YAW_THRESHOLD = 999   # disabled

    # Security / lockout
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    USERS_DB = os.path.join(DATA_DIR, 'users.json')
    EVENTS_LOG = os.path.join(LOGS_DIR, 'events.json')
    KEY_FILE = os.path.join(DATA_DIR, '.fernet.key')

    # 2FA: require password in addition to face?
    REQUIRE_PASSWORD_FACTOR = True
