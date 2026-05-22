import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

let scene, camera, renderer;
const canvas = document.getElementById('canvas');
const jsonInput = document.getElementById('jsonInput');
const statusDiv = document.getElementById('status');
const roomInfoDiv = document.getElementById('roomInfo');
const modelsListDiv = document.getElementById('modelsList');
const modelsListContainer = document.getElementById('modelsListContainer');
const objectParamsDiv = document.getElementById('objectParams');

const SERVER_URL = 'http://localhost:8000';
let availableModels = [];
let loadedObjects = [];
let selectedObject = null;

// Camera controls
let cameraRotation = { theta: Math.PI / 4, phi: Math.PI / 3 };
let cameraDistance = 15;

// Mouse state
let isRightDragging = false;
let previousMousePosition = { x: 0, y: 0 };

// Raycaster
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

// Global room dimensions
let room = { width: 0, length: 0 };

// Khởi tạo Loader
const gltfLoader = new GLTFLoader();

// --- INIT ---
async function init() {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);

    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    updateCameraPosition();

    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(10, 20, 10);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    scene.add(dirLight);

    setupControls();
    window.addEventListener('resize', onWindowResize);
    animate();
}

// --- CONTROLS ---
function updateCameraPosition() {
    camera.position.x = cameraDistance * Math.sin(cameraRotation.theta) * Math.cos(cameraRotation.phi);
    camera.position.y = cameraDistance * Math.sin(cameraRotation.phi);
    camera.position.z = cameraDistance * Math.cos(cameraRotation.theta) * Math.cos(cameraRotation.phi);
    camera.lookAt(0, 0, 0);
}


function setupControls() {
    canvas.addEventListener('mousedown', (e) => {
        if (e.button === 2) isRightDragging = true;
        else if (e.button === 0) handleObjectSelection(e);
        previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    canvas.addEventListener('mousemove', (e) => {
        const deltaX = e.clientX - previousMousePosition.x;
        const deltaY = e.clientY - previousMousePosition.y;

        if (isRightDragging) {
            cameraRotation.theta -= deltaX * 0.01;
            cameraRotation.phi -= deltaY * 0.01;
            cameraRotation.phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.1, cameraRotation.phi));
            updateCameraPosition();
        }
        previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    canvas.addEventListener('mouseup', () => isRightDragging = false);
    canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        cameraDistance += e.deltaY * 0.01;
        cameraDistance = Math.max(2, Math.min(50, cameraDistance));
        updateCameraPosition();
    });
    
    // Phím tắt xoay vật thể (R)
    window.addEventListener('keydown', (e) => {
        if (e.key.toLowerCase() === 'r' && selectedObject) {
            selectedObject.mesh.rotation.y += Math.PI / 2;
            updateObjectParamsUI(selectedObject);
        }
    });

    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    document.addEventListener('contextmenu', (e) => e.preventDefault());
}

// --- SELECTION ---
function handleObjectSelection(event) {
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);

    const groups = loadedObjects.map(obj => obj.mesh);
    const intersects = raycaster.intersectObjects(groups, true);

    if (intersects.length > 0) {
        let selectedWrapper = intersects[0].object;
        while(selectedWrapper.parent && selectedWrapper.parent.type !== 'Scene') {
            const isManagedObject = loadedObjects.some(obj => obj.mesh === selectedWrapper.parent);
            if (isManagedObject) {
                selectedWrapper = selectedWrapper.parent;
                break;
            }
            selectedWrapper = selectedWrapper.parent;
        }
        const obj = loadedObjects.find(o => o.mesh === selectedWrapper);
        if (obj) selectObject(obj);
    } else {
        deselectObject();
    }
}

function selectObject(obj) {
    if (selectedObject) {
        // Reset emissive cũ (nếu có material hỗ trợ)
        selectedObject.mesh.traverse(c => {
            if(c.isMesh && c.material.emissive) c.material.emissive.setHex(0x000000);
        });
    }
    selectedObject = obj;
    // Highlight mới
    obj.mesh.traverse(c => {
        if(c.isMesh && c.material.emissive) c.material.emissive.setHex(0x444444);
    });
    showObjectParams(obj);
}

