# Cài trước: pip install pyrender trimesh pillow numpy opengl-py
import trimesh
import pyrender
import numpy as np
from PIL import Image
import os

PREVIEW_DIR = "D:/Web/bed_previews_rendered"
os.makedirs(PREVIEW_DIR, exist_ok=True)

def render_glb_preview(glb_path, output_path, width=800, height=600):
    mesh = trimesh.load(glb_path, force='mesh')
    
    # Tạo scene
    scene = pyrender.Scene()
    mesh_py = pyrender.Mesh.from_trimesh(mesh, smooth=False)
    scene.add(mesh_py)
    
    # Đặt camera (góc 30 độ, zoom đẹp cho giường)
    camera = pyrender.PerspectiveCamera(yfov=np.pi / 6.0, aspectRatio=width/height)
    camera_pose = np.array([
        [1.0,  0.0,  0.0,  0.0],
        [0.0,  0.866, 0.5,  2.5],   # góc 30 độ + lùi xa
        [0.0, -0.5,  0.866, 1.8],   # nâng cao tí để nhìn giường đẹp
        [0.0,  0.0,  0.0,  1.0]
    ])
    scene.add(camera, pose=camera_pose)
    
    # Ánh sáng
    light = pyrender.SpotLight(color=np.ones(3), intensity=3.0)
    scene.add(light, pose=camera_pose)
    
    # Render
    r = pyrender.OffscreenRenderer(width, height)
    color, _ = r.render(scene)
    r.delete()
    
    # Lưu ảnh
    img = Image.fromarray(color)
    img.save(output_path)

# Ví dụ render 1 file
glb_path = "D:\Web\bed_models\glbs\000-000\03fa59009cb344ee9241128bad9bba13.glb"
render_glb_preview(glb_path, "test_preview.png")