const workspaceEl = document.getElementById('workspace');
const liveTooltip = document.getElementById('live-tooltip');

const canvas = new fabric.Canvas('floorplan', {
    width: workspaceEl.clientWidth, height: workspaceEl.clientHeight,
    preserveObjectStacking: true, selection: true
});

window.addEventListener('resize', () => {
    canvas.setWidth(workspaceEl.clientWidth);
    canvas.setHeight(workspaceEl.clientHeight);
    setupGridBackground();
});

const GRID_SIZE = 20;

function setupGridBackground() {
    const gridCanvas = document.createElement('canvas');
    gridCanvas.width = GRID_SIZE; gridCanvas.height = GRID_SIZE;
    const ctx = gridCanvas.getContext('2d');
    ctx.strokeStyle = '#ecf0f1'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(GRID_SIZE, 0); ctx.lineTo(GRID_SIZE, GRID_SIZE); ctx.lineTo(0, GRID_SIZE); ctx.stroke();
    canvas.setBackgroundColor(new fabric.Pattern({ source: gridCanvas, repeat: 'repeat' }), canvas.renderAll.bind(canvas));
}

function reorderLayers() {
    const walls = canvas.getObjects().filter(o => o.customType === 'wall');
    walls.forEach(w => canvas.sendToBack(w));
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.innerText = msg; toast.style.opacity = 1;
    setTimeout(() => { toast.style.opacity = 0; }, 2000);
}

// Lịch sử thao tác (Undo/Redo)
const MAX_HISTORY = 30;
let historyStack = []; let historyIndex = -1;
let isHistoryProcessing = false; let saveTimer;

function updateHistoryUI() {
    document.getElementById('btn-undo').disabled = historyIndex <= 0;
    document.getElementById('btn-redo').disabled = historyIndex >= historyStack.length - 1;
}

function saveHistory(immediate = false) {
    if (isHistoryProcessing) return;
    clearTimeout(saveTimer);
    const executeSave = () => {
        const json = JSON.stringify(canvas.toJSON(['customType', 'classID', 'uuid', 'name', 'baseColor', 'locked']));
        if (historyIndex < historyStack.length - 1) historyStack = historyStack.slice(0, historyIndex + 1);
        historyStack.push(json);
        if (historyStack.length > MAX_HISTORY) historyStack.shift(); else historyIndex++;
        updateHistoryUI();
    };
    if (immediate) executeSave(); else saveTimer = setTimeout(executeSave, 150);
}

function loadHistoryState(index) {
    isHistoryProcessing = true;
    canvas.loadFromJSON(historyStack[index], function () {
        applyLockStateToObjects();
        reorderLayers();
        canvas.requestRenderAll();
        isHistoryProcessing = false;
        updateHistoryUI();
    });
}

function undo() { if (historyIndex > 0) loadHistoryState(--historyIndex); }
function redo() { if (historyIndex < historyStack.length - 1) loadHistoryState(++historyIndex); }
const generateUUID = () => crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2) + Date.now().toString(36);
const normalizeAngle = (a) => (((Math.round(a / 90) * 90) % 360) + 360) % 360;

