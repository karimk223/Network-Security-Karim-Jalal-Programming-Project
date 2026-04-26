"""
Flask application: Biometric Authentication System
CSC 437 - Network Security Project

Routes:
  GET  /              - Landing page
  GET  /register      - Registration UI
  POST /api/register  - Create account (username, password, 3 face samples)
  GET  /login         - Login UI
  POST /api/login/password - Step 1: verify password, issue liveness challenge
  POST /api/login/frame    - Step 2: stream frames for liveness check
  POST /api/login/verify   - Step 3: final face match
  GET  /dashboard     - Authenticated user landing
  GET  /admin         - Security dashboard (events log)
  POST /api/logout
"""
import sys

if sys.version_info < (3, 10):
    print("\nERROR: Python 3.10 or higher is required.")
    print("Please follow README.md under 'Running the Project'.\n")
    sys.exit(1)

try:
    import cv2
    import mediapipe
except ImportError:
    print("\nERROR: Required dependencies are not installed.")
    print("Run these commands:")
    print("  cd biometric_auth")
    print("  python3 -m venv venv")
    print("  source venv/bin/activate")
    print("  pip install -r requirements.txt")
    print("  python app.py\n")
    sys.exit(1)

import os
import random
import secrets
from datetime import datetime, timedelta, timezone
from flask import (
    Flask, request, jsonify, render_template, session, redirect, url_for
)

from config import Config
from storage import SecureStorage
import face_engine
import liveness

# Warm up models at startup so the first login doesn't stall
print('[startup] warming up MediaPipe...')
import numpy as np
_warmup_img = np.zeros((480, 640, 3), dtype=np.uint8)
try:
    liveness._get_mesh().process(_warmup_img)
except Exception as e:
    print('  mesh warmup note:', e)
print('[startup] warming up ArcFace...')
try:
    face_engine._get_arcface()
except Exception as e:
    print('  arcface warmup note:', e)
print('[startup] ready.')


app = Flask(__name__)
app.config.from_object(Config)

storage = SecureStorage()

# In-memory liveness sessions keyed by challenge token
LIVENESS_SESSIONS = {}


# =========================================================================
#                               HELPERS
# =========================================================================
def _now():
    return datetime.now(timezone.utc)


def _client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr) or 'unknown'


def _is_locked(user):
    locked_until = user.get('locked_until')
    if not locked_until:
        return False
    try:
        lu = datetime.fromisoformat(locked_until)
    except Exception:
        return False
    return _now() < lu


def _record_failure(username):
    user = storage.get_user(username)
    if not user:
        return
    user['failed_attempts'] = user.get('failed_attempts', 0) + 1
    if user['failed_attempts'] >= Config.MAX_FAILED_ATTEMPTS:
        user['locked_until'] = (_now() + timedelta(minutes=Config.LOCKOUT_MINUTES)).isoformat()
    storage.update_user(username, user)


def _record_success(username):
    user = storage.get_user(username)
    if not user:
        return
    user['failed_attempts'] = 0
    user['locked_until'] = None
    storage.update_user(username, user)


# =========================================================================
#                               PAGES
# =========================================================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register')
def register_page():
    return render_template('register.html')


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if not session.get('username'):
        return redirect(url_for('login_page'))
    return render_template('dashboard.html', username=session['username'])


@app.route('/admin')
def admin_page():
    if not session.get('username'):
        return redirect(url_for('login_page'))
    return render_template('admin.html', username=session['username'])


