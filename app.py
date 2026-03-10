import streamlit as st
import cv2
import numpy as np
import subprocess
import tempfile
import os
import json
from pathlib import Path

st.set_page_config(page_title="Pro Video Cutter & Reframer", layout="wide")
st.title("🎬 Pro Video Cutter & Smart Reframer")
st.markdown("**Trim • Change aspect ratio • Zoom & Pan • Maximum quality**")

# ========================= SESSION STATE =========================
if "input_path" not in st.session_state:
    st.session_state.input_path = None
if "orig_w" not in st.session_state:
    st.session_state.orig_w = None
if "orig_h" not in st.session_state:
    st.session_state.orig_h = None
if "duration" not in st.session_state:
    st.session_state.duration = None
if "fps" not in st.session_state:
    st.session_state.fps = None
if "preview_frame" not in st.session_state:
    st.session_state.preview_frame = None

# ========================= HELPERS =========================
def get_video_metadata(video_path: str):
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)

    for stream in data['streams']:
        if stream['codec_type'] == 'video':
            return {
                'width': int(stream['width']),
                'height': int(stream['height']),
                'duration': float(data['format']['duration']),
                'fps': eval(stream.get('r_frame_rate', '30/1'))
            }
    return None


def extract_preview_frame(video_path: str, time_sec: float):
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000)
    ret, frame = cap.read()
    cap.release()
    if ret:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return None


def calculate_crop_params(orig_w, orig_h, target_ratio, zoom, h_shift, v_shift):
    # Base crop (maximum area with target aspect ratio)
    if orig_w / orig_h > target_ratio:
        base_h = orig_h
        base_w = int(base_h * target_ratio)
    else:
        base_w = orig_w
        base_h = int(base_w / target_ratio)

    # Apply zoom
    crop_w = int(base_w / zoom)
    crop_h = int(base_h / zoom)

    # Clamp
    crop_w = min(crop_w, orig_w)
    crop_h = min(crop_h, orig_h)

    # Center + shift
    max_offset_x = (orig_w - crop_w) / 2
    max_offset_y = (orig_h - crop_h) / 2

    offset_x = h_shift * max_offset_x
    offset_y = v_shift * max_offset_y

    crop_x = int((orig_w - crop_w) / 2 + offset_x)
    crop_y = int((orig_h - crop_h) / 2 + offset_y)

    return crop_x, crop_y, crop_w, crop_h


# ========================= MAIN APP =========================
uploaded_file = st.file_uploader("Upload video (MP4, MOV, AVI, MKV)", 
                                type=['mp4', 'mov', 'avi', 'mkv', 'webm'])