const OBJECT_CATALOG = {
    'wall':      { w: 200, h: 5,   color: '#000000', type: 'wall',      label: 'Wall' },
    'window':    { w: 80,  h: 10,  color: '#85c1e9', type: 'window',    label: 'Window' },
    'door':      { w: 60,  h: 60,  type: 'door',      label: '', icon: 'icon/door.png' },
    'bed':       { w: 120, h: 160, type: 'furniture', label: '', icon: 'icon/bed.png' },
    'wardrobe':  { w: 100, h: 50,  type: 'furniture', label: '', icon: 'icon/wardrobe.png' },
    'nightstand':{ w: 40,  h: 40,  type: 'furniture', label: '', icon: 'icon/nightstand.png' },
    'sofa':      { w: 160, h: 70,  type: 'furniture', label: '', icon: 'icon/sofa.png' },
    'tv_stand':  { w: 120, h: 40,  type: 'furniture', label: '', icon: 'icon/tv_stand.png' },
    'table':     { w: 140, h: 80,  type: 'furniture', label: '', icon: 'icon/table.png' },
    'chair':     { w: 40,  h: 40,  type: 'furniture', label: '', icon: 'icon/chair.png' },
    'toilet':    { w: 40,  h: 60,  type: 'furniture', label: '', icon: 'icon/toilet.png' },
    'bathtub':   { w: 60,  h: 140, type: 'furniture', label: '', icon: 'icon/bathtub.png' },
    'sink':      { w: 50,  h: 40,  type: 'furniture', label: '', icon: 'icon/sink.png' },
    'plant':     { w: 30,  h: 30,  color: '#2ecc71', type: 'furniture', label: 'Plant' }
};

function spawnObject(classID, customOptions = {}) {
    const data = OBJECT_CATALOG[classID];
    if (!data) return;
    const center = canvas.getVpCenter();

    const finalW = customOptions.width || data.w;
    const finalH = customOptions.height || data.h;

    const commonOptions = {
        left: customOptions.left || center.x,
        top: customOptions.top || center.y,
        angle: customOptions.angle || 0,
        originX: 'center', originY: 'center',
        customType: data.type, classID: classID, uuid: customOptions.uuid || generateUUID(), name: data.label,
        baseColor: data.color || '#ffffff',
        locked: false
    };

    if (data.icon) {
        fabric.Image.fromURL(data.icon, function (img) {
            img.set({
                scaleX: finalW / img.width,
                scaleY: finalH / img.height,
                originX: 'center', originY: 'center'
            });
            const obj = new fabric.Group([img], commonOptions);
            canvas.add(obj); canvas.setActiveObject(obj); reorderLayers();
            saveHistory(true);
        });
    } else {
        const obj = new fabric.Rect(Object.assign({}, commonOptions, {
            width: finalW, height: finalH,
            fill: data.color,
            strokeWidth: 0,
        }));
        canvas.add(obj); canvas.setActiveObject(obj); reorderLayers();
        saveHistory(true);
    }
}

function spawnRoomTemplate() {
    const center = canvas.getVpCenter();
    const w = 400; const h = 300; const t = 5;

    canvas.discardActiveObject();
    isHistoryProcessing = true;

    spawnObject('wall', { width: w, height: t, left: center.x, top: center.y - h / 2 + t / 2 });
    spawnObject('wall', { width: w, height: t, left: center.x, top: center.y + h / 2 - t / 2 });
    spawnObject('wall', { width: h - t * 2, height: t, left: center.x - w / 2 + t / 2, top: center.y, angle: 90 });
    spawnObject('wall', { width: h - t * 2, height: t, left: center.x + w / 2 - t / 2, top: center.y, angle: 90 });

    isHistoryProcessing = false;
    canvas.discardActiveObject();
    saveHistory(true);
    showToast("Đã tạo mẫu phòng vuông 400x300");
}

function duplicateActive() {
    const activeItems = canvas.getActiveObjects();
    if (!activeItems.length) return;
    canvas.discardActiveObject();

    let pending = activeItems.filter(o => o.classID && !o.locked).length;
    if (pending === 0) return;

    activeItems.forEach(obj => {
        if (!obj.classID || obj.locked) return;
        obj.clone(function (clonedObj) {
            clonedObj.set({ left: obj.left + GRID_SIZE, top: obj.top + GRID_SIZE, uuid: generateUUID() });
            canvas.add(clonedObj); reorderLayers();
            if (--pending === 0) {
                saveHistory(true);
            }
        }, ['customType', 'classID', 'uuid', 'name', 'baseColor', 'locked']);
    });
}

