/* SECTION SWITCH */
function showSection(id) {
  document.querySelectorAll('.card').forEach(section => {
    section.classList.remove('active');
  });

  document.getElementById(id).classList.add('active');
}

/* ---------------- ADD USER AUTO-CAPTURE ---------------- */
let addStream = null;
let addCount = 0;
let addInterval = null;
const MAX_IMAGES = 30;

async function startAddUser() {
  const name = document.getElementById("userName").value.trim();
  if (!name) {
    alert("Enter a name first");
    return;
  }

  // Stop any existing capture
  if (addInterval) {
    clearInterval(addInterval);
    addInterval = null;
  }

  // Stop any existing stream
  if (addStream) {
    addStream.getTracks().forEach(t => t.stop());
    addStream = null;
  }

  addCount = 0;
  document.getElementById("addStatus").innerText = "Starting capture. Hold still...";

  const video = document.getElementById("addVideo");
  const box = document.getElementById("videoBox");

  box.classList.add("waiting");

  addStream = await navigator.mediaDevices.getUserMedia({ video: true });
  video.srcObject = addStream;

  await video.play();

  // CAMERA IS ON
  video.classList.remove("camera-off");
  box.classList.remove("waiting");
  box.classList.add("active");

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");

  addInterval = setInterval(() => {
    if (!video || !video.videoWidth) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0);

    const frame = canvas.toDataURL("image/jpeg", 0.9);

    const formData = new FormData();
    formData.append("name", name);
    formData.append("frame", frame);

    fetch("/add_user_frame", {
      method: "POST",
      body: formData
    })
    .then(res => res.json())
    .then(data => {
      if (data.saved) {
        addCount++;
        document.getElementById("addStatus").innerText =
          `Captured ${addCount}/${MAX_IMAGES}`;

        // Show finalize button after 20+ images
        if (addCount >= 20) {
          const finalizeBtn = document.getElementById("finalizeBtn");
          if (finalizeBtn) {
            finalizeBtn.style.display = "block";
          }
        }

        if (addCount >= MAX_IMAGES) {
          stopAddUser();
        }
      }
    })
    .catch(err => {
      console.error("Capture error:", err);
    });

  }, 300); // ~3 frames/sec (similar to Colab)
}

function stopAddUser() {
  if (addInterval) {
    clearInterval(addInterval);
    addInterval = null;
  }

  const video = document.getElementById("addVideo");
  const box = document.getElementById("videoBox");

  if (addStream) {
    addStream.getTracks().forEach(t => t.stop());
    addStream = null;
  }

  if (video) {
    video.srcObject = null;
  }

  // CAMERA OFF
  video.classList.add("camera-off");
  box.classList.remove("active");
  box.classList.add("waiting");

  document.getElementById("addStatus").innerText =
    "Capture complete. 30 images saved. Click 'Finalize User & Train Model' to update the recognition model.";

  // Show the finalize button after capture completes
  const finalizeBtn = document.getElementById("finalizeBtn");
  if (finalizeBtn) {
    finalizeBtn.style.display = "block";
  }

  // Clear the input field after successful capture
  const userNameInput = document.getElementById("userName");
  if (userNameInput) {
    userNameInput.value = "";
  }

  alert("Capture complete. Camera stopped.");
}

/* ---------------- REBUILD EMBEDDINGS ---------------- */
function rebuildEmbeddings() {
  const status = document.getElementById("trainStatus");
  const finalizeBtn = document.getElementById("finalizeBtn");
  
  if (finalizeBtn) {
    finalizeBtn.disabled = true;
    finalizeBtn.innerText = "Training...";
  }
  
  status.innerText = "Training model... please wait ⏳";

  fetch("/rebuild_embeddings", {
    method: "POST"
  })
  .then(res => res.json())
  .then(data => {
    if (data.status === "success") {
      status.innerText =
        "Model updated successfully ✅\nUsers: " + data.users.join(", ");
      if (finalizeBtn) {
        finalizeBtn.style.display = "none";
      }
      // Clear input field after successful rebuild
      const userNameInput = document.getElementById("userName");
      if (userNameInput) {
        userNameInput.value = "";
      }
      // Clear status message after a delay
      setTimeout(() => {
        document.getElementById("addStatus").innerText = "";
      }, 3000);
    } else {
      status.innerText = "Training failed ❌: " + (data.message || "Unknown error");
      if (finalizeBtn) {
        finalizeBtn.disabled = false;
        finalizeBtn.innerText = "Finalize User & Train Model";
      }
    }
  })
  .catch(err => {
    status.innerText = "Server error ❌: " + err.message;
    if (finalizeBtn) {
      finalizeBtn.disabled = false;
      finalizeBtn.innerText = "Finalize User & Train Model";
    }
  });
}