function deselectObject() {
    if (selectedObject) {
        selectedObject.mesh.traverse(c => {
            if(c.isMesh && c.material.emissive) c.material.emissive.setHex(0x000000);
        });
    }
    selectedObject = null;
    objectParamsDiv.style.display = 'none';
}

function showObjectParams(obj) {
    objectParamsDiv.innerHTML = `
        <h3>🎯 ${obj.name}</h3>
        <div style="font-size:0.8em; color:#888; margin-bottom:10px">Press 'R' to Rotate 90°</div>
        <div class="param-group"><label>Pos X:</label><input type="number" step="0.1" id="paramX"></div>
        <div class="param-group"><label>Pos Y (Height):</label><input type="number" step="0.1" id="paramY"></div>
        <div class="param-group"><label>Pos Z:</label><input type="number" step="0.1" id="paramZ"></div>
        <div class="param-group"><label>Rot (°):</label><input type="number" step="1" id="paramRotation"></div>
    `;
    objectParamsDiv.style.display = 'block';
    
    // Gán giá trị & Event Listener
    const inputX = document.getElementById('paramX');
    const inputY = document.getElementById('paramY');
    const inputZ = document.getElementById('paramZ');
    const inputRot = document.getElementById('paramRotation');

    const updateInputs = () => {
        inputX.value = obj.mesh.position.x.toFixed(2);
        
        let currentY = obj.mesh.position.y;
        if (obj.mesh.isMesh) {
            const h = obj.data.size[1] || 0.5;
            currentY = obj.mesh.position.y - h/2;
        }
        inputY.value = currentY.toFixed(2);
        
        inputZ.value = obj.mesh.position.z.toFixed(2);
        inputRot.value = (obj.mesh.rotation.y * 180 / Math.PI).toFixed(0);
    };
    updateInputs();

    inputX.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value) || 0;
        obj.mesh.position.x = val;
        obj.data.position[0] = val + (room.width / 2);
    });
    inputY.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value) || 0;
        if (obj.mesh.isMesh) {
            const h = obj.data.size[1] || 0.5;
            obj.mesh.position.y = val + h/2;
        } else {
            obj.mesh.position.y = val;
        }
        obj.data.position[1] = val;
    });
    inputZ.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value) || 0;
        obj.mesh.position.z = val;
        obj.data.position[2] = val + (room.length / 2);
    });
    inputRot.addEventListener('input', (e) => {
        const rad = (parseFloat(e.target.value) || 0) * Math.PI / 180;
        obj.mesh.rotation.y = rad;
        obj.data.position[3] = rad;
    });

    // Lưu reference updateUI để gọi khi nhấn phím R
    window.updateObjectParamsUI = (currentObj) => {
        if(currentObj === obj) updateInputs();
    }
}

// --- LOGIC TÌM KIẾM ---
// room_viewer.js - Cập nhật hàm tìm kiếm
async function findModelPath(item) {
    // Lấy tên vật thể để xác định Collection
    const objectName = item.object || item.name;
    let keyword = objectName.toLowerCase().replace(/_[0-9]+$/, '').replace(/_/g, ' ').trim();
    
    // Mapping cơ bản như cũ
    if (keyword.includes('nightstand') || keyword.includes('bedside')) keyword = 'nightstand';
    if (keyword.includes('cabinet') || keyword.includes('closet')) keyword = 'wardrobe';
    
    try {
        const url = `${SERVER_URL}/search`;
        console.log(`🔍 Hybrid Searching: [${keyword}]`);
        
        // Chuyển sang POST để gửi được JSON object phức tạp
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                q: keyword,
                item_data: item // Gửi toàn bộ thông tin: color, style, description...
            })
        });

        if (!resp.ok) return null;
        const data = await resp.json();
        
        if (data.found && data.path) {
            console.log(`   ✅ Found (Score: ${data.total_score.toFixed(2)}): ${data.path}`);
            return data.path;
        }
    } catch (err) {
        console.warn(`   ⚠️ Error searching "${keyword}":`, err);
    }
    return null;
}

// --- JSON LOADING ---
async function loadRoomJSON(file) {
    showStatus('Đang đọc file JSON...', 'success');
    const reader = new FileReader();
    reader.onload = async function(e) {
        try {
            const roomData = JSON.parse(e.target.result);
            await processRoomData(roomData);
        } catch (error) {
            showStatus('Lỗi xử lý: ' + error.message, 'error');
            console.error(error);
        }
    };
    reader.readAsText(file);
}