function toggleLockActive() {
    const obj = canvas.getActiveObject();
    if (!obj) return;
    obj.locked = !obj.locked;
    obj.set({
        lockMovementX: obj.locked, lockMovementY: obj.locked,
        lockRotation: obj.locked, lockScalingX: obj.locked, lockScalingY: obj.locked,
        hasControls: !obj.locked, borderColor: obj.locked ? '#e74c3c' : '#1abc9c'
    });
    document.getElementById('btn-lock').innerText = obj.locked ? 'Mở Khóa 🔓' : 'Khóa 🔒';
    canvas.requestRenderAll();
    saveHistory(true);
}

function applyLockStateToObjects() {
    canvas.getObjects().forEach(obj => {
        if (!obj.customType) return;
        if (obj.locked) {
            obj.set({ lockMovementX: true, lockMovementY: true, lockRotation: true, lockScalingX: true, lockScalingY: true, hasControls: false, borderColor: '#e74c3c' });
        } else {
            obj.set({ lockMovementX: false, lockMovementY: false, lockRotation: false, lockScalingX: false, lockScalingY: false, hasControls: true, borderColor: '#1abc9c' });
        }
    });
}

// Camera Pan & Zoom
canvas.on('mouse:wheel', function (opt) {
    var delta = opt.e.deltaY; var zoom = canvas.getZoom(); zoom *= 0.999 ** delta;
    if (zoom > 5) zoom = 5; if (zoom < 0.2) zoom = 0.2;
    canvas.zoomToPoint({ x: opt.e.offsetX, y: opt.e.offsetY }, zoom);
    opt.e.preventDefault(); opt.e.stopPropagation();
});

canvas.on('mouse:down', function (opt) {
    if (opt.e.altKey) { this.isDragging = true; this.selection = false; this.lastPosX = opt.e.clientX; this.lastPosY = opt.e.clientY; }
});

canvas.on('mouse:move', function (opt) {
    if (this.isDragging) {
        var vpt = this.viewportTransform; vpt[4] += opt.e.clientX - this.lastPosX; vpt[5] += opt.e.clientY - this.lastPosY;
        this.requestRenderAll(); this.lastPosX = opt.e.clientX; this.lastPosY = opt.e.clientY;
    }
});

canvas.on('mouse:up', function (opt) {
    this.setViewportTransform(this.viewportTransform);
    this.isDragging = false;
    this.selection = true;
    liveTooltip.style.display = 'none';
});

function resetViewport() { canvas.setViewportTransform([1, 0, 0, 1, 0, 0]); canvas.requestRenderAll(); }

// UI Thông số
const propPanel = document.getElementById('properties-panel');
const msgMulti = document.getElementById('multi-select-msg');
const inW = document.getElementById('prop-w'); const inH = document.getElementById('prop-h');
const inAngle = document.getElementById('prop-angle');
const btnLock = document.getElementById('btn-lock');
const rightSidebar = document.getElementById('right-sidebar');

function loadObjectToPanel(activeObjects) {
    if (!activeObjects || activeObjects.length === 0) {
        rightSidebar.style.display = 'none';
        return;
    }

    rightSidebar.style.display = 'flex';

    if (activeObjects.length > 1) {
        propPanel.style.display = 'none';
        msgMulti.style.display = 'block';
        return;
    }

    msgMulti.style.display = 'none';
    propPanel.style.display = 'block';

    const obj = activeObjects[0];
    inW.value = Math.max(1, Math.round(obj.width * obj.scaleX));
    inH.value = Math.max(1, Math.round(obj.height * obj.scaleY));
    inAngle.value = Math.round(obj.angle || 0);
    btnLock.innerText = obj.locked ? 'Mở Khóa 🔓' : 'Khóa 🔒';
}

