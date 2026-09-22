"""
Face detection service using Coral M.2 TPU on Pi5
Based on Gr1n95/Raspberry-Pi5-Edge-M.2-Coral_TPU setup
Uses BlazeFace EdgeTPU for detection + InsightFace for recognition (CPU)
"""
import time
import cv2
import numpy as np
from pathlib import Path

# Coral imports - will work if libedgetpu1-std installed
try:
    from pycoral.utils import edgetpu
    from pycoral.adapters import common, detect
    import tflite_runtime.interpreter as tflite
    CORAL_AVAILABLE = True
except ImportError:
    CORAL_AVAILABLE = False
    print("Coral not available, fallback to CPU")

# InsightFace for embedding (CPU)
try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False

class CoralFaceService:
    def __init__(self, model_dir="./coral_models", use_coral=True):
        self.use_coral = use_coral and CORAL_AVAILABLE
        self.model_dir = Path(model_dir)
        
        if self.use_coral:
            print(f"[Coral] Initializing EdgeTPU: {edgetpu.list_edge_tpus()}")
            model_path = self.model_dir / "blazeface_128x128_edgetpu.tflite"
            if not model_path.exists():
                print(f"[Coral] Model not found at {model_path}, downloading...")
                self._download_model()
            
            self.interpreter = edgetpu.make_interpreter(
                str(model_path),
                device=":0"  # pci:0 -> /dev/apex_0
            )
            self.interpreter.allocate_tensors()
            print("[Coral] BlazeFace EdgeTPU loaded, ~25ms inference")
        else:
            print("[CPU] Using InsightFace detection")
        
        if INSIGHTFACE_AVAILABLE:
            # Use buffalo_s for speed, not buffalo_l
            self.face_app = FaceAnalysis(name="buffalo_s", providers=['CPUExecutionProvider'])
            self.face_app.prepare(ctx_id=0, det_size=(320, 320))
            print("[InsightFace] buffalo_s loaded for recognition")

    def _download_model(self):
        """Download BlazeFace model for Coral if not present"""
        import urllib.request
        self.model_dir.mkdir(parents=True, exist_ok=True)
        url = "https://github.com/google-coral/test_data/raw/master/blazeface_128x128_edgetpu.tflite"
        dest = self.model_dir / "blazeface_128x128_edgetpu.tflite"
        print(f"Downloading {url} -> {dest}")
        urllib.request.urlretrieve(url, dest)

    def detect_faces_coral(self, frame):
        """Fast face detection on Coral ~25ms"""
        if not self.use_coral:
            return []
        
        start = time.time()
        # Preprocess
        input_size = 128
        resized = cv2.resize(frame, (input_size, input_size))
        # Normalize to [-1,1] if needed, BlazeFace expects 0-255
        input_tensor = np.expand_dims(resized, axis=0).astype(np.uint8)
        
        common.set_input(self.interpreter, input_tensor)
        self.interpreter.invoke()
        
        # Get boxes
        # Output format depends on model, for BlazeFace: [ymin, xmin, ymax, xmax, score]
        boxes = common.get_output(self.interpreter, 0)  # adjust index
        # Simplified parsing - real implementation needs proper parsing
        elapsed = (time.time() - start) * 1000
        print(f"[Coral] Detect: {elapsed:.1f}ms")
        return boxes

    def detect_faces_cpu(self, frame):
        """Fallback CPU detection via InsightFace"""
        if not INSIGHTFACE_AVAILABLE:
            return []
        start = time.time()
        faces = self.face_app.get(frame)
        elapsed = (time.time() - start) * 1000
        print(f"[CPU] InsightFace detect: {elapsed:.1f}ms, found {len(faces)}")
        return faces

    def get_embedding(self, face_crop):
        """Get face embedding for recognition (CPU, ~150ms)"""
        if not INSIGHTFACE_AVAILABLE:
            return None
        faces = self.face_app.get(face_crop)
        if faces:
            return faces[0].normed_embedding
        return None

    def recognize(self, frame, known_embeddings, threshold=0.45):
        """
        Full pipeline: detect (Coral) -> crop -> embedding (CPU) -> compare
        known_embeddings: dict {name: embedding}
        """
        # 1. Detect
        if self.use_coral:
            # Use Coral for fast bbox, then crop and run InsightFace for embedding
            # For simplicity, use InsightFace get which does both but we already have bbox from Coral
            faces = self.face_app.get(frame)  # TODO: use coral bboxes to crop
        else:
            faces = self.detect_faces_cpu(frame)
        
        results = []
        for face in faces:
            # face.embedding already from InsightFace
            emb = face.normed_embedding
            # Compare
            best_match = None
            best_score = 0
            for name, known_emb in known_embeddings.items():
                score = np.dot(emb, known_emb)  # cosine similarity, embeddings are normalized
                if score > best_score and score > threshold:
                    best_score = score
                    best_match = name
            
            results.append({
                "bbox": face.bbox.tolist(),
                "name": best_match,
                "score": float(best_score),
                "det_score": float(face.det_score)
            })
        return results


# Example usage for offline garage
if __name__ == "__main__":
    import sys
    service = CoralFaceService()
    
    # Test with PiCam
    # from picamera2 import Picamera2
    # picam = Picamera2()
    # picam.start()
    
    # Load known faces
    # known = np.load("faces_db.npz")
    
    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        results = service.recognize(frame, known_embeddings={})
        for r in results:
            x1,y1,x2,y2 = map(int, r["bbox"])
            cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
            cv2.putText(frame, f"{r['name']} {r['score']:.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
        
        cv2.imshow("Garage FaceID - Coral", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
