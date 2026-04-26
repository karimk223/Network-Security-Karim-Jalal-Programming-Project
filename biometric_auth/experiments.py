"""
Experiments runner for the Biometric Authentication System.

This script produces the numbers you'll cite in the "Experiments and Results"
section of the report.

Experiments implemented:
  E1. Genuine vs impostor distance distribution (requires a small face dataset)
  E2. ROC-like sweep: FAR / FRR across tolerance values 0.35 .. 0.70
  E3. Enrollment cost: time to compute & encrypt embeddings
  E4. Verification latency: end-to-end face-match time
  E5. Anti-spoofing: photo-attack simulation (same face, no blink)

USAGE:
  Place enrollment images in:  experiments/dataset/<person>/*.jpg
    - at least 2 persons
    - at least 3 images per person
  Then run:
    python experiments.py

Optional: use the LFW dataset (http://vis-www.cs.umass.edu/lfw/) — just
unpack it and pass --lfw_dir path/to/lfw.
"""
import os
import sys
import time
import json
import argparse
import random
import numpy as np
from pathlib import Path
from PIL import Image
import io
import base64

import face_engine
from storage import SecureStorage
from config import Config


def _image_to_b64(path):
    with open(path, 'rb') as f:
        data = f.read()
    return 'data:image/jpeg;base64,' + base64.b64encode(data).decode()


def _iter_dataset(dataset_dir, max_per_person=None):
    """Yield (person_id, image_path). Expects dataset_dir/<person>/*.jpg|png"""
    p = Path(dataset_dir)
    for person_dir in sorted([d for d in p.iterdir() if d.is_dir()]):
        imgs = sorted([f for f in person_dir.iterdir()
                       if f.suffix.lower() in ('.jpg', '.jpeg', '.png')])
        if max_per_person:
            imgs = imgs[:max_per_person]
        for img in imgs:
            yield person_dir.name, str(img)


def build_embedding_bank(dataset_dir, max_per_person=5, max_persons=None):
    print(f'[E0] Building embeddings from: {dataset_dir}')
    bank = {}  # person_id -> list of (embedding, path, enroll_time)
    seen_persons = 0
    for person, path in _iter_dataset(dataset_dir, max_per_person=max_per_person):
        if max_persons and person not in bank and seen_persons >= max_persons:
            continue
        t0 = time.perf_counter()
        emb, _loc, status = face_engine.extract_embedding(_image_to_b64(path))
        t1 = time.perf_counter()
        if status != 'ok':
            print(f'    skip {path}: {status}')
            continue
        if person not in bank:
            bank[person] = []
            seen_persons += 1
        bank[person].append((emb, path, t1 - t0))
    # Keep only persons with >= 2 images
    bank = {k: v for k, v in bank.items() if len(v) >= 2}
    total_imgs = sum(len(v) for v in bank.values())
    print(f'    -> {len(bank)} persons, {total_imgs} images usable')
    return bank


# -------------------------------------------------------------------------
def E1_distance_distribution(bank):
    print('\n[E1] Genuine vs impostor distance distribution')
    genuine_dists, impostor_dists = [], []
    persons = list(bank.keys())
    for p in persons:
        imgs = bank[p]
        for i in range(len(imgs)):
            for j in range(i + 1, len(imgs)):
                genuine_dists.append(face_engine.compare_distance(imgs[i][0], imgs[j][0]))
    for i in range(len(persons)):
        for j in range(i + 1, len(persons)):
            for a in bank[persons[i]]:
                for b in bank[persons[j]]:
                    impostor_dists.append(face_engine.compare_distance(a[0], b[0]))

    def stats(xs):
        return {
            'n': len(xs),
            'mean': float(np.mean(xs)) if xs else None,
            'std':  float(np.std(xs))  if xs else None,
            'min':  float(np.min(xs))  if xs else None,
            'max':  float(np.max(xs))  if xs else None,
        }

    result = {'genuine': stats(genuine_dists), 'impostor': stats(impostor_dists)}
    print('    genuine :', result['genuine'])
    print('    impostor:', result['impostor'])
    return result, genuine_dists, impostor_dists


# -------------------------------------------------------------------------
def E2_far_frr_sweep(genuine, impostor):
    print('\n[E2] FAR / FRR sweep across tolerance values')
    rows = []
    for tol in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        # FRR = genuine pairs incorrectly rejected (distance > tol)
        # FAR = impostor pairs incorrectly accepted (distance <= tol)
        frr = (np.sum(np.array(genuine)  > tol) / len(genuine))  if genuine  else None
        far = (np.sum(np.array(impostor) <= tol) / len(impostor)) if impostor else None
        acc = None
        if genuine and impostor:
            correct = np.sum(np.array(genuine) <= tol) + np.sum(np.array(impostor) > tol)
            acc = correct / (len(genuine) + len(impostor))
        rows.append({'tolerance': tol, 'FAR': far, 'FRR': frr, 'accuracy': acc})
        print(f'    tol={tol:.2f}  FAR={far:.4f}  FRR={frr:.4f}  Acc={acc:.4f}')
    # Find operating point nearest EER
    def diff(r): return abs(r['FAR'] - r['FRR']) if r['FAR'] is not None else 1
    eer = min(rows, key=diff)
    print(f'    Approx EER near tol={eer["tolerance"]}: FAR={eer["FAR"]:.4f} FRR={eer["FRR"]:.4f}')
    return rows, eer


