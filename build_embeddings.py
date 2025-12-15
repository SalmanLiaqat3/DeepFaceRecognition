import os, cv2, pickle, numpy as np
from keras_facenet import FaceNet

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "users")
OUT_PKL = os.path.join(BASE_DIR, "data", "embeddings_facenet.pkl")

embedder = FaceNet()

means = {}
raw = {}

for person in os.listdir(DATA_DIR):
    person_dir = os.path.join(DATA_DIR, person)
    if not os.path.isdir(person_dir):
        continue

    embeddings = []
    for img_name in os.listdir(person_dir):
        if img_name.lower().endswith((".jpg", ".png", ".jpeg")):
            img_path = os.path.join(person_dir, img_name)
            img = cv2.imread(img_path)
            if img is None:
                continue

            img = cv2.resize(img, (160,160))
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            emb = embedder.embeddings([rgb])[0]
            emb /= (np.linalg.norm(emb) + 1e-10)
            embeddings.append(emb)

    if len(embeddings) == 0:
        continue

    raw[person] = np.vstack(embeddings)
    mean = np.mean(raw[person], axis=0)
    means[person] = mean / (np.linalg.norm(mean) + 1e-10)

    print(f"Built embeddings for {person}: {len(embeddings)} images")

pickle.dump({"raw": raw, "mean": means}, open(OUT_PKL, "wb"))
print("Saved embeddings to:", OUT_PKL)