// --- LOGIC XỬ LÝ DỮ LIỆU PHÒNG (QUAN TRỌNG) ---
async function processRoomData(data) {
    // 1. Cleanup Scene
    loadedObjects.forEach(obj => {
        scene.remove(obj.mesh);
        // Dispose geometries/materials nếu cần kỹ tính
    });
    loadedObjects = [];
    deselectObject();

    // 2. Setup Room Info
    room.width = data.room_width || 5;
    room.length = data.room_length || 5;
    const roomStyle = data.style || "Modern";

    roomInfoDiv.innerHTML = `
        <h3>📐 Room: ${room.width}m x ${room.length}m</h3>
        <div style="font-size:0.8em; color:#aaa; margin-top:5px">Style: ${roomStyle}</div>
    `;
    roomInfoDiv.style.display = 'block';

    createRoom(room.width, room.length);

    // 3. CHUẨN HÓA DỮ LIỆU ĐẦU VÀO (Convert sang List thống nhất)
    let objectsList = [];

    // Kiểm tra xem JSON là format Mới (Array) hay Cũ (Object Key)
    if (data.furniture && Array.isArray(data.furniture)) {
        // Format MỚI: "furniture": [ {type: "bed", ...}, ... ]
        console.log("Detect: New JSON Format (Array)");
        
        objectsList = data.furniture.map(item => {
            let posData = item.position;
            let sizeData = item.size; // [w, h, l]

            // Nếu là vật thể gắn tường (wall), cần tính toán lại vị trí tuyệt đối
            if (item.wall) {
                // position của wall object thường là số thực (0.0 - 1.0)
                // getAbsolutePosition trả về [x, z, rot]
                posData = getAbsolutePositionForFixed(
                    item.wall, item.position, 
                    room.width, room.length, 
                    item.width || 1, item.length || 0.1
                );
                // Với wall object, size có thể là width/length rời rạc
                sizeData = [item.width, item.height || 1, item.length];
            }

            // Chuẩn hóa position sang 4 tham số [x, y, z, rotation]
            let normalizedPos = [0, 0, 0, 0];
            if (Array.isArray(posData)) {
                if (posData.length === 3) {
                    normalizedPos = [posData[0], 0.0, posData[1], posData[2]];
                } else if (posData.length === 4) {
                    normalizedPos = [posData[0], posData[1], posData[2], posData[3]];
                }
            }

            return {
                name: item.type,
                description: item.description || "",
                path: item.path, // <--- Nhận path từ Hybrid Search
                // Chuẩn hóa data để truyền vào load
                data: {
                    position: normalizedPos,
                    size: Array.isArray(sizeData) ? sizeData : [1,1,1]    // [w, h, l]
                }
            };
        });

    } else {
        // Format CŨ (Fallback): "bed": {...}
        console.log("Detect: Old JSON Format (Keys)");
        for (const key in data) {
            if (['prompt', 'room_width', 'room_length', 'style'].includes(key)) continue;
            
            const objData = data[key];
            let posData = objData.position;
            let sizeData = [objData.width || 1, 1.5, objData.length || 1]; // Default height 1.5

            if (objData.wall) {
                posData = getAbsolutePositionForFixed(
                    objData.wall, objData.position, 
                    room.width, room.length, 
                    objData.width, objData.length
                );
            }

            // Chuẩn hóa position sang 4 tham số [x, y, z, rotation]
            let normalizedPos = [0, 0, 0, 0];
            if (Array.isArray(posData)) {
                if (posData.length === 3) {
                    normalizedPos = [posData[0], 0.0, posData[1], posData[2]];
                } else if (posData.length === 4) {
                    normalizedPos = [posData[0], posData[1], posData[2], posData[3]];
                }
            }

            objectsList.push({
                name: key,
                description: "", // Format cũ không có description riêng
                data: {
                    position: normalizedPos,
                    size: sizeData 
                }
            });
        }
    }

    // 4. LOAD PARALLEL (Song song)
    showStatus(`Searching & Loading ${objectsList.length} items...`, 'success');
    modelsListContainer.style.display = 'block';
    modelsListDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Processing...</div>';

    let loadedCount = 0;
    let placeholderCount = 0;

    const loadPromises = objectsList.map(async (item) => {
        const { name, description, data: objData, path: preFoundPath } = item;
        
        // Dùng luôn path do Backend chọn (nếu có từ Hybrid Search), nếu không thì tìm mới
        let foundPath = preFoundPath;
        if (!foundPath) {
            const searchDesc = description && description.length > 5 ? description : roomStyle;
            foundPath = await findModelPath(name, searchDesc);
        }

        let resultHtml = "";

        if (foundPath) {
            try {
                await loadObjectModel(name, objData, foundPath);
                loadedCount++;
                resultHtml = `<div class="model-item">✓ <strong>${name}</strong></div>`;
            } catch (e) {
                console.error(e);
                createPlaceholder(name, objData);
                placeholderCount++;
                resultHtml = `<div class="model-item" style="color:orange">⚠ ${name} (Error)</div>`;
            }
        } else {
            createPlaceholder(name, objData);
            placeholderCount++;
            resultHtml = `<div class="model-item" style="opacity:0.5">⬜ ${name}</div>`;
        }
        return resultHtml;
    });

    const results = await Promise.all(loadPromises);
    
    modelsListDiv.innerHTML = results.join('');
    showStatus(`Done: ${loadedCount} Models | ${placeholderCount} Boxes`, 'success');
}