/* CAPTURE FRAME (for recognition) */
function captureFrame(video) {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  return canvas.toDataURL("image/jpeg", 0.9);
}

/* ---------------- RECOGNITION CAMERA ---------------- */
let videoStream = null;
let video = null;
let capturedFrames = [];
let captureTimer = null;

/* ---------------- START RECOGNITION CAMERA ---------------- */
async function startCamera() {
  video = document.getElementById("videoRec");
  const box = document.getElementById("videoRecBox");
  if (!video) return;

  // Stop any existing stream first
  stopCamera();

  if (box) box.classList.add("waiting");

  videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
  video.srcObject = videoStream;
  await video.play();

  // CAMERA IS ON
  video.classList.remove("camera-off");
  if (box) {
    box.classList.remove("waiting");
    box.classList.add("active");
  }
}

/* ---------------- STOP RECOGNITION CAMERA (CRITICAL FIX) ---------------- */
function stopCamera() {
  const box = document.getElementById("videoRecBox");

  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
    videoStream = null;
  }

  if (video) {
    video.srcObject = null;
    // CAMERA OFF
    video.classList.add("camera-off");
  }

  if (box) {
    box.classList.remove("active");
    box.classList.add("waiting");
  }

  if (captureTimer) {
    clearInterval(captureTimer);
    captureTimer = null;
  }
}

/* ---------------- CAPTURE MULTIPLE FRAMES ---------------- */
/* Colab equivalent: RUN_SECONDS = 3, CAPTURE_INTERVAL = 0.18 */
const RUN_SECONDS = 3;
const CAPTURE_INTERVAL = 180; // 180ms = 0.18 seconds

function captureFrames() {
  capturedFrames = [];

  if (!video || !video.videoWidth) {
    document.getElementById("result").innerText = "Camera not ready";
    return;
  }

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");

  // Capture frame every 180ms (matches Colab CAPTURE_INTERVAL)
  captureTimer = setInterval(() => {
    if (!video || !video.videoWidth) return;
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0);

    capturedFrames.push(
      canvas.toDataURL("image/jpeg", 0.9)
    );
  }, CAPTURE_INTERVAL);

  // Stop after 3 seconds
  setTimeout(() => {
    clearInterval(captureTimer);
    captureTimer = null;
    stopCamera();          // ✅ camera turns OFF here
    sendFrames();
  }, RUN_SECONDS * 1000);
}

/* ---------------- SEND FRAMES TO BACKEND ---------------- */
function sendFrames() {
  const resultEl = document.getElementById("result");
  const outputImg = document.getElementById("outputImg");

  if (capturedFrames.length === 0) {
    resultEl.innerText = "No frames captured";
    return;
  }

  resultEl.innerText = "Processing...";

  fetch("/recognize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(capturedFrames)
  })
  .then(res => res.json())
  .then(data => {
    // Display result text
    if (data.result && data.result !== "Unknown") {
      resultEl.innerText = 
        `Result: ${data.result} | Similarity: ${data.similarity.toFixed(3)} | Reason: ${data.reason}`;
    } else {
      resultEl.innerText = `Result: ${data.result || "Unknown"} | Reason: ${data.reason}`;
    }

    // Display annotated image with bounding box
    if (outputImg) {
      // Style the output image
      outputImg.style.width = "100%";
      outputImg.style.borderRadius = "10px";
      outputImg.style.marginTop = "10px";
      
      // Prefer saved image URL, fallback to base64
      if (data.image_url) {
        outputImg.src = data.image_url + "?t=" + new Date().getTime();
        outputImg.style.display = "block";
      } else if (data.image) {
        outputImg.src = data.image;
        outputImg.style.display = "block";
      }
    }
  })
  .catch(err => {
    resultEl.innerText = "Recognition failed";
    console.error(err);
  });
}

/* ---------------- MAIN RECOGNITION BUTTON ---------------- */
async function runRecognition() {
  const resultEl = document.getElementById("result");
  resultEl.innerText = "Starting camera...";
  
  await startCamera();
  
  resultEl.innerText = "Capturing frames for 3 seconds...";
  captureFrames(); // 3 seconds, every 180ms
}

/* START RECOGNITION - Keep for backward compatibility */
async function startRecognition() {
  return runRecognition();
}

/* AUTO START - No auto-start for add user, starts on button click */
window.onload = () => {
  // Cameras start on demand
};
