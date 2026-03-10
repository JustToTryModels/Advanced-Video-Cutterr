import streamlit as st
import cv2
import os
import tempfile
import subprocess
from PIL import Image

# --- PAGE CONFIG ---
st.set_page_config(page_title="Pro Video Editor: Zoom & Pan", layout="wide")
st.title("🎬 Pro Video Editor: Layout, Zoom & Pan")
st.markdown("""
Create perfect 9:16 Shorts or 16:9 Landscape videos. 
* **Trim Only:** 100% Lossless stream copy.
* **Layout/Zoom/Pan:** Re-encoded with visually lossless quality (CRF 17).
""")

# Initialize session state for preview
if 'preview_video' not in st.session_state:
    st.session_state['preview_video'] = None

# --- HELPER FUNCTIONS ---
def get_video_info(video_path):
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps > 0 else 0
    cap.release()
    return width, height, fps, duration

def extract_frame(video_path, time_in_seconds):
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, time_in_seconds * 1000)
    ret, frame = cap.read()
    cap.release()
    if ret:
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return None

def make_even(val):
    """FFmpeg requires dimensions to be divisible by 2"""
    val = int(val)
    return val if val % 2 == 0 else val + 1

def generate_preview(frame_img, w_out, h_out, zoom, pan_x_pct, pan_y_pct):
    """Generates a live WYSIWYG preview of the Zoom & Pan layout"""
    w_in, h_in = frame_img.size
    
    # Calculate scaled dimensions
    w_s, h_s = int(w_in * zoom), int(h_in * zoom)
    
    # Scale image (using fast resampling for preview)
    resized_img = frame_img.resize((w_s, h_s), Image.Resampling.LANCZOS)
    
    # Base center coordinates (centers the video on the canvas)
    x_center = (w_out - w_s) // 2
    y_center = (h_out - h_s) // 2
    
    # Apply Pan (Percentage based offset)
    # 100% pan means moving it by half its width
    x_final = int(x_center + (pan_x_pct / 100.0) * (w_s / 2))
    y_final = int(y_center + (pan_y_pct / 100.0) * (h_s / 2))
    
    # Create black canvas and paste the video frame onto it
    canvas = Image.new("RGB", (w_out, h_out), (0, 0, 0))
    canvas.paste(resized_img, (x_final, y_final))
    
    return canvas, w_s, h_s, x_final, y_final

def generate_preview_video(input_path, output_path, start_t, end_t, layout_data=None, max_duration=10):
    """Generate a quick preview video (lower quality for speed)"""
    # Limit preview duration
    preview_end = min(start_t + max_duration, end_t)
    
    if layout_data is None:
        cmd = [
            "ffmpeg", "-y", 
            "-ss", str(start_t), 
            "-to", str(preview_end), 
            "-i", input_path,
            "-c:v", "libx264",
            "-crf", "28",           # Lower quality for faster preview
            "-preset", "ultrafast", # Fastest encoding
            "-c:a", "aac",
            "-b:a", "128k",
            output_path
        ]
    else:
        w_out, h_out = make_even(layout_data['w_out']), make_even(layout_data['h_out'])
        w_s, h_s = make_even(layout_data['w_s']), make_even(layout_data['h_s'])
        x_f, y_f = layout_data['x_final'], layout_data['y_final']
        
        filter_complex = f"color=c=black:s={w_out}x{h_out} [bg]; [0:v] scale={w_s}:{h_s} [vid]; [bg][vid] overlay={x_f}:{y_f}:shortest=1"
        
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_t),
            "-to", str(preview_end),
            "-i", input_path,
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-crf", "28",           # Lower quality for faster preview
            "-preset", "ultrafast", # Fastest encoding
            "-c:a", "aac",
            "-b:a", "128k",
            output_path
        ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"FFmpeg Error: {e.stderr.decode('utf-8')}")
        return False

def process_video(input_path, output_path, start_t, end_t, layout_data=None):
    if layout_data is None:
        st.info("No Layout applied. Performing Lossless Trim...")
        cmd = [
            "ffmpeg", "-y", 
            "-ss", str(start_t), 
            "-to", str(end_t), 
            "-i", input_path,
            "-c", "copy", 
            output_path
        ]
    else:
        st.info("Layout/Zoom/Pan applied. Rendering visually lossless (CRF 17)...")
        w_out, h_out = make_even(layout_data['w_out']), make_even(layout_data['h_out'])
        w_s, h_s = make_even(layout_data['w_s']), make_even(layout_data['h_s'])
        x_f, y_f = layout_data['x_final'], layout_data['y_final']
        
        # FFmpeg Filter Graph:
        # 1. Create black background canvas of specific size
        # 2. Scale the input video by the zoom factor
        # 3. Overlay the scaled video onto the black background at X,Y pan coordinates
        filter_complex = f"color=c=black:s={w_out}x{h_out} [bg]; [0:v] scale={w_s}:{h_s} [vid]; [bg][vid] overlay={x_f}:{y_f}:shortest=1"
        
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_t),
            "-to", str(end_t),
            "-i", input_path,
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-crf", "17",        # Visually Lossless
            "-preset", "slow",   # Best compression/quality ratio
            "-c:a", "aac",
            "-b:a", "192k",
            output_path
        ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"FFmpeg Error: {e.stderr.decode('utf-8')}")
        return False

# --- MAIN APP ---
uploaded_file = st.file_uploader("Upload Video (MP4, MOV, MKV)", type=["mp4", "mov", "mkv"])

