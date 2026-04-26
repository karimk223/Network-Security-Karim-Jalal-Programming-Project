Project
BioAuth — Multi-Factor Biometric Authentication System
CSC 437 — Network Security · Programming Project · Spring 2026
A facial-authentication login system built around three independent factors —
password, active liveness detection, and face-embedding match —
with encrypted template storage at rest and a full security audit log.

Project topic
This project implements Topic 6: Biometric Security from the course
project manual. The system uses ArcFace ResNet-50 (CVPR 2019), the current
state-of-the-art in face recognition, in a creative manner to enhance
authentication accuracy through multi-factor composition and active
anti-spoofing.

Novelty over baseline student face-login projects
Most undergraduate face-login projects stop at a single
face_recognition.compare_faces call. This project adds:

State-of-the-art face embeddings. ArcFace ResNet-50 (CVPR 2019),
loaded directly via ONNX Runtime — the same model family used in modern
production systems. 512-dimensional embeddings compared by cosine
distance.
Active liveness detection. Eye Aspect Ratio (Soukupová & Čech, 2016)
on MediaPipe FaceMesh landmarks. The user must produce three deliberate
blinks within the challenge window — a printed photograph cannot blink.
Encrypted template storage. Face embeddings are encrypted with
Fernet (AES-128-CBC + HMAC-SHA256) before being written to disk. An
attacker who exfiltrates the user database obtains only ciphertext.
Password + biometric composition. A PBKDF2-SHA256 password gate
(200 000 iterations, per-user 16-byte salt) runs before the biometric
factor. A leaked face image alone cannot authenticate.
Enrollment self-consistency check. During registration, the
pairwise cosine distance between captured samples is verified to ensure
all three samples are of the same individual.
Full security telemetry. Every event (enrollment, password
verification, liveness pass/fail, face-match distance, lockout) is
logged to a JSON audit trail, surfaced through an admin dashboard.
Tunable operating point. Match tolerance, EAR threshold, blink
count, and lockout policy are all exposed in config.py so the
FAR/FRR trade-off can be empirically tuned.


Architecture
Browser                                  Flask server
─────────                                 ─────────────
register.html ─┐                          /api/register
login.html ────┼── getUserMedia() ──────► /api/login/password
dashboard.html │      JPEG frames         /api/login/frame   (~4 fps)
admin.html ────┘                          /api/login/verify
                                                │
                                                ├── face_engine.py
                                                │     • ArcFace ResNet-50 (ONNX)
                                                │     • YuNet face detector (OpenCV)
                                                │     • 5-point affine alignment
                                                │     • 512-d cosine matching
                                                │
                                                ├── liveness.py
                                                │     • MediaPipe FaceMesh (468 landmarks)
                                                │     • Eye Aspect Ratio blink detection
                                                │
                                                └── storage.py
                                                      • Fernet-encrypted templates
                                                      • PBKDF2-SHA256 passwords
                                                      • JSON audit log

Authentication pipeline
Registration. The user supplies a username and password (≥ 8 chars)
and captures three face samples from their webcam. The server detects the
face with YuNet, aligns it to a canonical 112×112 crop using 5 facial
landmarks, and produces an L2-normalized 512-d ArcFace embedding for each
sample. Pairwise cosine distance must be below a configurable bound to
ensure all three samples are consistent. Embeddings are then encrypted with
Fernet and written to disk alongside the PBKDF2-SHA256 password hash.
Login (3 stages).

Password factor — server verifies the PBKDF2 hash. On success,
issues a single-use, time-limited liveness challenge token.
Liveness factor — the client streams webcam frames at ~4 fps. For
each frame the server computes Eye Aspect Ratio for both eyes from
MediaPipe FaceMesh landmarks. A blink is registered when EAR drops below
0.21 for at least one frame and recovers. Three deliberate blinks within
the challenge window are required.
Face match — a high-resolution final frame is captured. Face is
detected with YuNet, aligned, and embedded with ArcFace. The minimum
cosine distance against the user's enrolled templates is compared
against FACE_MATCH_TOLERANCE (default 0.40). On success, a session
cookie is issued.


Security properties
ThreatMitigationPassword compromise aloneFace match still rejects the imposterPrinted-photo presentation attackLiveness layer rejects (no blinks possible on a still image)Stolen template databaseEmbeddings are Fernet-encrypted at restBrute-force login5 failed attempts → 15-minute lockoutReplay of an old challengeLiveness tokens are single-use and time-limitedCross-origin / CSRFSameSite=Lax, HttpOnly session cookie, JSON API

