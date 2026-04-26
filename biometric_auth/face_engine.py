"""
Face recognition engine using ArcFace (ONNX) directly via onnxruntime.
Face detection by OpenCV's YuNet (ships inside opencv-python).

No C++ compilation required anywhere - all dependencies are prebuilt wheels.

Pipeline:
  1. Detect face with YuNet (CNN-based, inside cv2.FaceDetectorYN)
  2. Align to 112x112 crop using 5 facial landmarks
  3. Run ArcFace ONNX inference -> 512-d embedding
  4. Compare embeddings with cosine distance

Models are auto-downloaded on first use and cached in data/models/.
"""
import io
import os
import base64
import hashlib
import numpy as np
from PIL import Image
import cv2
import onnxruntime as ort

from config import Config


# =========================================================================
# Model files (auto-downloaded once on first run)
# =========================================================================
MODELS_DIR = os.path.join(Config.DATA_DIR, 'models')

ARCFACE_MODEL = {
    'url':  'https://github.com/yakhyo/face-reidentification/releases/download/v0.0.1/w600k_r50.onnx',
    'path': os.path.join(MODELS_DIR, 'arcface.onnx'),
}

YUNET_MODEL = {
    'url':  'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',
    'path': os.path.join(MODELS_DIR, 'yunet.onnx'),
}


def _download(url, path):
    import requests
    os.makedirs(os.path.dirname(path), exist_ok=True)
    print(f'[face_engine] downloading {os.path.basename(path)} ...')
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    total = 0
    with open(path + '.tmp', 'wb') as f:
        for chunk in r.iter_content(chunk_size=1 << 15):
            if chunk:
                f.write(chunk)
                total += len(chunk)
    os.replace(path + '.tmp', path)
    print(f'[face_engine] downloaded {total // 1024} KB -> {path}')


def _ensure_models():
    if not os.path.exists(ARCFACE_MODEL['path']):
        _download(ARCFACE_MODEL['url'], ARCFACE_MODEL['path'])
    if not os.path.exists(YUNET_MODEL['path']):
        _download(YUNET_MODEL['url'], YUNET_MODEL['path'])


# =========================================================================
# Singletons
# =========================================================================
_ARCFACE_SESSION = None
_DETECTOR = None


def _get_arcface():
    global _ARCFACE_SESSION
    if _ARCFACE_SESSION is None:
        _ensure_models()
        _ARCFACE_SESSION = ort.InferenceSession(
            ARCFACE_MODEL['path'],
            providers=['CPUExecutionProvider']
        )
    return _ARCFACE_SESSION


def _get_detector(img_w=640, img_h=480):
    """YuNet detector - creates new instance if size changed."""
    global _DETECTOR
    _ensure_models()
    if _DETECTOR is None:
        _DETECTOR = cv2.FaceDetectorYN.create(
            YUNET_MODEL['path'],
            '',
            (img_w, img_h),
            score_threshold=0.7,
            nms_threshold=0.3,
            top_k=5000,
        )
    _DETECTOR.setInputSize((img_w, img_h))
    return _DETECTOR


# =========================================================================
# Image decoding
# =========================================================================
def _decode_image(image_data):
    """Accept data URL / base64 / bytes. Return BGR uint8 array (OpenCV format)."""
    if isinstance(image_data, str):
        if image_data.startswith('data:'):
            image_data = image_data.split(',', 1)[1]
        image_bytes = base64.b64decode(image_data)
    elif isinstance(image_data, (bytes, bytearray)):
        image_bytes = image_data
    else:
        raise ValueError('Unsupported image_data type')
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    rgb = np.array(img)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# =========================================================================
# Face alignment (5-point similarity transform to canonical 112x112)
# =========================================================================
# Canonical landmark positions for ArcFace 112x112 input
ARCFACE_DST = np.array([
    [38.2946, 51.6963],   # right eye
    [73.5318, 51.5014],   # left eye
    [56.0252, 71.7366],   # nose
    [41.5493, 92.3655],   # right mouth
    [70.7299, 92.2041],   # left mouth
], dtype=np.float32)


def _align_face(bgr, landmarks_5):
    """
    landmarks_5: (5,2) numpy array in image pixel coords.
    Returns 112x112 BGR aligned face crop.
    """
    src = landmarks_5.astype(np.float32)
    M, _ = cv2.estimateAffinePartial2D(src, ARCFACE_DST, method=cv2.LMEDS)
    if M is None:
        # Fall back to a naive crop around landmark centroid
        return cv2.resize(bgr, (112, 112))
    aligned = cv2.warpAffine(bgr, M, (112, 112), borderValue=0.0)
    return aligned


# =========================================================================
# ArcFace inference
# =========================================================================
def _arcface_embed(aligned_bgr):
    """Run ArcFace on a 112x112 BGR crop. Returns L2-normalized 512-d vector."""
    # This w600k model expects BGR, scaled to [-1, 1] as (x - 127.5) / 127.5
    blob = cv2.dnn.blobFromImage(
        aligned_bgr,
        scalefactor=1.0 / 127.5,
        size=(112, 112),
        mean=(127.5, 127.5, 127.5),
        swapRB=False,
        crop=False,
    ).astype(np.float32)
    sess = _get_arcface()
    input_name = sess.get_inputs()[0].name
    out = sess.run(None, {input_name: blob})[0]
    emb = out[0].astype(np.float64)
    n = np.linalg.norm(emb)
    if n > 0:
        emb = emb / n
    return emb


# =========================================================================
# Public API
# =========================================================================
def extract_embedding(image_data):
    """
    Detect one face, align, embed.
    Returns (embedding, bbox_xywh, status).
    status in {'ok', 'no_face', 'multiple_faces'}
    """
    bgr = _decode_image(image_data)
    h, w = bgr.shape[:2]
    det = _get_detector(w, h)
    _, faces = det.detect(bgr)

    if faces is None or len(faces) == 0:
        return None, None, 'no_face'
    if len(faces) > 1:
        # Keep only if one face is dominant; else bail
        # YuNet returns scored rows sorted by confidence
        # For our auth use case, require exactly one face
        return None, None, 'multiple_faces'

    f = faces[0]
    # f layout: [x, y, w, h, lm_rx, lm_ry, lm_lx, lm_ly, lm_nx, lm_ny,
    #            lm_rmx, lm_rmy, lm_lmx, lm_lmy, score]
    bbox = f[0:4].astype(int).tolist()
    lm = np.array([
        [f[4],  f[5]],    # right eye
        [f[6],  f[7]],    # left eye
        [f[8],  f[9]],    # nose
        [f[10], f[11]],   # right mouth
        [f[12], f[13]],   # left mouth
    ], dtype=np.float32)

    aligned = _align_face(bgr, lm)
    emb = _arcface_embed(aligned)
    return emb, bbox, 'ok'


def cosine_distance(a, b):
    """Cosine distance in [0, 2]; same person typically < 0.40."""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 2.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def compare_distance(a, b):
    return cosine_distance(a, b)


def match_embedding(candidate, known_embeddings, tolerance=None):
    """Returns (is_match, best_distance, mean_distance)."""
    if tolerance is None:
        tolerance = Config.FACE_MATCH_TOLERANCE
    if not known_embeddings:
        return False, None, None
    dists = [cosine_distance(candidate, k) for k in known_embeddings]
    best = float(min(dists))
    mean = float(sum(dists) / len(dists))
    return (best <= tolerance), best, mean
