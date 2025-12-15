import os
import cv2
import pickle
import numpy as np
import base64
import subprocess
import sys
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from keras_facenet import FaceNet

# ---------------- CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_DIR = os.path.join(DATA_DIR, "users")
EMB_PKL = os.path.join(DATA_DIR, "embeddings_facenet.pkl")
RESULT_DIR = os.path.join(BASE_DIR, "static", "results")
ATT_DIR = os.path.join(DATA_DIR, "Attendance")

os.makedirs(USERS_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(ATT_DIR, exist_ok=True)

IMG_SZ = (160, 160)
SIM_THRESHOLD = 0.60

# Colab consensus constants (exact match)
PER_FRAME_SIM = 0.60
CONSENSUS_FRAMES = 2
INSTANT_SIM_THRESH = 0.82
UNKNOWN_FRAMES_TO_BLOCK = 2

# ---------------- INIT ----------------
app = Flask(__name__)

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

embedder = FaceNet()

# load embeddings safely
MEANS = {}
if os.path.exists(EMB_PKL):
    db = pickle.load(open(EMB_PKL, "rb"))
    MEANS = db.get("mean", {})

# ---------------- HELPERS ----------------
def is_valid_image(img):
    return img is not None and isinstance(img, np.ndarray) and img.size > 0

def base64_to_image(base64_string):
    """Convert base64 data URL to OpenCV image"""
    # Remove data URL prefix if present
    if ',' in base64_string:
        base64_string = base64_string.split(',')[1]
    
    img_data = base64.b64decode(base64_string)
    img_array = np.frombuffer(img_data, np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return image

def image_to_base64(image):
    """Convert OpenCV image to base64 data URL"""
    _, buffer = cv2.imencode('.jpg', image)
    img_base64 = base64.b64encode(buffer).decode('utf-8')
    return f"data:image/jpeg;base64,{img_base64}"

def recognize_image(image):
    annotated = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 5)

    if len(faces) == 0:
        cv2.putText(annotated, "No face detected", (20,40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
        return "No Face", 0.0, "blocked_unknowns", annotated

    x,y,w,h = sorted(faces, key=lambda r: r[2]*r[3], reverse=True)[0]
    crop = image[y:y+h, x:x+w]

    crop = cv2.resize(crop, IMG_SZ)
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

    emb = embedder.embeddings([rgb])[0]
    emb /= (np.linalg.norm(emb) + 1e-10)

    best_name = "Unknown"
    best_sim = 0.0

    for name, mean_emb in MEANS.items():
        sim = float(np.dot(emb, mean_emb))
        if sim > best_sim:
            best_sim = sim
            best_name = name

    if best_sim < SIM_THRESHOLD:
        best_name = "Unknown"
        reason = "blocked_unknowns"
        color = (0,0,255)
    else:
        reason = "accepted"
        color = (0,255,0)

    label = f"{best_name} {best_sim:.2f}"
    cv2.rectangle(annotated, (x,y),(x+w,y+h), color, 2)
    cv2.putText(annotated, label, (x, y-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    return best_name, best_sim, reason, annotated

# ---------------- ROUTES ----------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

# -------- ADD USER (NEW) --------
@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form.get("name")
    
    # Handle both file upload and base64 frame
    image = None
    if request.files.get("image"):
        file = request.files.get("image")
        img_bytes = np.frombuffer(file.read(), np.uint8)
        image = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
    elif request.form.get("frame"):
        # Handle base64 frame from camera
        frame_data = request.form.get("frame")
        image = base64_to_image(frame_data)

    if not name or not image or not is_valid_image(image):
        return jsonify({"error": "Name and valid image required"}), 400

    person_dir = os.path.join(USERS_DIR, name)
    os.makedirs(person_dir, exist_ok=True)

    # Count existing images to get next index
    existing = [f for f in os.listdir(person_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
    idx = len(existing) + 1
    img_path = os.path.join(person_dir, f"{name}_{idx:03d}.jpg")
    cv2.imwrite(img_path, image)

    return jsonify({
        "status": "saved",
        "path": img_path,
        "count": idx,
        "note": "Add more images, then rebuild embeddings"
    })

# -------- ADD USER FRAME (Auto-capture endpoint) --------
@app.route("/add_user_frame", methods=["POST"])
def add_user_frame():
    name = request.form.get("name")
    frame_data = request.form.get("frame")

    if not name or not frame_data:
        return jsonify({"saved": False})

    image = base64_to_image(frame_data)
    if image is None or image.size == 0:
        return jsonify({"saved": False})

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60,60)
    )

    if len(faces) == 0:
        return jsonify({"saved": False})

    # largest face (same as Colab)
    x,y,w,h = sorted(faces, key=lambda r: r[2]*r[3], reverse=True)[0]
    face = image[y:y+h, x:x+w]

    if face.size == 0:
        return jsonify({"saved": False})

    face = cv2.resize(face, IMG_SZ)

    person_dir = os.path.join(USERS_DIR, name)
    os.makedirs(person_dir, exist_ok=True)

    idx = len([f for f in os.listdir(person_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]) + 1
    cv2.imwrite(os.path.join(person_dir, f"{name}_{idx:03d}.jpg"), face)

    return jsonify({"saved": True, "count": idx})

# -------- REBUILD EMBEDDINGS --------
@app.route("/rebuild_embeddings", methods=["POST"])
def rebuild_embeddings():
    """
    Runs build_embeddings.py and reloads embeddings into memory
    """
    try:
        # Run the embedding builder using SAME python + venv
        subprocess.run(
            [sys.executable, "build_embeddings.py"],
            check=True,
            cwd=BASE_DIR
        )

        # Reload embeddings after rebuild
        global MEANS
        db = pickle.load(open(EMB_PKL, "rb"))
        MEANS = db.get("mean", {})

        return jsonify({
            "status": "success",
            "users": list(MEANS.keys())
        })

    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "error",
            "message": "Embedding build failed",
            "details": str(e)
        }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Failed to rebuild embeddings",
            "details": str(e)
        }), 500

@app.route("/recognize", methods=["POST"])
def recognize():
    data = request.get_json()
    if not isinstance(data, list) or len(data) == 0:
        return jsonify({"error": "No frames received"}), 400

    per_name_counts = {}
    per_name_sums = {}
    unknown_frame_count = 0
    max_sim_seen = 0.0
    max_sim_name = None
    last_annotated = None

    # Process ALL frames (not just the last one) - matches Colab logic
    for frame_data in data:
        frame = base64_to_image(frame_data)
        if not is_valid_image(frame):
            unknown_frame_count += 1
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60,60))
        annotated = frame.copy()

        if len(faces) == 0:
            unknown_frame_count += 1
            last_annotated = annotated
            continue

        x,y,w,h = sorted(faces, key=lambda r: r[2]*r[3], reverse=True)[0]
        crop = frame[y:y+h, x:x+w]

        if crop.size == 0:
            unknown_frame_count += 1
            continue

        crop = cv2.resize(crop, IMG_SZ)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        emb = embedder.embeddings([rgb])[0]
        emb /= (np.linalg.norm(emb) + 1e-10)

        best_name = None
        best_sim = 0.0
        for name, mean_emb in MEANS.items():
            sim = float(np.dot(emb, mean_emb))
            if sim > best_sim:
                best_sim = sim
                best_name = name

        # Track frames meeting PER_FRAME_SIM threshold (CRITICAL: check best_name is not None)
        if best_sim >= PER_FRAME_SIM and best_name is not None:
            per_name_counts[best_name] = per_name_counts.get(best_name, 0) + 1
            per_name_sums[best_name] = per_name_sums.get(best_name, 0.0) + best_sim
        else:
            unknown_frame_count += 1

        if best_sim > max_sim_seen:
            max_sim_seen = best_sim
            max_sim_name = best_name

        # Display label: show "Unknown" if similarity below threshold (matches Colab semantics)
        display_name = best_name if (best_sim >= PER_FRAME_SIM and best_name is not None) else "Unknown"
        color = (0,255,0) if best_sim >= PER_FRAME_SIM and best_name is not None else (0,0,255)
        label = f"{display_name} {best_sim:.2f}"
        cv2.rectangle(annotated, (x,y),(x+w,y+h), color, 2)
        cv2.putText(annotated, label, (x, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

        last_annotated = annotated

        # Early exit: instant accept threshold
        if max_sim_seen >= INSTANT_SIM_THRESH:
            break

        # Early exit: too many unknown frames
        if unknown_frame_count >= UNKNOWN_FRAMES_TO_BLOCK:
            break

    # STRICT ACCEPTANCE LOGIC (matches Colab exactly)
    accepted = None
    
    # Rule 1: Consensus (2+ frames with same name above PER_FRAME_SIM)
    for name, count in per_name_counts.items():
        if count >= CONSENSUS_FRAMES:
            accepted = name
            break
    
    # Rule 2: Instant accept (single frame above INSTANT_SIM_THRESH)
    if not accepted and max_sim_seen >= INSTANT_SIM_THRESH and max_sim_name is not None:
        accepted = max_sim_name
    
    # If neither condition met → Unknown (strict rejection)

    # Save annotated image to results folder
    result_img_base64 = None
    result_img_url = None
    
    if last_annotated is not None and is_valid_image(last_annotated):
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # milliseconds
        filename = f"detection_{timestamp}.jpg"
        output_path = os.path.join(RESULT_DIR, filename)
        
        # Save the annotated image
        cv2.imwrite(output_path, last_annotated)
        
        # Convert to base64 for immediate display
        result_img_base64 = image_to_base64(last_annotated)
        
        # Generate URL for the saved image
        result_img_url = f"/static/results/{filename}"

    # Record attendance if accepted
    if accepted and accepted != "Unknown":
        csv_path = os.path.join(
            ATT_DIR, f"Attendance_{datetime.now().strftime('%d-%m-%Y')}.csv"
        )
        avg_sim = per_name_sums.get(accepted, max_sim_seen) / per_name_counts.get(accepted, 1)
        write_header = not os.path.exists(csv_path)
        with open(csv_path, "a") as f:
            if write_header:
                f.write("NAME,TIME,SIMILARITY\n")
            f.write(f"{accepted},{datetime.now().strftime('%H:%M:%S')},{avg_sim:.3f}\n")

    # Determine reason
    if accepted:
        reason = "consensus" if per_name_counts.get(accepted, 0) >= CONSENSUS_FRAMES else "instant_accept"
    else:
        reason = "blocked_unknowns"

    return jsonify({
        "result": accepted if accepted else "Unknown",
        "label": accepted if accepted else "Unknown",
        "similarity": round(max_sim_seen, 3),
        "reason": reason,
        "image": result_img_base64,  # Base64 for immediate display
        "image_url": result_img_url   # URL to saved image in results folder
    })

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
