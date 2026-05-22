// Tạo scene
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf0f0f0);

// Tạo camera
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(5, 5, 5);
camera.lookAt(0, 0, 0);

// Tạo renderer 
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.getElementById('canvas-container').appendChild(renderer.domElement);

// Tạo hệ trục tọa độ Oxyz
function createAxis(length = 5, color = 0x000000) {
    const material = new THREE.LineBasicMaterial({ color: color });
    const points = [
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(length, 0, 0)
    ];
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    return new THREE.Line(geometry, material);
}

// Thêm các trục
const axisX = createAxis(5, 0xff0000); // Đỏ cho trục X
const axisY = createAxis(5, 0x00ff00); // Xanh lá cho trục Y
const axisZ = createAxis(5, 0x0000ff); // Xanh dương cho trục Z
scene.add(axisX);
scene.add(axisY);
scene.add(axisZ);

// Thêm mũi tên cho các trục
function createArrowHelper(direction, origin, length, color) {
    return new THREE.ArrowHelper(direction, origin, length, color);
}

const arrowX = createArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0), 4.5, 0xff0000);
const arrowY = createArrowHelper(new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 0), 4.5, 0x00ff00);
const arrowZ = createArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, 0), 4.5, 0x0000ff);
scene.add(arrowX);
scene.add(arrowY);
scene.add(arrowZ);

// Tạo lưới (grid)
const gridHelper = new THREE.GridHelper(10, 10, 0x888888, 0xcccccc);
scene.add(gridHelper);

// Điều khiển camera với chuột
let isMouseDown = false;
let mouseX = 0;
let mouseY = 0;
let rotateSpeed = 0.005;

const spherical = new THREE.Spherical();
spherical.setFromVector3(camera.position);

// Khi nhấn chuột
document.addEventListener('mousedown', (e) => {
    isMouseDown = true;
    mouseX = e.clientX;
    mouseY = e.clientY;
});

// Khi thả chuột
document.addEventListener('mouseup', () => {
    isMouseDown = false;
});

// Khi di chuyển chuột
document.addEventListener('mousemove', (e) => {
    if (isMouseDown) {
        const deltaX = e.clientX - mouseX;
        const deltaY = e.clientY - mouseY;
        
        if (e.ctrlKey || e.metaKey) {
            // Di chuyển camera (pan) khi giữ Ctrl
            const panX = deltaX * 0.01;
            const panY = -deltaY * 0.01;
            
            const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
            const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
            const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
            
            const panVector = right.clone().multiplyScalar(-panX)
                                .add(up.clone().multiplyScalar(panY));
            
            camera.position.add(panVector);
        } else {
            // Xoay camera
            spherical.theta -= deltaX * rotateSpeed;
            spherical.phi += deltaY * rotateSpeed;
            spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi));
            
            camera.position.setFromSpherical(spherical);
            camera.lookAt(0, 0, 0);
        }
    }
    
    mouseX = e.clientX;
    mouseY = e.clientY;
});

// Zoom với scroll wheel
document.addEventListener('wheel', (e) => {
    const zoomSpeed = 0.1;
    const distance = camera.position.length();
    const zoom = e.deltaY * zoomSpeed;
    
    if (distance + zoom > 0.5 && distance + zoom < 50) {
        camera.position.multiplyScalar((distance + zoom) / distance);
    }
});

// Điều chỉnh kích thước khi resize cửa sổ
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

// Hàm animation
function animate() {
    requestAnimationFrame(animate);
    renderer.render(scene, camera);
}

// Bắt đầu animation
animate();

