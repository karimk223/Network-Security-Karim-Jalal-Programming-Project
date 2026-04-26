# BioAuth — Multi-Factor Biometric Authentication System

CSC 437 — Network Security · Programming Project · Spring 2026

A facial-authentication system combining three independent factors: password verification, active liveness detection, and face embedding matching. The system includes encrypted biometric storage and a complete security audit log.

---

## Project Topic

This project implements Topic 6: Biometric Security from the course project manual. It uses ArcFace ResNet-50 (CVPR 2019), a state-of-the-art face recognition model, combined with multi-factor authentication and anti-spoofing techniques.

---

## Key Features

### Face Recognition
- ArcFace ResNet-50 (ONNX Runtime)
- 512-dimensional embeddings
- Cosine similarity matching

### Liveness Detection
- Eye Aspect Ratio (EAR) using MediaPipe FaceMesh
- Requires three deliberate blinks to pass authentication

### Secure Storage
- Encrypted embeddings using Fernet (AES-128-CBC + HMAC-SHA256)
- Passwords hashed using PBKDF2-SHA256 (200,000 iterations with per-user salt)

### Multi-Factor Authentication
- Password verification followed by biometric verification
- Prevents authentication using a single compromised factor

### Security Logging
- JSON audit log tracks:
  - Login attempts
  - Liveness results
  - Face match distances
  - Account lockouts

### Configurable Security Parameters
- Face match tolerance
- Blink detection threshold
- Lockout policy
- FAR/FRR tuning

---

## System Architecture
## System Architecture

```
Client (Browser)
│
├── register.html
├── login.html
├── dashboard.html
│
▼
Flask Backend (API)
│
├── /api/register
├── /api/login/password
├── /api/login/frame
├── /api/login/verify
│
├── face_engine.py
│   ├── ArcFace (ONNX model)
│   ├── YuNet face detection
│   └── Face alignment
│
├── liveness.py
│   ├── MediaPipe FaceMesh
│   └── Blink detection (EAR)
│
└── storage.py
    ├── Encrypted templates
    ├── Password hashing
    └── Audit logging
```

---

## Authentication Pipeline

### Registration
1. User enters username and password (minimum 8 characters)
2. Captures three face samples via webcam
3. System:
   - Detects face using YuNet
   - Aligns face using 5-point landmarks
   - Generates 512-dimensional embeddings
4. Validates consistency between samples using cosine distance
5. Stores encrypted embeddings and hashed password

---

### Login Process

#### Step 1 — Password Verification
- PBKDF2 hash verification
- If successful, a liveness challenge is issued

#### Step 2 — Liveness Detection
- Webcam frames streamed at approximately 4 FPS
- Blink detection using Eye Aspect Ratio
- Requires three valid blinks

#### Step 3 — Face Matching
- Final frame captured
- Embedding generated and compared with stored templates
- Authentication succeeds if distance is below threshold

---

## Security Properties

| Threat                          | Mitigation                                      |
|--------------------------------|------------------------------------------------|
| Password compromise            | Face matching still required                   |
| Photo spoofing                 | Liveness detection prevents static attacks     |
| Stolen database                | Embeddings encrypted at rest                   |
| Brute-force attempts           | Lockout after 5 failed attempts                |
| Replay attacks                 | Single-use, time-limited tokens                |
| CSRF                           | SameSite and HttpOnly cookies                  |

---

## Experimental Results

- Imposter (correct password + liveness): rejected  
  - Cosine distance: 0.886  

- Legitimate user: accepted  
  - Distance range: 0.06 – 0.15  

This shows a strong separation between genuine and imposter scores at the selected threshold.

---

## Tech Stack

- Python 3.10+
- Flask
- ArcFace ResNet-50 (ONNX)
- OpenCV YuNet
- MediaPipe FaceMesh
- Fernet Encryption
- PBKDF2-HMAC-SHA256
- HTML / CSS / JavaScript

---

## Running the Project

### Prerequisites

- Python 3.10 or newer
- Webcam
- macOS, Linux, or Windows

---

### Option A — Run from ZIP

```bash
cd biometric_auth
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python app.py
Open:  
http://127.0.0.1:5000
```

---

### Option B — Run from GitHub

Repository:  
https://github.com/karimk223/Network-Security-Karim-Jalal-Programming-Project

Download ZIP and follow the same steps as above.

---

### First Run Note

On first launch, the system downloads ONNX models (~166 MB) into `data/models/`. This may take a few minutes.

---

## Troubleshooting

- Python errors during installation  
  → Ensure Python version is 3.10 or newer  

- Camera not working  
  → Use http://127.0.0.1:5000 (not external URL)  

- Model download fails  
  → Check connection and rerun application

Repository Structure:
```
biometric_auth/
├── app.py
├── config.py
├── face_engine.py
├── liveness.py
├── storage.py
├── experiments.py
├── requirements.txt
├── templates/
├── static/
└── data/ (created on first run)
```

Limitations
Software-based liveness can be bypassed using advanced video attacks
Encryption key stored locally with data
Performance affected by poor lighting or occlusion
Future Work
Hardware-based liveness detection (depth or IR sensors)
External key management (KMS or HSM)
Improved robustness under challenging conditions
Authors

Karim Khalil
Jalal Al Arab

Instructor: Dr. Khaleel Mershad