if uploaded_file:
    temp_dir = tempfile.gettempdir()
    input_path = os.path.join(temp_dir, f"in_{uploaded_file.name}")
    output_path = os.path.join(temp_dir, f"out_{uploaded_file.name}")
    preview_video_path = os.path.join(temp_dir, f"preview_{uploaded_file.name}")
    
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    orig_w, orig_h, fps, duration = get_video_info(input_path)
    st.success(f"Loaded! Resolution: {orig_w}x{orig_h} | Duration: {duration:.2f}s")

    # --- TRIM CONTROLS ---
    st.markdown("### 1. Trim Video")
    start_t, end_t = st.slider("Select Start and End Time (Seconds)", 
                               0.0, duration, (0.0, duration), step=0.1)

    # --- LAYOUT & ZOOM/PAN CONTROLS ---
    st.markdown("### 2. Layout, Zoom & Pan")
    enable_layout = st.checkbox("Enable Layout Edits (Zoom/Pan/Aspect Ratio)", value=False)
    
    layout_data = None
    
    if enable_layout:
        col_ui, col_preview = st.columns([1, 1.5])
        
        with col_ui:
            # 1. Canvas Resolution
            aspect_choice = st.selectbox("Target Layout (Canvas Size)", [
                "9:16 (Shorts/Reels/TikTok) - 1080x1920",
                "16:9 (YouTube) - 1920x1080",
                "1:1 (Square) - 1080x1080",
                "Keep Original Dimensions"
            ])
            
            if "9:16" in aspect_choice:
                w_out, h_out = 1080, 1920
            elif "16:9" in aspect_choice:
                w_out, h_out = 1920, 1080
            elif "1:1" in aspect_choice:
                w_out, h_out = 1080, 1080
            else:
                w_out, h_out = orig_w, orig_h

            # Calculate a "Fill" zoom default so the video covers the whole canvas initially
            fill_zoom = max(w_out / orig_w, h_out / orig_h)

            st.markdown("---")
            # 2. Zoom & Pan Sliders
            zoom = st.slider("🔍 Zoom (Scale)", min_value=0.1, max_value=5.0, value=float(fill_zoom), step=0.05)
            pan_x = st.slider("↔️ Pan Horizontal (%)", min_value=-100, max_value=100, value=0, step=1)
            pan_y = st.slider("↕️ Pan Vertical (%)", min_value=-100, max_value=100, value=0, step=1)
            
            st.markdown("---")
            preview_time = st.slider("Preview Frame Time", min_value=start_t, max_value=end_t, value=start_t, step=0.1)
        
        with col_preview:
            frame_img = extract_frame(input_path, preview_time)
            if frame_img:
                # Generate live preview
                preview_canvas, final_w_s, final_h_s, final_x, final_y = generate_preview(
                    frame_img, w_out, h_out, zoom, pan_x, pan_y
                )
                
                st.image(preview_canvas, caption=f"Live Frame Preview ({w_out}x{h_out})", use_column_width=True)
                
                # Save math for FFmpeg
                layout_data = {
                    'w_out': w_out, 'h_out': h_out,
                    'w_s': final_w_s, 'h_s': final_h_s,
                    'x_final': final_x, 'y_final': final_y
                }

    # --- VIDEO PREVIEW SECTION ---
    st.markdown("---")
    st.markdown("### 3. Preview Video")
    st.markdown("Generate a quick preview video to see how your trimmed/edited video looks in motion before final processing.")
    
    col_prev1, col_prev2 = st.columns([1, 2])
    
    with col_prev1:
        # Calculate max preview duration based on trim selection
        max_preview_dur = min(30, int(end_t - start_t)) if end_t > start_t else 1
        preview_duration = st.slider(
            "Preview Duration (seconds)", 
            min_value=1, 
            max_value=max(1, max_preview_dur), 
            value=min(10, max(1, max_preview_dur)), 
            step=1,
            help="Length of preview video to generate"
        )
        
        if st.button("🎥 Generate Preview", use_container_width=True):
            with st.spinner("Generating preview video (fast encoding)..."):
                success = generate_preview_video(
                    input_path, preview_video_path, 
                    start_t, end_t, layout_data, preview_duration
                )
                if success:
                    with open(preview_video_path, "rb") as f:
                        st.session_state['preview_video'] = f.read()
                    st.success("Preview generated!")
                    # Clean up temp preview file
                    try:
                        os.remove(preview_video_path)
                    except:
                        pass
    
    with col_prev2:
        # Display preview video if available
        if st.session_state['preview_video'] is not None:
            st.video(st.session_state['preview_video'])
            st.caption(f"📹 Preview: First {preview_duration} seconds (lower quality for speed)")
        else:
            st.info("👆 Click 'Generate Preview' to see how your video will look")

    # --- PROCESS & DOWNLOAD ---
    st.markdown("---")
    st.markdown("### 4. Process & Download")
    if st.button("🚀 Process Full Video (High Quality)", use_container_width=True, type="primary"):
        with st.spinner("Processing full video with high quality settings..."):
            
            success = process_video(input_path, output_path, start_t, end_t, layout_data)

            if success:
                st.success("✅ Complete! Quality retained.")
                with open(output_path, "rb") as file:
                    video_bytes = file.read()
                    st.video(video_bytes)
                    st.download_button(
                        label="⬇️ Download Output Video",
                        data=video_bytes,
                        file_name=f"edited_{uploaded_file.name}",
                        mime="video/mp4",
                        use_container_width=True
                    )
                try:
                    os.remove(output_path)
                except:
                    pass
