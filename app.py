import streamlit as st
import streamlit.components.v1 as components
import cv2
import os
import tempfile
import subprocess
import base64

# --- PAGE CONFIG ---
st.set_page_config(page_title="Pro Video Editor", layout="wide")
st.title("🎬 Interactive Pro Video Editor")
st.markdown("""
* **Pure Trimming:** 100% Mathematically Lossless (`-c copy`).
* **Interactive Layout/Zoom:** Drag to Pan, Drag corners to Zoom! Uses visually lossless Re-encoding (`CRF-17`).
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

def extract_frame_base64(video_path, time_in_seconds):
    """Extract a frame and convert to Base64 to send to our HTML5 Canvas UI"""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, time_in_seconds * 1000)
    ret, frame = cap.read()
    cap.release()
    if ret:
        # Encode as JPEG to keep UI fast
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode('utf-8')
    return None

def make_even(val):
    """FFmpeg requires output dimensions to be divisible by 2"""
    val = int(val)
    return val if val % 2 == 0 else val + 1

# --- THE INTERACTIVE UI COMPONENT (Fabric.js) ---
def st_interactive_canvas(b64_image, target_w, target_h, key):
    """Injects a Fabric.js canvas allowing mobile-style Touch/Mouse Drag & Zoom"""
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/streamlit-component-lib@1.3.0/dist/streamlit.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/fabric.min.js"></script>
        <style>
            body {{ margin: 0; display: flex; justify-content: center; align-items: center; background: #1E1E1E; padding: 20px; touch-action: none; }}
            .canvas-container {{ box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 2px solid #333; }}
        </style>
    </head>
    <body>
        <canvas id="c"></canvas>
        <script>
            function init() {{
                Streamlit.setComponentReady();
                
                const targetW = {target_w};
                const targetH = {target_h};
                
                // Scale down the UI workspace so it fits nicely on screen
                const maxUIHeight = 500;
                const uiScale = Math.min(maxUIHeight / targetH, window.innerWidth * 0.8 / targetW);
                
                const canvas = new fabric.Canvas('c', {{
                    width: targetW * uiScale,
                    height: targetH * uiScale,
                    backgroundColor: '#000000'
                }});

                Streamlit.setFrameHeight(maxUIHeight + 40);

                fabric.Image.fromURL('data:image/jpeg;base64,{b64_image}', function(img) {{
                    // Auto-fill canvas initially
                    const scaleX = targetW / img.width;
                    const scaleY = targetH / img.height;
                    const initialScale = Math.max(scaleX, scaleY) * uiScale;

                    img.set({{
                        left: (canvas.width - img.width * initialScale) / 2,
                        top: (canvas.height - img.height * initialScale) / 2,
                        scaleX: initialScale,
                        scaleY: initialScale,
                        borderColor: '#FF4B4B',
                        cornerColor: '#FF4B4B',
                        cornerSize: 15,
                        transparentCorners: false
                    }});
                    
                    img.setControlsVisibility({{ mtr: false }}); // Disable rotation
                    
                    canvas.add(img);
                    canvas.setActiveObject(img);

                    function sendData() {{
                        // Send TRUE math back to Streamlit (ignoring the UI scale down)
                        const data = {{
                            scale: img.scaleX / uiScale,
                            left: img.left / uiScale,
                            top: img.top / uiScale
                        }};
                        Streamlit.setComponentValue(data);
                    }}

                    canvas.on('object:modified', sendData);
                    sendData(); // Send initial state immediately
                }});
            }}
            window.onload = init;
        </script>
    </body>
    </html>
    """
    return components.html(html_code, height=560)


def process_video(input_path, output_path, start_t, end_t, layout_data=None, orig_w=None, orig_h=None, target_w=None, target_h=None):
    if layout_data is None:
        st.info("No Layout applied. Performing Lossless Trim (Instant & 0% Quality Loss)...")
        cmd = [
            "ffmpeg", "-y", 
            "-ss", str(start_t), 
            "-to", str(end_t), 
            "-i", input_path,
            "-c", "copy", # 100% copy
            output_path
        ]
    else:
        st.info("Layout Edited. Re-encoding with Visually Lossless Quality (CRF 17)...")
        
        # Extract Math from Javascript
        scale = layout_data['scale']
        x_offset = int(layout_data['left'])
        y_offset = int(layout_data['top'])
        
        w_out = make_even(target_w)
        h_out = make_even(target_h)
        
        # Scaled video dimensions
        s_w = make_even(orig_w * scale)
        s_h = make_even(orig_h * scale)
        
        # FFmpeg Filter Graph:
        # 1. Create Black Canvas
        # 2. Scale Video
        # 3. Overlay Video onto Canvas at exact X/Y coordinates dragged by the user
        filter_complex = f"color=c=black:s={w_out}x{h_out} [bg]; [0:v] scale={s_w}:{s_h} [vid]; [bg][vid] overlay={x_offset}:{y_offset}:shortest=1"
        
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_t),
            "-to", str(end_t),
            "-i", input_path,
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-crf", "17",        # Visually Lossless
            "-preset", "slow",   # Deep analysis to retain high quality
            "-c:a", "copy",      # Copy audio losslessly to save time
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
    
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    orig_w, orig_h, fps, duration = get_video_info(input_path)
    st.success(f"Original Resolution: {orig_w}x{orig_h} | Duration: {duration:.2f}s")

    # --- 1. TRIM ---
    st.markdown("### 1. Trim Video")
    start_t, end_t = st.slider("Select Start and End Time (Seconds)", 0.0, duration, (0.0, duration), step=0.1)

    # --- 2. LAYOUT / ZOOM / PAN ---
    st.markdown("### 2. Layout & Framing")
    enable_layout = st.checkbox("Enable Layout Edit (Drag & Zoom)", value=False)
    
    js_data = None
    target_w, target_h = orig_w, orig_h

    if enable_layout:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            aspect_choice = st.selectbox("Select Target Layout", [
                "9:16 (Shorts/Reels) - 1080x1920",
                "16:9 (YouTube) - 1920x1080",
                "1:1 (Square) - 1080x1080",
                "Custom Dimensions"
            ])
            
            if "9:16" in aspect_choice:
                target_w, target_h = 1080, 1920
            elif "16:9" in aspect_choice:
                target_w, target_h = 1920, 1080
            elif "1:1" in aspect_choice:
                target_w, target_h = 1080, 1080
            else:
                cust_w = st.number_input("Width", min_value=100, max_value=4000, value=1080)
                cust_h = st.number_input("Height", min_value=100, max_value=4000, value=1920)
                target_w, target_h = cust_w, cust_h

            st.markdown("---")
            preview_time = st.slider("Select Frame to align layout:", min_value=start_t, max_value=end_t, value=start_t, step=0.1)
            st.info("👉 Use your Mouse (PC) or Finger (Mobile) to drag the image around. Drag the corners of the red box to Zoom.")

        with col2:
            b64_img = extract_frame_base64(input_path, preview_time)
            if b64_img:
                # The component returns a dict: {"scale": X, "left": Y, "top": Z}
                js_data = st_interactive_canvas(b64_img, target_w, target_h, key=f"canvas_{target_w}_{target_h}_{preview_time}")

    # --- PROCESS ---
    st.markdown("---")
    if st.button("🚀 Process Final Video", use_container_width=True, type="primary"):
        with st.spinner("Processing... ensuring zero quality drop."):
            
            success = process_video(
                input_path, output_path, start_t, end_t, 
                layout_data=js_data if enable_layout else None,
                orig_w=orig_w, orig_h=orig_h, target_w=target_w, target_h=target_h
            )

            if success:
                st.success("✅ Complete!")
                with open(output_path, "rb") as file:
                    video_bytes = file.read()
                    st.video(video_bytes)
                    st.download_button("⬇️ Download Final Video", data=video_bytes, file_name=f"edited_{uploaded_file.name}", mime="video/mp4", use_container_width=True)
                
                try: os.remove(output_path)
                except: pass