Experimental result
In a controlled imposter-with-stolen-password test, an attacker who knew
the victim's password and successfully passed the liveness challenge (real
human, real blinks) was rejected at the face-match stage with a cosine
distance of 0.886. Legitimate logins by the enrolled user produced
distances in the 0.06 – 0.15 range — a roughly tenfold separation
between genuine and imposter scores at the chosen tolerance of 0.40.

Tech stack

Python 3.10+ · Flask — backend API and templating
ArcFace ResNet-50 (ONNX) — 512-dimensional face embeddings (Deng et al., CVPR 2019)
OpenCV YuNet — CNN-based face detector (Wu et al., 2023)
MediaPipe FaceMesh — 468-point facial landmarks for EAR
cryptography (Fernet) — symmetric template encryption
PBKDF2-HMAC-SHA256 — password hashing (200 k iterations)
Vanilla HTML / CSS / JS — frontend (no build step)


Running the project
Prerequisites

Python 3.10 or newer (Python 3.9 is NOT supported — MediaPipe and JAX require ≥ 3.10).
Verify your version with python3 --version. If your system Python is 3.9 or older,
install Python 3.10+ from python.org or via Homebrew (brew install python@3.12).
A working webcam.
macOS, Linux, or Windows.

Option A — Running from the submitted ZIP file

Unzip the submission file. You will get a folder containing this
README.md and a subfolder named biometric_auth/.
Open a terminal in the unzipped folder and run:

bashcd biometric_auth
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python app.py

On first launch the server will auto-download two ONNX face-recognition
models (~166 MB total) into data/models/. This takes 1–3 minutes
depending on your connection. Subsequent launches are instant.
Open http://127.0.0.1:5000 in Chrome or Firefox.
Click Register, create a test account, capture three face samples,
then click Login to verify all three factors work end-to-end.

Option B — Running from the GitHub repository
The project is also published at:
https://github.com/karimk223/Network-Security-Karim-Jalal-Programming-Project

Open the GitHub link above in a browser.
Click the green Code button → Download ZIP. The file
Network-Security-Karim-Jalal-Programming-Project-main.zip will
download to your Downloads/ folder.
Unzip the file. You will get a folder named
Network-Security-Karim-Jalal-Programming-Project-main/ containing
this README.md and a subfolder named biometric_auth/.
Open a terminal in the unzipped folder and run:

bashcd biometric_auth
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python app.py

On first launch the server will auto-download two ONNX face-recognition
models (~166 MB total) into data/models/. This takes 1–3 minutes
depending on your connection. Subsequent launches are instant.
Open http://127.0.0.1:5000 in Chrome or Firefox.
Click Register, create a test account, capture three face samples,
then click Login to verify all three factors work end-to-end.

Troubleshooting

SyntaxError during pip install — your Python is older than 3.10.
Install Python 3.10+ and recreate the venv with the newer interpreter:
rm -rf venv && python3.12 -m venv venv (replace python3.12 with
whichever 3.10+ binary you installed).
Browser denies camera access — make sure you opened
http://127.0.0.1:5000 (not a remote URL); browsers only allow webcam
access on localhost without HTTPS.
ONNX model download fails — check your internet connection and
re-run python app.py; the download resumes automatically.


Repository layout
Network-Security-Karim-Jalal-Programming-Project/
├── README.md
└── biometric_auth/
    ├── app.py                  # Flask routes & login state machine
    ├── config.py               # Tunable thresholds (tolerance, EAR, lockout)
    ├── face_engine.py          # ArcFace ONNX wrapper + YuNet face detection
    ├── liveness.py             # MediaPipe FaceMesh + EAR blink detection
    ├── storage.py              # Encrypted user store + audit log
    ├── experiments.py          # FAR / FRR sweep runner
    ├── requirements.txt
    ├── templates/              # index, register, login, dashboard, admin
    ├── static/                 # CSS + JS
    └── experiments/
        └── results.json        # Benchmark results from FAR/FRR sweep
biometric_auth/data/ and biometric_auth/logs/ are created on first run
and excluded from version control. They contain the encrypted user
database, the Fernet key, the downloaded ONNX models, and the runtime
audit log.

Limitations and future work

Software-only liveness. A sophisticated attacker with a phone
displaying a short looping video of the user blinking can still pass.
Depth cameras or IR sensing (Face ID-style) would be required to defeat
this class of attacks.
Co-located encryption key. The Fernet key currently lives on the
same host as the ciphertext; a root-level compromise defeats encryption
at rest. A production deployment would store the key in a KMS or HSM.
Lighting and occlusion sensitivity. Recognition accuracy degrades
under poor lighting or with face coverings. A quality-score gate before
embedding would improve robustness.


Authors
Karim Khalil · Jalal Al Arab
CSC 437 Network Security · Spring 2026
Submitted to: Dr. Khaleel Mershad