if uploaded_file:
    # Save uploaded file
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        st.session_state.input_path = tmp.name

    # Get metadata
    meta = get_video_metadata(st.session_state.input_path)
    if meta:
        st.session_state.orig_w = meta['width']
        st.session_state.orig_h = meta['height']
        st.session_state.duration = meta['duration']
        st.session_state.fps = meta['fps']

    st.success(f"Loaded: {st.session_state.orig_w}×{st.session_state.orig_h} | "
               f"{st.session_state.duration:.1f}s | {st.session_state.fps:.2f} fps")

    # Original video
    st.video(st.session_state.input_path)

    # ===================== CONTROLS =====================
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("1. Trim")
        start_time = st.slider("Start Time (s)", 0.0, st.session_state.duration, 0.0, 0.01)
        end_time = st.slider("End Time (s)", start_time, st.session_state.duration, 
                            st.session_state.duration, 0.01)

    with col2:
        st.subheader("2. Output Aspect Ratio")
        presets = {
            "16:9 (Landscape)": 16/9,
            "9:16 (Vertical/Reels)": 9/16,
            "1:1 (Square)": 1.0,
            "4:3": 4/3,
            "21:9 (Ultrawide)": 21/9,
            "9:21 (Vertical Ultrawide)": 9/21,
            "3:4": 3/4,
        }

        preset_name = st.selectbox("Preset", list(presets.keys()))
        target_ratio = presets[preset_name]

        if st.checkbox("Custom Ratio"):
            c1, c2 = st.columns(2)
            with c1:
                w = st.number_input("Width ratio", 1, 100, 16)
            with c2:
                h = st.number_input("Height ratio", 1, 100, 9)
            target_ratio = w / h

    # Output resolution
    st.subheader("3. Output Resolution")
    target_height = st.select_slider(
        "Target Height",
        options=[480, 720, 1080, 1440, 2160],
        value=1080
    )
    target_width = int(target_height * target_ratio)
    # Make dimensions even (required for many encoders)
    target_width = target_width if target_width % 2 == 0 else target_width + 1
    target_height = target_height if target_height % 2 == 0 else target_height + 1

    st.info(f"**Output resolution:** {target_width}×{target_height}")

    # ===================== FRAMING =====================
    st.subheader("4. Zoom & Pan (Framing)")

    zoom = st.slider("Zoom Level", min_value=1.0, max_value=6.0, value=1.0, step=0.05,
                    help="1.0 = maximum area, higher = more zoom")

    h_shift = st.slider("Horizontal Pan", -1.0, 1.0, 0.0, 0.01)
    v_shift = st.slider("Vertical Pan", -1.0, 1.0, 0.0, 0.01)

    # Calculate crop
    crop_x, crop_y, crop_w, crop_h = calculate_crop_params(
        st.session_state.orig_w, st.session_state.orig_h, target_ratio, zoom, h_shift, v_shift
    )

    # Preview frame (middle of trimmed section)
    preview_time = (start_time + end_time) / 2

    preview_frame = extract_preview_frame(st.session_state.input_path, preview_time)
    if preview_frame is not None:
        st.session_state.preview_frame = preview_frame

    if st.session_state.preview_frame is not None:
        frame = st.session_state.preview_frame.copy()

        # Draw crop rectangle on original
        overlay = frame.copy()
        cv2.rectangle(overlay, (crop_x, crop_y), (crop_x + crop_w, crop_y + crop_h), 
                     (0, 255, 0), 6)

        st.image(overlay, caption="Original frame with crop overlay", use_column_width=True)

        # Apply crop + resize
        cropped = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
        result = cv2.resize(cropped, (target_width, target_height), 
                          interpolation=cv2.INTER_LANCZOS4)

        st.image(result, caption="**FINAL OUTPUT PREVIEW**", use_column_width=True)

    # ===================== PROCESS =====================
    if st.button("🚀 Process Video (High Quality)", type="primary", use_container_width=True):
        if not st.session_state.input_path:
            st.error("No video loaded")
            st.stop()

        with st.spinner("Processing with maximum quality settings..."):
            output_path = tempfile.mktemp(suffix=".mp4")

            trim_duration = end_time - start_time

            # High quality ffmpeg command
            vf = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={target_width}:{target_height}:flags=lanczos"

            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_time),
                '-i', st.session_state.input_path,
                '-t', str(trim_duration),
                '-vf', vf,
                '-c:v', 'libx264',
                '-crf', '17',           # Visually lossless
                '-preset', 'slow',      # Best quality
                '-tune', 'film',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                output_path
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                st.success("✅ Processing completed!")

                with open(output_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Final Video",
                        data=f,
                        file_name="FINAL_VIDEO.mp4",
                        mime="video/mp4",
                        use_container_width=True
                    )

            except subprocess.CalledProcessError as e:
                st.error("FFmpeg error:")
                st.code(e.stderr)

            finally:
                if os.path.exists(output_path):
                    os.unlink(output_path)

# Cleanup on session end
def cleanup():
    if st.session_state.input_path and os.path.exists(st.session_state.input_path):
        try:
            os.unlink(st.session_state.input_path)
        except:
            pass

st.button("Clear & Upload New Video", on_click=cleanup)