// --- HÀM TẢI MODEL THÔNG MINH (SMART ALIGN) ---
async function loadObjectModel(name, objData, modelPath) {
    return new Promise((resolve, reject) => {
        gltfLoader.load(`${SERVER_URL}/models/${modelPath}`, (gltf) => {
            const model = gltf.scene;

            // 1. Reset
            model.scale.set(1, 1, 1);
            model.rotation.set(0, 0, 0);

            // 2. Đo kích thước gốc
            const box = new THREE.Box3().setFromObject(model);
            const size = new THREE.Vector3();
            box.getSize(size); // [x, y, z] gốc

            // 3. Lấy kích thước đích [w, h, l]
            // Lưu ý: Trong logic cũ width=X, length=Z. 
            // JSON mới: size[0]=Width(X), size[1]=Height(Y), size[2]=Length(Z)
            const targetW = objData.size[0] || 1;
            const targetH = objData.size[1] || 1;
            const targetL = objData.size[2] || 1;

            // --- SMART ALIGN (XOAY TỰ ĐỘNG) ---
            const modelRatio = size.x / size.z;   // Tỷ lệ gốc
            const targetRatio = targetW / targetL; // Tỷ lệ đích

            // Kiểm tra hình vuông (sai số 20%)
            const isModelSquare = modelRatio > 0.8 && modelRatio < 1.2;
            const isTargetSquare = targetRatio > 0.8 && targetRatio < 1.2;

            if (!isModelSquare && !isTargetSquare) {
                // Chỉ xoay nếu cả 2 đều là hình chữ nhật rõ ràng
                const isModelWide = size.x > size.z;
                const isTargetWide = targetW > targetL;

                if (isModelWide !== isTargetWide) {
                    console.log(`🔄 Rotating ${name} 90° to fit`);
                    model.rotation.y = Math.PI / 2;
                    // Swap kích thước gốc để tính scale đúng
                    const temp = size.x;
                    size.x = size.z;
                    size.z = temp;
                }
            }

            // 4. Scale 3 trục
            // Tránh chia cho 0
            model.scale.set(
                targetW / (size.x || 1),
                targetH / (size.y || 1),
                targetL / (size.z || 1)
            );

            // 5. Căn tâm (Re-center Pivot)
            const finalBox = new THREE.Box3().setFromObject(model);
            const center = new THREE.Vector3();
            finalBox.getCenter(center);

            // Dời về gốc (0,0,0) và đáy chạm sàn
            model.position.x += (model.position.x - center.x);
            model.position.z += (model.position.z - center.z);
            model.position.y -= finalBox.min.y;

            // 6. Đặt vào Wrapper
            const wrapper = new THREE.Group(); // Khai báo wrapper
            wrapper.add(model);
            const pX = objData.position[0];
            const pY = objData.position[1];
            const pZ = objData.position[2]; 
            const pRot = objData.position[3];

            // Gọi hàm snap để sửa lại pX và pZ nếu cần
            const snapped = getSnappedPosition(
                pX, pZ, pRot, 
                targetW, targetL, 
                room.width, room.length
            );

            const halfW = room.width / 2;
            const halfL = room.length / 2;

            // Sử dụng tọa độ đã được snap
            wrapper.position.set(snapped.x - halfW, pY, snapped.z - halfL);
            wrapper.rotation.y = pRot;

            // Shadow
            model.traverse(c => { if(c.isMesh) { c.castShadow=true; c.receiveShadow=true; }});

            scene.add(wrapper);
            loadedObjects.push({ name, mesh: wrapper, data: objData });
            resolve(wrapper);

        }, undefined, reject);
    });
}