function updateObject() {
    const obj = canvas.getActiveObject();
    if (!obj || !obj.customType || obj.locked) return;
    const newW = Math.max(1, parseInt(inW.value) || 1);
    const newH = Math.max(1, parseInt(inH.value) || 1);
    const newAngle = parseInt(inAngle.value) || 0;

    if (obj.type === 'rect') {
        obj.set({ scaleX: 1, scaleY: 1, angle: newAngle, width: newW, height: newH });
        obj.setCoords();
    } else if (obj.type === 'group') {
        obj.set({ scaleX: 1, scaleY: 1, angle: newAngle });
        const child = obj.item(0);
        if (child) {
            if (child.type === 'rect') { child.set({ width: newW, height: newH }); }
            else if (child.type === 'image') { child.set({ scaleX: newW / child.width, scaleY: newH / child.height }); }
        }
        obj.scaleX = 1; obj.scaleY = 1;
        obj.width = newW; obj.height = newH;
        obj.setCoords();
    }
    canvas.requestRenderAll();
    saveHistory();
}

canvas.on('selection:created', (e) => loadObjectToPanel(e.selected));
canvas.on('selection:updated', (e) => loadObjectToPanel(e.selected));
canvas.on('selection:cleared', () => loadObjectToPanel(null));

// Live Tooltip
function updateLiveTooltip(e, text) {
    liveTooltip.style.display = 'block';
    liveTooltip.innerText = text;
    const workspaceRect = workspaceEl.getBoundingClientRect();
    liveTooltip.style.left = (e.e.clientX - workspaceRect.left + 15) + 'px';
    liveTooltip.style.top = (e.e.clientY - workspaceRect.top + 15) + 'px';
}

canvas.on('object:scaling', function (e) {
    const obj = e.target;
    const w = Math.round(obj.width * obj.scaleX);
    const h = Math.round(obj.height * obj.scaleY);
    updateLiveTooltip(e, `W: ${w} x H: ${h}`);
});

canvas.on('object:rotating', function (e) {
    const obj = e.target;
    updateLiveTooltip(e, `Góc xoay: ${normalizeAngle(obj.angle)}°`);
});

canvas.on('object:modified', function (e) {
    const obj = e.target;
    if (obj && obj.customType && !obj.locked) {
        if (obj.type === 'rect') {
            const w = Math.max(1, Math.round(obj.width * obj.scaleX));
            const h = Math.max(1, Math.round(obj.height * obj.scaleY));
            obj.set({ scaleX: 1, scaleY: 1, width: w, height: h });
            obj.setCoords();
        } else if (obj.type === 'group' && (obj.scaleX !== 1 || obj.scaleY !== 1)) {
            const w = Math.max(1, Math.round(obj.width * Math.abs(obj.scaleX)));
            const h = Math.max(1, Math.round(obj.height * Math.abs(obj.scaleY)));
            const child = obj.item(0);
            if (child) {
                if (child.type === 'rect') { child.set({ width: w, height: h, scaleX: 1, scaleY: 1 }); }
                else if (child.type === 'image') { child.set({ scaleX: w / child.width, scaleY: h / child.height }); }
            }
            if (obj.item(1)) obj.item(1).set({ left: 0, top: 0, scaleX: 1, scaleY: 1 });
            obj.scaleX = 1; obj.scaleY = 1;
            obj.width = w; obj.height = h;
            obj.setCoords();
        }
        canvas.requestRenderAll();
    }
    loadObjectToPanel(canvas.getActiveObjects());
    saveHistory();
});

const SNAP_TOLERANCE = 10;

canvas.on('object:moving', function (options) {
    const obj = options.target;
    if (obj.type === 'activeSelection' || obj.locked) return;

    let newLeft = Math.round(obj.left);
    let newTop = Math.round(obj.top);

    obj.set({ left: newLeft, top: newTop });
    loadObjectToPanel(canvas.getActiveObjects());
});

