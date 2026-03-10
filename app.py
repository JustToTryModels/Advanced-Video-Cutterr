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
    val = int(val)
    return val if val % 2 == 0 else val + 1

# --- TIME FORMATTING HELPERS ---
def sec_to_hhmmss(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def hhmmss_to_sec(time_str):
    try:
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split('.')
        s = int(s_parts[0])
        ms = int(s_parts[1]) if len(s_parts) > 1 else 0
        return h * 3600 + m * 60 + s + ms / 1000.0
    except:
        return -1 # Invalid format

# --- UI SYNC HELPERS ---
def sync_state(key_from, key_to):
    """Synchronizes slider and number input states"""
    st.session_state[key_to] = st.session_state[key_from]

def render_synced_slider_number(label, min_v, max_v, default_v, step_v, base_key, is_int=False):
    """Renders a slider with a perfectly synced manual number input next to it"""
    sl_key = f"{base_key}_sl"
    num_key = f"{base_key}_num"

    if sl_key not in st.session_state: st.session_state[sl_key] = default_v
    if num_key not in st.session_state: st.session_state[num_key] = default_v

    # Clamp bounds dynamically
    if st.session_state[sl_key] > max_v: st.session_state[sl_key] = max_v
    if st.session_state[sl_key] < min_v: st.session_state[sl_key] = min_v
    st.session_state[num_key] = st.session_state[sl_key]

    col1, col2 = st.columns([4, 1])
    with col1:
        st.slider(label, min_value=min_v, max_value=max_v, step=step_v, key=sl_key, on_change=sync_state, args=(sl_key, num_key))
    with col2:
        # Align with slider
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if is_int:
            st.number_input(label, min_value=int(min_v), max_value=int(max_v), step=int(step_v), key=num_key, on_change=sync_state, args=(num_key, sl_key), label_visibility="collapsed")
        else:
            st.number_input(label, min_value=float(min_v), max_value=float(max_v), step=float(step_v), key=num_key, on_change=sync_state, args=(num_key, sl_key), label_visibility="collapsed")
    
    return st.session_state[sl_key]

# --- PREVIEW AND PROCESS ---
def generate_preview(frame_img, w_out, h_out, zoom, pan_x_pct, pan_y_pct):
    w_in, h_in = frame_img.size
    w_s, h_s = int(w_in * zoom), int(h_in * zoom)
    resized_img = frame_img.resize((w_s, h_s), Image.Resampling.LANCZOS)
    x_center = (w_out - w_s) // 2
    y_center = (h_out - h_s) // 2
    x_final = int(x_center + (pan_x_pct / 100.0) * (w_s / 2))
    y_final = int(y_center + (pan_y_pct / 100.0) * (h_s / 2))
    canvas = Image.new("RGB", (w_out, h_out), (0, 0, 0))
    canvas.paste(resized_img, (x_final, y_final))
    return canvas, w_s, h_s, x_final, y_final

def process_video(input_path, output_path, start_t, end_t, layout_data=None):
    if layout_data is None:
        st.info("No Layout applied. Performing Lossless Trim...")
        cmd = ["ffmpeg", "-y", "-ss", str(start_t), "-to", str(end_t), "-i", input_path, "-c", "copy", output_path]
    else:
        st.info("Layout/Zoom/Pan applied. Rendering visually lossless (CRF 17)...")
        w_out, h_out = make_even(layout_data['w_out']), make_even(layout_data['h_out'])
        w_s, h_s = make_even(layout_data['w_s']), make_even(layout_data['h_s'])
        x_f, y_f = layout_data['x_final'], layout_data['y_final']
        
        filter_complex = f"color=c=black:s={w_out}x{h_out} [bg]; [0:v] scale={w_s}:{h_s} [vid]; [bg][vid] overlay={x_f}:{y_f}:shortest=1"
        
        cmd = [
            "ffmpeg", "-y", "-ss", str(start_t), "-to", str(end_t), "-i", input_path,
            "-filter_complex", filter_complex, "-c:v", "libx264", "-crf", "17", "-preset", "slow",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", output_path
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
    # Reset Session State entirely if a NEW video is uploaded to prevent caching errors
    if "last_filename" not in st.session_state or st.session_state.last_filename != uploaded_file.name:
        st.session_state.clear()
        st.session_state.last_filename = uploaded_file.name

    temp_dir = tempfile.gettempdir()
    input_path = os.path.join(temp_dir, f"in_{uploaded_file.name}")
    output_path = os.path.join(temp_dir, f"out_{uploaded_file.name}")
    
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    orig_w, orig_h, fps, duration = get_video_info(input_path)
    st.success(f"Loaded! Resolution: {orig_w}x{orig_h} | Duration: {duration:.2f}s")

    # --- TRIM CONTROLS ---
    st.markdown("### 1. Trim Video")
    
    # Initialize Trim State
    if "trim_sl" not in st.session_state:
        st.session_state.trim_sl = (0.0, duration)
        st.session_state.trim_st_num = sec_to_hhmmss(0.0)
        st.session_state.trim_end_num = sec_to_hhmmss(duration)

    def sync_trim_slider():
        st.session_state.trim_st_num = sec_to_hhmmss(st.session_state.trim_sl[0])
        st.session_state.trim_end_num = sec_to_hhmmss(st.session_state.trim_sl[1])
        
    def sync_trim_num():
        st_sec = hhmmss_to_sec(st.session_state.trim_st_num)
        end_sec = hhmmss_to_sec(st.session_state.trim_end_num)
        # Validate input
        if st_sec != -1 and end_sec != -1 and 0 <= st_sec < end_sec <= duration:
            st.session_state.trim_sl = (st_sec, end_sec)
        else: # Revert to valid if user types nonsense
            st.session_state.trim_st_num = sec_to_hhmmss(st.session_state.trim_sl[0])
            st.session_state.trim_end_num = sec_to_hhmmss(st.session_state.trim_sl[1])

    st.slider("Select Range", 0.0, duration, step=0.1, key="trim_sl", on_change=sync_trim_slider)
    
    t_col1, t_col2 = st.columns(2)
    with t_col1: st.text_input("Start Time (HH:MM:SS.mmm)", key="trim_st_num", on_change=sync_trim_num)
    with t_col2: st.text_input("End Time (HH:MM:SS.mmm)", key="trim_end_num", on_change=sync_trim_num)
    
    start_t, end_t = st.session_state.trim_sl

    # --- LAYOUT & ZOOM/PAN CONTROLS ---
    st.markdown("### 2. Layout, Zoom & Pan")
    enable_layout = st.checkbox("Enable Layout Edits (Zoom/Pan/Aspect Ratio)", value=False)
    
    layout_data = None
    
    if enable_layout:
        col_ui, col_preview = st.columns([1.2, 1])
        
        with col_ui:
            aspect_choice = st.selectbox("Target Layout (Canvas Size)", [
                "9:16 (Shorts/Reels/TikTok) - 1080x1920",
                "16:9 (YouTube) - 1920x1080",
                "1:1 (Square) - 1080x1080",
                "Keep Original Dimensions"
            ])
            
            if "9:16" in aspect_choice: w_out, h_out = 1080, 1920
            elif "16:9" in aspect_choice: w_out, h_out = 1920, 1080
            elif "1:1" in aspect_choice: w_out, h_out = 1080, 1080
            else: w_out, h_out = orig_w, orig_h

            fill_zoom = max(w_out / orig_w, h_out / orig_h)
            
            # Reset Zoom/Pan if layout changes
            if "last_aspect" not in st.session_state or st.session_state.last_aspect != aspect_choice:
                st.session_state.last_aspect = aspect_choice
                st.session_state.zoom_sl = float(fill_zoom)
                st.session_state.zoom_num = float(fill_zoom)
                st.session_state.panx_sl = 0
                st.session_state.panx_num = 0
                st.session_state.pany_sl = 0
                st.session_state.pany_num = 0

            st.markdown("---")
            # Using our custom synchronized inputs
            zoom = render_synced_slider_number("🔍 Zoom (Scale)", 0.1, 5.0, float(fill_zoom), 0.05, "zoom")
            pan_x = render_synced_slider_number("↔️ Pan Horizontal (%)", -100, 100, 0, 1, "panx", is_int=True)
            pan_y = render_synced_slider_number("↕️ Pan Vertical (%)", -100, 100, 0, 1, "pany", is_int=True)
            
            st.markdown("---")
            preview_time = render_synced_slider_number("Preview Frame Time", start_t, end_t, start_t, 0.1, "prev")
        
        with col_preview:
            frame_img = extract_frame(input_path, preview_time)
            if frame_img:
                preview_canvas, final_w_s, final_h_s, final_x, final_y = generate_preview(frame_img, w_out, h_out, zoom, pan_x, pan_y)
                st.image(preview_canvas, caption=f"Live Preview ({w_out}x{h_out})", use_column_width=True)
                
                layout_data = {
                    'w_out': w_out, 'h_out': h_out,
                    'w_s': final_w_s, 'h_s': final_h_s,
                    'x_final': final_x, 'y_final': final_y
                }

    # --- PROCESS ---
    st.markdown("---")
    if st.button("🚀 Process Video", use_container_width=True, type="primary"):
        with st.spinner("Processing in background..."):
            
            success = process_video(input_path, output_path, start_t, end_t, layout_data)

            if success:
                st.success("✅ Complete! Quality retained.")
                
                st.markdown("### 🎬 Preview Final Video")
                st.info("Watch your trimmed and zoomed video below before downloading.")
                
                with open(output_path, "rb") as file:
                    video_bytes = file.read()
                    
                    st.video(video_bytes)
                    
                    st.markdown("---")
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