# =========================================================================
#                               REGISTRATION
# =========================================================================
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    samples = data.get('samples') or []

    if not username or not password:
        return jsonify(ok=False, error='Username and password required'), 400
    if len(password) < 8:
        return jsonify(ok=False, error='Password must be at least 8 characters'), 400
    if len(samples) < 3:
        return jsonify(ok=False, error='At least 3 face samples required'), 400
    if storage.get_user(username):
        return jsonify(ok=False, error='Username already taken'), 409

    # Extract embeddings from each sample
    embeddings = []
    for i, sample in enumerate(samples):
        emb, _loc, status = face_engine.extract_embedding(sample)
        if status != 'ok':
            return jsonify(ok=False, error=f'Sample {i+1}: {status}'), 400
        embeddings.append(emb)

    # Sanity check: samples should be of the *same* person (cosine distance small)
    pairwise = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            pairwise.append(face_engine.cosine_distance(embeddings[i], embeddings[j]))
    if pairwise and max(pairwise) > Config.ENROLL_MAX_PAIRWISE:
        return jsonify(
            ok=False,
            error='Samples appear to be of different people. Please retake.'
        ), 400

    storage.add_user(username, password, embeddings)
    storage.log_event({
        'type': 'register',
        'username': username,
        'ip': _client_ip(),
        'success': True,
    })
    return jsonify(ok=True, message='Account created. You may now log in.')


# =========================================================================
#                               LOGIN (3-step)
# =========================================================================
@app.route('/api/login/password', methods=['POST'])
def api_login_password():
    """Step 1: verify password, issue a liveness challenge token."""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    user = storage.get_user(username)
    if not user:
        # Constant-ish time: still run a dummy verify to avoid leaking existence
        SecureStorage.verify_password(password, 'YWFhYQ==', 'YmJiYg==')
        storage.log_event({
            'type': 'login_password', 'username': username,
            'ip': _client_ip(), 'success': False, 'reason': 'unknown_user',
        })
        return jsonify(ok=False, error='Invalid credentials'), 401

    if _is_locked(user):
        storage.log_event({
            'type': 'login_password', 'username': username,
            'ip': _client_ip(), 'success': False, 'reason': 'locked',
        })
        return jsonify(ok=False, error='Account locked. Try again later.'), 423

    if Config.REQUIRE_PASSWORD_FACTOR:
        if not SecureStorage.verify_password(password, user['password_salt'], user['password_hash']):
            _record_failure(username)
            storage.log_event({
                'type': 'login_password', 'username': username,
                'ip': _client_ip(), 'success': False, 'reason': 'bad_password',
            })
            return jsonify(ok=False, error='Invalid credentials'), 401

    # Issue liveness challenge
    token = secrets.token_urlsafe(24)
    direction = random.choice(Config.HEAD_POSE_CHALLENGES)
    LIVENESS_SESSIONS[token] = {
        'username': username,
        'session': liveness.LivenessSession(challenge_direction=direction),
        'created_at': _now(),
        'ip': _client_ip(),
    }
    storage.log_event({
        'type': 'login_password', 'username': username,
        'ip': _client_ip(), 'success': True,
    })
    return jsonify(
        ok=True,
        challenge_token=token,
        challenge_direction=direction,
        blinks_required=Config.BLINKS_REQUIRED,
        timeout_seconds=Config.LIVENESS_TIMEOUT_SECONDS,
    )


@app.route('/api/login/frame', methods=['POST'])
def api_login_frame():
    """Step 2: accept individual frames for liveness scoring."""
    data = request.get_json(silent=True) or {}
    token = data.get('challenge_token')
    frame = data.get('frame')

    ctx = LIVENESS_SESSIONS.get(token)
    if not ctx:
        return jsonify(ok=False, error='Invalid or expired challenge'), 400

    # Timeout check
    if (_now() - ctx['created_at']).total_seconds() > Config.LIVENESS_TIMEOUT_SECONDS:
        LIVENESS_SESSIONS.pop(token, None)
        return jsonify(ok=False, error='Liveness challenge timed out'), 408

    landmarks, rgb = liveness.extract_face_landmarks(frame)
    if landmarks is None:
        return jsonify(ok=True, status=ctx['session'].status(), face_detected=False)

    ear = liveness.compute_ear(landmarks)
    yaw, _pitch = liveness.estimate_head_pose(landmarks, rgb.shape)
    ctx['session'].process_frame(ear, yaw)
    print(f"[liveness] yaw={yaw}, ear={ear}, challenge={ctx['session'].challenge_direction}, met={ctx['session'].challenge_met}, blinks={ctx['session'].blink_count}")
    

    return jsonify(
        ok=True,
        status=ctx['session'].status(),
        face_detected=True,
        ear=ear,
        yaw=yaw,
    )