window.addEventListener('keydown', function (e) {
    const isInputFocused = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
    if (isInputFocused) return;
    if (e.key === 'Delete' || e.key === 'Backspace') {
        const activeObjects = canvas.getActiveObjects();
        if (activeObjects.length) {
            const unlockedObjects = activeObjects.filter(o => !o.locked);
            if (unlockedObjects.length === 0) return;
            unlockedObjects.forEach(obj => canvas.remove(obj));
            canvas.discardActiveObject(); rightSidebar.style.display = 'none';
            saveHistory(true);
        }
    }
    if (e.ctrlKey && e.key === 'd') { e.preventDefault(); duplicateActive(); }
    if (e.ctrlKey && e.key === 'z') { e.preventDefault(); undo(); }
    if (e.ctrlKey && e.key === 'y') { e.preventDefault(); redo(); }
    if (e.key === 'l' || e.key === 'L') { toggleLockActive(); }
});

function clearCanvas() {
    if (confirm("Xóa toàn bộ bản vẽ (bao gồm cả vật thể bị khóa)?")) {
        canvas.clear(); setupGridBackground(); rightSidebar.style.display = 'none'; document.getElementById('score-board').style.display = 'none';
        saveHistory(true);
    }
}

function saveDraft() {
    try {
        localStorage.setItem('floorplan_draft_v3', JSON.stringify(canvas.toJSON(['customType', 'classID', 'uuid', 'name', 'baseColor', 'locked'])));
        showToast("Đã lưu bản nháp an toàn!");
    } catch (e) { showToast("Lỗi: Không thể lưu nháp!"); }
}

function loadDraft() {
    setupGridBackground();
    try {
        const draft = localStorage.getItem('floorplan_draft_v3');
        if (draft) {
            isHistoryProcessing = true;
            canvas.loadFromJSON(draft, function () {
                applyLockStateToObjects();
                reorderLayers(); canvas.requestRenderAll();
                isHistoryProcessing = false;
                saveHistory(true);
            });
        } else { saveHistory(true); }
    } catch (e) { showToast("Bản nháp bị lỗi, tải bản vẽ mới."); saveHistory(true); }
}
window.addEventListener('load', loadDraft);

function getPolygonDistance(obj1, obj2) {
    const c1 = obj1.getCoords(); const c2 = obj2.getCoords();
    let minDist = Infinity;
    for (let p1 of c1) { for (let p2 of c2) { const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y); if (dist < minDist) minDist = dist; } }
    return minDist;
}

function evaluateLayout() {
    const items = canvas.getObjects().filter(o => o.customType === 'furniture' || o.customType === 'window');
    let totalScore = 0; let details = [];
    for (let i = 0; i < items.length; i++) {
        for (let j = i + 1; j < items.length; j++) {
            const a = items[i], b = items[j]; const dist = getPolygonDistance(a, b); const pair = [a.classID, b.classID].sort().join("-");
            if (pair === "bed-nightstand") {
                if (dist < 40) { totalScore += 20; details.push(`+20: Tủ đầu giường hợp lý`); } else { totalScore -= 10; details.push(`-10: Tủ đầu giường xa Giường`); }
            }
            if (pair === "bed-wardrobe") {
                if (dist < 10) { totalScore -= 50; details.push(`-50: Tủ ĐÈ / quá sát Giường!`); } else if (dist < 50) { totalScore -= 30; details.push(`-30: Tủ quá sát Giường`); } else { totalScore += 10; details.push(`+10: Không gian Tủ - Giường mở cửa tốt`); }
            }
            if (pair === "wardrobe-window") { if (dist < 10) { totalScore -= 40; details.push(`-40: Tủ che Cửa sổ!`); } }
        }
    }
    document.getElementById('score-board').style.display = 'block'; document.getElementById('total-score').innerText = totalScore;
    document.getElementById('score-details').innerHTML = details.length ? details.map(d => `<li>${d}</li>`).join('') : '<li>Chưa đủ điều kiện đánh giá</li>';
}