function getSnappedPosition(pX, pZ, pRot, targetW, targetL, roomW, roomL) {
    const threshold = 0.15; // Ngưỡng nhận diện sát tường (15cm)
    let newX = pX;
    let newZ = pZ;

    // Tính toán kích thước thực tế trong không gian thế giới sau khi xoay (0, 90, 180, 270 độ)
    // Nếu xoay 90 hoặc 270 độ, Width và Length sẽ đổi chỗ cho nhau
    const isRotated = Math.abs(Math.sin(pRot)) > 0.7; 
    const actualW = isRotated ? targetL : targetW;
    const actualL = isRotated ? targetW : targetL;

    // Kiểm tra trục X (Tường trái/phải)
    if (pX - actualW / 2 < threshold) { 
        newX = actualW / 2; // Sát tường trái (x=0)
    } else if (pX + actualW / 2 > roomW - threshold) {
        newX = roomW - actualW / 2; // Sát tường phải (x=roomW)
    }

    // Kiểm tra trục Z (Tường trên/dưới)
    if (pZ - actualL / 2 < threshold) {
        newZ = actualL / 2; // Sát tường dưới (z=0)
    } else if (pZ + actualL / 2 > roomL - threshold) {
        newZ = roomL - actualL / 2; // Sát tường trên (z=roomL)
    }

    return { x: newX, z: newZ };
}
// --- TẠO HỘP GIẢ (FALLBACK) ---
function createPlaceholder(name, objData) {
    const w = objData.size[0] || 1;
    const h = objData.size[1] || 0.5;
    const l = objData.size[2] || 1;

    const geometry = new THREE.BoxGeometry(w, h, l);
    const material = new THREE.MeshStandardMaterial({ 
        color: getColorForObject(name), 
        transparent: true, opacity: 0.8 
    });
    
    const mesh = new THREE.Mesh(geometry, material);
    
    const halfW = room.width / 2;
    const halfL = room.length / 2;
    const pX = objData.position[0];
    const pY = objData.position[1];
    const pZ = objData.position[2];
    const pRot = objData.position[3];

    mesh.position.set(pX - halfW, pY + h/2, pZ - halfL);
    mesh.rotation.y = pRot;

    scene.add(mesh);
    loadedObjects.push({ name, mesh, data: objData });
}

// --- HELPER FUNCTIONS ---
function createRoom(width, length) {
    // Floor
    const floorGeo = new THREE.PlaneGeometry(width, length);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0xeeeeee, roughness: 0.8 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    // Walls Outline
    const pts = [
        new THREE.Vector3(-width/2, 0, -length/2),
        new THREE.Vector3(width/2, 0, -length/2),
        new THREE.Vector3(width/2, 0, length/2),
        new THREE.Vector3(-width/2, 0, length/2),
        new THREE.Vector3(-width/2, 0, -length/2)
    ];
    const lineGeo = new THREE.BufferGeometry().setFromPoints(pts);
    const lineMat = new THREE.LineBasicMaterial({ color: 0x888888 });
    scene.add(new THREE.Line(lineGeo, lineMat));
    
    // Grid Helper
    const grid = new THREE.GridHelper(Math.max(width, length), 10, 0xcccccc, 0xeeeeee);
    scene.add(grid);
}