@app.route('/api/login/verify', methods=['POST'])
def api_login_verify():
    """Step 3: final image -> face match + require liveness completed."""
    data = request.get_json(silent=True) or {}
    token = data.get('challenge_token')
    frame = data.get('frame')

    ctx = LIVENESS_SESSIONS.get(token)
    if not ctx:
        return jsonify(ok=False, error='Invalid or expired challenge'), 400

    username = ctx['username']
    live_session = ctx['session']

    if not live_session.is_complete():
        storage.log_event({
            'type': 'login_verify', 'username': username,
            'ip': _client_ip(), 'success': False,
            'reason': 'liveness_failed',
            'details': live_session.status(),
        })
        LIVENESS_SESSIONS.pop(token, None)
        _record_failure(username)
        return jsonify(ok=False, error='Liveness check failed. Possible spoofing attempt.'), 403

    user = storage.get_user(username)
    if not user:
        LIVENESS_SESSIONS.pop(token, None)
        return jsonify(ok=False, error='User not found'), 404

    emb, _loc, status = face_engine.extract_embedding(frame)
    if status != 'ok':
        _record_failure(username)
        storage.log_event({
            'type': 'login_verify', 'username': username,
            'ip': _client_ip(), 'success': False, 'reason': status,
        })
        return jsonify(ok=False, error=f'Face detection failed: {status}'), 400

    known = [storage.decrypt_embedding(t) for t in user['embeddings']]
    is_match, best, mean = face_engine.match_embedding(emb, known)

    if not is_match:
        _record_failure(username)
        LIVENESS_SESSIONS.pop(token, None)
        storage.log_event({
            'type': 'login_verify', 'username': username,
            'ip': _client_ip(), 'success': False, 'reason': 'face_mismatch',
            'best_distance': best, 'mean_distance': mean,
        })
        return jsonify(
            ok=False,
            error='Face did not match',
            best_distance=best,
        ), 403

    # Success
    _record_success(username)
    LIVENESS_SESSIONS.pop(token, None)
    session['username'] = username
    session.permanent = True
    storage.log_event({
        'type': 'login_verify', 'username': username,
        'ip': _client_ip(), 'success': True,
        'best_distance': best, 'mean_distance': mean,
    })
    return jsonify(ok=True, username=username, best_distance=best)


# =========================================================================
#                               ADMIN / SESSION
# =========================================================================
@app.route('/api/events')
def api_events():
    if not session.get('username'):
        return jsonify(ok=False, error='Not authenticated'), 401
    limit = int(request.args.get('limit', 100))
    return jsonify(ok=True, events=storage.get_events(limit))


@app.route('/api/stats')
def api_stats():
    if not session.get('username'):
        return jsonify(ok=False, error='Not authenticated'), 401
    events = storage.get_events(limit=1000)
    stats = {
        'total_events': len(events),
        'successful_logins': sum(1 for e in events if e.get('type') == 'login_verify' and e.get('success')),
        'failed_logins': sum(1 for e in events if e.get('type') == 'login_verify' and not e.get('success')),
        'liveness_failures': sum(1 for e in events if e.get('reason') == 'liveness_failed'),
        'face_mismatches': sum(1 for e in events if e.get('reason') == 'face_mismatch'),
        'registrations': sum(1 for e in events if e.get('type') == 'register'),
        'registered_users': len(storage.load_users()),
    }
    return jsonify(ok=True, stats=stats)


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('username', None)
    return jsonify(ok=True)


@app.route('/api/me')
def api_me():
    return jsonify(ok=True, username=session.get('username'))


if __name__ == '__main__':
    print('=' * 60)
    print('CSC 437 - Biometric Authentication System')
    print('=' * 60)
    print('Setup reminder: Python 3.10+ is required.')
    print('If the server does not start, follow README.md instructions.')
    print(f'Running at: http://127.0.0.1:5000')
    print(f'Data dir:   {Config.DATA_DIR}')
    print(f'Logs dir:   {Config.LOGS_DIR}')
    print('=' * 60)
    app.run(host='127.0.0.1', port=5000, debug=True)