function exportData() {
    const items = canvas.getObjects().filter(o => o.customType);
    const layoutData = {
        objects: items.map(obj => ({
            id: obj.uuid, type: obj.classID,
            position: { x: Math.round(obj.left), z: Math.round(obj.top) },
            rotation: normalizeAngle(obj.angle || 0),
            size: { w: Math.round(obj.width * obj.scaleX), d: Math.round(obj.height * obj.scaleY) }
        }))
    };
    const jsonStr = JSON.stringify(layoutData, null, 2);
    navigator.clipboard.writeText(jsonStr).then(() => {
        showToast("Đã copy JSON vào Clipboard!"); console.log(jsonStr);
    }).catch(() => { alert("Dữ liệu xuất ra Console. Nhấn F12 để xem."); });
}

function downloadJSON() {
    const items = canvas.getObjects().filter(o => o.customType);
    const layoutData = {
        objects: items.map(obj => ({
            id: obj.uuid,
            type: obj.classID,
            position: { x: Math.round(obj.left), z: Math.round(obj.top) },
            rotation: normalizeAngle(obj.angle || 0),
            size: { w: Math.round(obj.width * obj.scaleX), d: Math.round(obj.height * obj.scaleY) }
        }))
    };

    const jsonStr = JSON.stringify(layoutData, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "floorplan_masterpiece.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast("Đã lưu file JSON về máy!");
}

function uploadJSON(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (e) {
        try {
            const data = JSON.parse(e.target.result);
            if (!data.objects || !Array.isArray(data.objects)) {
                throw new Error("File JSON không đúng cấu trúc Layout!");
            }

            canvas.clear();
            setupGridBackground();
            document.getElementById('right-sidebar').style.display = 'none';

            isHistoryProcessing = true;

            data.objects.forEach(item => {
                spawnObject(item.type, {
                    width: item.size.w,
                    height: item.size.d,
                    left: item.position.x,
                    top: item.position.z,
                    angle: item.rotation,
                    uuid: item.id
                });
            });

            setTimeout(() => {
                isHistoryProcessing = false;
                saveHistory(true);
                showToast("Đã tải lên & dựng lại Layout thành công!");
            }, 500);

        } catch (error) {
            alert("Lỗi đọc file: " + error.message);
        }

        event.target.value = '';
    };

    reader.readAsText(file);
}

function handleFakeApiUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const fileName = file.name;
    let jsonFileToLoad = '';

    if (fileName === 'example.png') {
        jsonFileToLoad = 'god.json';
    } else if (fileName === 'image_floorplan.png') {
        jsonFileToLoad = 'goddess.json';
    } else {
        jsonFileToLoad = 'god.json';
    }

    document.getElementById('loading-overlay').style.display = 'flex';

    setTimeout(() => {
        document.getElementById('loading-overlay').style.display = 'none';
        showToast("Phân tích thành công! Đang dựng bản vẽ...");

        fetch(jsonFileToLoad)
            .then(response => {
                if (!response.ok) throw new Error("Không tìm thấy file " + jsonFileToLoad);
                return response.json();
            })
            .then(data => {
                renderLayoutFromData(data);
            })
            .catch(error => {
                alert("Lỗi tải JSON: " + error.message + "\n(Nhớ đặt " + jsonFileToLoad + " cùng thư mục với file HTML nhé!)");
            });

        event.target.value = '';
    }, 22000);
}

function renderLayoutFromData(data) {
    if (!data.objects || !Array.isArray(data.objects)) {
        alert("Dữ liệu JSON không đúng cấu trúc!");
        return;
    }

    canvas.clear();
    setupGridBackground();
    document.getElementById('right-sidebar').style.display = 'none';
    isHistoryProcessing = true;

    data.objects.forEach(item => {
        spawnObject(item.type, {
            width: item.size.w,
            height: item.size.d,
            left: item.position.x,
            top: item.position.z,
            angle: item.rotation,
            uuid: item.id
        });
    });

    setTimeout(() => {
        isHistoryProcessing = false;
        saveHistory(true);
    }, 500);
}