"""
Secure storage for face embeddings.
Embeddings are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).
Passwords are hashed with PBKDF2-HMAC-SHA256.
"""
import os
import json
import base64
import hashlib
import hmac
import secrets
import numpy as np
from cryptography.fernet import Fernet
from config import Config


class SecureStorage:
    def __init__(self):
        self.key = self._load_or_create_key()
        self.fernet = Fernet(self.key)
        self._ensure_files()

    def _load_or_create_key(self):
        """Load Fernet key from disk or generate a fresh one."""
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        if os.path.exists(Config.KEY_FILE):
            with open(Config.KEY_FILE, 'rb') as f:
                return f.read()
        key = Fernet.generate_key()
        # Write with restrictive permissions
        with open(Config.KEY_FILE, 'wb') as f:
            f.write(key)
        try:
            os.chmod(Config.KEY_FILE, 0o600)
        except Exception:
            pass
        return key

    def _ensure_files(self):
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        os.makedirs(Config.LOGS_DIR, exist_ok=True)
        if not os.path.exists(Config.USERS_DB):
            with open(Config.USERS_DB, 'w') as f:
                json.dump({}, f)
        if not os.path.exists(Config.EVENTS_LOG):
            with open(Config.EVENTS_LOG, 'w') as f:
                json.dump([], f)

    # ---------- Face embedding encryption ----------
    def encrypt_embedding(self, embedding: np.ndarray) -> str:
        """Encrypt a face embedding (512-d ArcFace). Returns base64 string."""
        raw = embedding.astype(np.float64).tobytes()
        token = self.fernet.encrypt(raw)
        return token.decode('utf-8')

    def decrypt_embedding(self, token: str) -> np.ndarray:
        """Decrypt to float64 numpy array (512-d)."""
        raw = self.fernet.decrypt(token.encode('utf-8'))
        return np.frombuffer(raw, dtype=np.float64)

    # ---------- Password hashing (PBKDF2) ----------
    @staticmethod
    def hash_password(password: str, salt: bytes = None) -> tuple:
        if salt is None:
            salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200_000)
        return base64.b64encode(salt).decode(), base64.b64encode(dk).decode()

    @staticmethod
    def verify_password(password: str, salt_b64: str, hash_b64: str) -> bool:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200_000)
        return hmac.compare_digest(dk, expected)

    # ---------- User DB ----------
    def load_users(self) -> dict:
        with open(Config.USERS_DB, 'r') as f:
            return json.load(f)

    def save_users(self, users: dict):
        with open(Config.USERS_DB, 'w') as f:
            json.dump(users, f, indent=2)

    def get_user(self, username: str):
        return self.load_users().get(username)

    def add_user(self, username: str, password: str, embeddings: list):
        users = self.load_users()
        if username in users:
            raise ValueError('User already exists')
        salt, pw_hash = self.hash_password(password)
        enc_embeddings = [self.encrypt_embedding(e) for e in embeddings]
        users[username] = {
            'password_salt': salt,
            'password_hash': pw_hash,
            'embeddings': enc_embeddings,
            'failed_attempts': 0,
            'locked_until': None,
            'created_at': _now_iso(),
        }
        self.save_users(users)

    def update_user(self, username: str, user_data: dict):
        users = self.load_users()
        users[username] = user_data
        self.save_users(users)

    def delete_user(self, username: str):
        users = self.load_users()
        if username in users:
            del users[username]
            self.save_users(users)

    # ---------- Event logging ----------
    def log_event(self, event: dict):
        event.setdefault('timestamp', _now_iso())
        with open(Config.EVENTS_LOG, 'r') as f:
            events = json.load(f)
        events.append(event)
        # Keep last 1000 events
        events = events[-1000:]
        with open(Config.EVENTS_LOG, 'w') as f:
            json.dump(events, f, indent=2)

    def get_events(self, limit: int = 100):
        with open(Config.EVENTS_LOG, 'r') as f:
            events = json.load(f)
        return events[-limit:][::-1]  # most-recent first


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
