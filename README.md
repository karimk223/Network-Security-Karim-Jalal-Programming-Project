IMPORTANT: Follow the "Running the Project" section below before launching the application.
# BioAuth — Multi-Factor Biometric Authentication System

CSC 437 — Network Security  
Programming Project — Spring 2026  

BioAuth is a secure authentication system combining three factors:
- Password verification  
- Active liveness detection (blink-based)  
- Face embedding matching  

The system also includes encrypted biometric storage and a complete security audit log.

---

## Project Overview

This project implements a biometric security system using a multi-factor authentication approach.  
It combines modern face recognition with liveness detection and secure credential storage to simulate a real-world authentication system.

---

## Key Features

- ArcFace ResNet-50 face recognition (512-dimensional embeddings)
- Cosine similarity matching
- Blink-based liveness detection using MediaPipe FaceMesh
- Encrypted face template storage (Fernet)
- Secure password hashing (PBKDF2-SHA256)
- Multi-factor authentication (password + biometrics)
- Session logging and audit tracking
- Configurable security thresholds

---

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
1. User enters username and password  
2. Captures three face samples  
3. System generates embeddings  
4. Validates consistency  
5. Stores encrypted templates and hashed password  

### Login Process

Step 1 — Password Verification  
- Validates password using PBKDF2  

Step 2 — Liveness Detection  
- Detects blinks using Eye Aspect Ratio  
- Requires three valid blinks  

Step 3 — Face Matching  
- Captures final frame  
- Compares embeddings  
- Grants access if within threshold  

---

## Security Properties

| Threat                   | Protection                           |
|------------------------|--------------------------------------|
| Password compromise     | Requires biometric match             |
| Photo spoofing          | Blink-based liveness detection       |
| Database breach         | Encrypted templates                  |
| Brute-force attempts    | Lockout after multiple failures      |
| Replay attacks          | Time-limited tokens                  |
| CSRF                    | Secure session cookies               |

---

## Tech Stack

- Python 3.10+ (recommended: Python 3.12)
- Flask
- ArcFace (ONNX Runtime)
- OpenCV (YuNet)
- MediaPipe FaceMesh
- Cryptography (Fernet)
- PBKDF2-HMAC-SHA256
- HTML / CSS / JavaScript

---

## Running the Project

### Prerequisites

- Python **3.10 or newer** (required)  
- Webcam  
- macOS, Linux, or Windows  

---

### Steps to Run

```bash
cd biometric_auth

# Check Python version (must be 3.10+)
python3 --version

# Create virtual environment
python3 -m venv venv

# Activate it
venv\Scripts\activate     # Mac: source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Run the server
python app.py
```

Open in browser:
http://127.0.0.1:5000

---

### If Python version is below 3.10

Use a newer version if available:

```bash
python3.12 -m venv venv
venv\Scripts\activate     # Mac: source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

---

## First Run Note

On first launch, the system downloads required ONNX models (~166 MB).  
This may take 1–3 minutes depending on your internet connection.

---

## Troubleshooting

- Python errors  
  → Ensure Python version is 3.10 or newer  

- Camera not working  
  → Use http://127.0.0.1:5000 (local access required)  

- Model download fails  
  → Check internet connection and restart the application  

---

## Repository Structure

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

---

## Limitations

- Software-based liveness can be bypassed by advanced video attacks  
- Encryption key is stored locally  
- Performance may degrade under poor lighting  

---

## Future Work

- Hardware-based liveness detection (depth / IR sensors)  
- External key management (KMS / HSM)  
- Improved robustness and accuracy  

---

## Authors

Karim Khalil  
Jalal Al Arab  

Instructor: Dr. Khaleel Mershad