function getAbsolutePositionForFixed(wall, frac, roomW, roomL, objW, objL) {
    // Hàm này tính toán vị trí cho cửa/cửa sổ bám tường
    let x, y, rot;
    const halfThickness = objL / 2; 

    if (wall === 'north') { // Z min
        x = frac * roomW; y = roomL; rot = Math.PI; 
        // Note: Logic tọa độ trong JS của bạn có vẻ là 0 -> Max.
        // Nhưng trong ThreeJS, tâm là 0,0. Cần map lại nếu cần.
        // Ở đây tôi giữ logic cũ của bạn trả về giá trị tuyệt đối (0..W, 0..L)
        // Sau đó ở bước wrapper.position.set ta trừ đi halfW, halfL.
    } else if (wall === 'south') { // Z max
        x = frac * roomW; y = 0; rot = 0; // Giả sử wall south là z=0
    } else if (wall === 'east') {
        x = roomW; y = frac * roomL; rot = -Math.PI/2;
    } else if (wall === 'west') {
        x = 0; y = frac * roomL; rot = Math.PI/2;
    }
    return [x, y, rot];
}

function getColorForObject(name) {
    const n = name.toLowerCase();
    if(n.includes('bed')) return 0x8B4513;
    if(n.includes('rug')) return 0xE9967A;
    if(n.includes('wardrobe')) return 0xA0522D;
    if(n.includes('desk')) return 0xD2691E;
    return 0x808080;
}

function showStatus(msg, type) {
    statusDiv.textContent = msg;
    statusDiv.className = type;
    statusDiv.style.display = 'block';
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
    requestAnimationFrame(animate);
    renderer.render(scene, camera);
}

jsonInput.addEventListener('change', (e) => {
    if (e.target.files[0]) loadRoomJSON(e.target.files[0]);
    e.target.value = '';
});
// Thêm vào cuối file room_viewer.js hoặc trong khu vực setup Event Listeners

const btnGenerate = document.getElementById('btnGenerate');
const aiPromptInput = document.getElementById('aiPrompt');

btnGenerate.addEventListener('click', async () => {
    const prompt = aiPromptInput.value.trim();
    if (!prompt) {
        showStatus('Vui lòng nhập mô tả căn phòng!', 'error');
        return;
    }

    try {
        btnGenerate.disabled = true;
        btnGenerate.textContent = '⌛ Đang thiết kế...';
        showStatus('AI đang suy nghĩ bố cục...', 'success');

        const response = await fetch(`${SERVER_URL}/generate_layout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt })
        });

        if (!response.ok) throw new Error(`Lỗi server: ${response.status}`);

        // ── Đọc SSE stream đúng cách ──────────────────────────────────────
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let eventType = '';
        let dataStr = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Tách thành từng dòng, giữ lại dòng chưa hoàn chỉnh
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed.startsWith('event: ')) {
                    eventType = trimmed.slice(7).trim();
                } else if (trimmed.startsWith('data: ')) {
                    dataStr = trimmed.slice(6).trim();
                } else if (trimmed === '' && eventType && dataStr) {
                    // Một SSE message hoàn chỉnh
                    try {
                        const data = JSON.parse(dataStr);

                        if (eventType === 'progress') {
                            showStatus(`[Bước ${data.step}] ${data.message}`, 'success');

                        } else if (eventType === 'result') {
                            // Flatten metadata + furniture để processRoomData hiểu được
                            const roomData = {
                                room_width:  data.metadata?.room_width  ?? 5,
                                room_length: data.metadata?.room_length ?? 5,
                                style:       data.metadata?.style       ?? '',
                                room_type:   data.metadata?.room_type   ?? '',
                                explanation: data.metadata?.explanation ?? '',
                                furniture:   data.furniture ?? [],
                            };
                            await processRoomData(roomData);
                            const explanation = roomData.explanation;
                            if (explanation) showStatus('✅ ' + explanation, 'success');
                            else showStatus('✅ Thiết kế hoàn tất!', 'success');

                        } else if (eventType === 'error') {
                            showStatus('❌ ' + (data.message || 'Lỗi không xác định'), 'error');
                        }
                    } catch (parseErr) {
                        console.warn('SSE parse error:', parseErr, dataStr);
                    }
                    // Reset cho message tiếp theo
                    eventType = '';
                    dataStr = '';
                }
            }
        }

    } catch (err) {
        console.error(err);
        showStatus('❌ Lỗi: ' + err.message, 'error');
    } finally {
        btnGenerate.disabled = false;
        btnGenerate.textContent = '✨ Thiết kế bằng AI';
    }
});
// Start
init();