# -------------------------------------------------------------------------
def E3_enrollment_cost(bank):
    print('\n[E3] Enrollment cost')
    times = [t for v in bank.values() for (_e, _p, t) in v]
    storage = SecureStorage()
    enc_times = []
    for v in bank.values():
        for (e, _p, _t) in v:
            t0 = time.perf_counter()
            _ = storage.encrypt_embedding(e)
            enc_times.append(time.perf_counter() - t0)
    res = {
        'embed_extract_ms': {
            'mean': float(np.mean(times)) * 1000,
            'std':  float(np.std(times)) * 1000,
        },
        'encrypt_ms': {
            'mean': float(np.mean(enc_times)) * 1000,
            'std':  float(np.std(enc_times)) * 1000,
        },
    }
    print(f'    embed extract: {res["embed_extract_ms"]["mean"]:.1f} ± {res["embed_extract_ms"]["std"]:.1f} ms')
    print(f'    encrypt:       {res["encrypt_ms"]["mean"]:.3f} ± {res["encrypt_ms"]["std"]:.3f} ms')
    return res


# -------------------------------------------------------------------------
def E4_verify_latency(bank):
    print('\n[E4] Verification latency (extract + match)')
    storage = SecureStorage()
    enroll_encrypted = {}
    for person, items in bank.items():
        enroll_encrypted[person] = [storage.encrypt_embedding(e) for (e, _p, _t) in items[:3]]

    total = []
    for person, items in bank.items():
        if len(items) < 4:
            continue
        probe_img_b64 = _image_to_b64(items[-1][1])
        t0 = time.perf_counter()
        emb, _l, status = face_engine.extract_embedding(probe_img_b64)
        known = [storage.decrypt_embedding(tok) for tok in enroll_encrypted[person]]
        _match, _best, _mean = face_engine.match_embedding(emb, known)
        total.append(time.perf_counter() - t0)
    if not total:
        print('    insufficient probes for latency test')
        return None
    res = {
        'verify_ms': {
            'mean': float(np.mean(total)) * 1000,
            'std':  float(np.std(total)) * 1000,
            'min':  float(np.min(total)) * 1000,
            'max':  float(np.max(total)) * 1000,
            'n':    len(total),
        }
    }
    print(f'    verify: {res["verify_ms"]["mean"]:.1f} ± {res["verify_ms"]["std"]:.1f} ms (n={res["verify_ms"]["n"]})')
    return res


# -------------------------------------------------------------------------
def E5_photo_attack_simulation():
    """
    Simulates presentation-attack resistance: the face match alone would pass,
    but the liveness layer rejects because no blink is detected.
    """
    print('\n[E5] Anti-spoofing: photo-attack simulation')
    from liveness import LivenessSession
    # Scenario: attacker holds up a printed photo. EAR is roughly constant (no blink),
    # and head pose is fixed at 0 degrees.
    s = LivenessSession(challenge_direction='left')
    for _ in range(40):   # 10 seconds at 4 fps
        s.process_frame(ear=0.30, yaw=0.0)
    passed = s.is_complete()
    print(f'    blinks detected: {s.blink_count}  challenge met: {s.challenge_met}  PASSED={passed}')

    # Legitimate user: has blinks + turns head
    s2 = LivenessSession(challenge_direction='left')
    ear_trace = []
    for i in range(40):
        ear = 0.30 if (i % 12 < 10) else 0.10  # blink every ~3s
        yaw = -20.0 if i > 10 else 0.0
        ear_trace.append(ear)
        s2.process_frame(ear=ear, yaw=yaw)
    passed2 = s2.is_complete()
    print(f'    (legit) blinks: {s2.blink_count}  challenge met: {s2.challenge_met}  PASSED={passed2}')

    return {
        'photo_attack_passed': passed,
        'legit_user_passed': passed2,
        'spoof_rejection_rate': 0.0 if passed else 1.0,
    }


# -------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', default='experiments/dataset')
    ap.add_argument('--lfw_dir', default=None,
                    help='Optional path to LFW root. Uses first N persons with >=3 images.')
    ap.add_argument('--max_persons', type=int, default=30)
    ap.add_argument('--max_per_person', type=int, default=5)
    ap.add_argument('--out', default='experiments/results.json')
    args = ap.parse_args()

    dataset = args.lfw_dir if args.lfw_dir else args.dataset
    if not os.path.isdir(dataset):
        print(f'Dataset dir not found: {dataset}')
        print('Create one with this layout:')
        print('  experiments/dataset/alice/{1.jpg,2.jpg,3.jpg}')
        print('  experiments/dataset/bob/{1.jpg,2.jpg,3.jpg}')
        print('Or download LFW and pass --lfw_dir.')
        # Still run E5 (synthetic), so the report has at least one result
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        out = {'E5_photo_attack': E5_photo_attack_simulation()}
        with open(args.out, 'w') as f:
            json.dump(out, f, indent=2)
        print(f'\nWrote: {args.out}')
        return

    bank = build_embedding_bank(dataset, max_per_person=args.max_per_person,
                                max_persons=args.max_persons)
    if len(bank) < 2:
        print('Need at least 2 persons with >=2 images each.')
        return

    r1, gen, imp = E1_distance_distribution(bank)
    r2, eer = E2_far_frr_sweep(gen, imp)
    r3 = E3_enrollment_cost(bank)
    r4 = E4_verify_latency(bank)
    r5 = E5_photo_attack_simulation()

    out = {
        'dataset': dataset,
        'n_persons': len(bank),
        'n_images': sum(len(v) for v in bank.values()),
        'E1_distances': r1,
        'E2_far_frr': r2,
        'E2_eer_point': eer,
        'E3_enrollment': r3,
        'E4_verification': r4,
        'E5_photo_attack': r5,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'\nWrote: {args.out}')


if __name__ == '__main__':
    main()
