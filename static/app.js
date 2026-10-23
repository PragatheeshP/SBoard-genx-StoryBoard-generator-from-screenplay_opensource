/**
 * Screenplay-to-Storyboard Generator — Frontend Application
 * Single-page app using plain HTML/CSS/JS, no framework.
 */

const EXAMPLE_SCREENPLAYS = {
    1: `SCENE: 1 - INT. COFFEE SHOP - DAY
DESCRIPTION: Two friends reunite after years apart.

SHOT: 1
TYPE: wide
ANGLE: eye-level
CHAR: MAYA, RAHUL
ACTION: Maya enters the coffee shop and spots Rahul sitting at a corner table
MOOD: peaceful

SHOT: 2
TYPE: close-up
ANGLE: eye-level
CHAR: MAYA
ACTION: Maya's face lights up with joy and recognition
MOOD: happy

SHOT: 3
TYPE: medium
ANGLE: eye-level
CHAR: MAYA, RAHUL
ACTION: They embrace warmly, both smiling
MOOD: happy`,

    2: `SCENE: 1 - EXT. ROOFTOP - NIGHT
DESCRIPTION: A tense confrontation between hero and villain.

SHOT: 1
TYPE: wide
ANGLE: low-angle
CHAR: HERO, VILLAIN
ACTION: Hero and Villain face each other on the edge of a rooftop
MOOD: tense

SHOT: 2
TYPE: close-up
ANGLE: eye-level
CHAR: VILLAIN
ACTION: Villain raises his weapon, eyes cold and calculating
MOOD: dramatic

SHOT: 3
TYPE: over-the-shoulder
ANGLE: eye-level
CHAR: HERO
ACTION: Hero stands firm, refusing to back down
MOOD: dramatic

SHOT: 4
TYPE: wide
ANGLE: bird's-eye
CHAR: HERO, VILLAIN
ACTION: Both figures silhouetted against the city lights far below
MOOD: mysterious`,
};

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────

const state = {
    project: null,
    shots: [],
    characters: [],
    currentSection: 'storyboard',
    selectedFile: null,
};

// ─────────────────────────────────────────────────────────────────────────────
// API helpers
// ─────────────────────────────────────────────────────────────────────────────

async function api(method, path, body = null, isForm = false) {
    const opts = { method, credentials: 'include' };
    if (body && isForm) {
        opts.body = body;
    } else if (body) {
        opts.headers = { 'Content-Type': 'application/json' };
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(`/api${path}`, opts);
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'API error');
    return json;
}

// ─────────────────────────────────────────────────────────────────────────────
// Notifications
// ─────────────────────────────────────────────────────────────────────────────

function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText =
            'position:fixed;top:2rem;right:2rem;z-index:99999;display:flex;flex-direction:column;gap:0.75rem;';
        document.body.appendChild(container);
    }
    const colors = { info: '#4a5fc1', error: '#d64f4f', success: '#3a9a6e' };
    const toast = document.createElement('div');
    toast.style.cssText = `
        background:${colors[type] || colors.info};color:#fff;padding:1rem 1.5rem;
        border-radius:10px;font-size:0.95rem;box-shadow:0 4px 16px rgba(0,0,0,0.2);
        max-width:360px;opacity:0;transition:opacity 0.3s ease;
    `;
    toast.textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.style.opacity = '1'; });
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 4500);
}

// ─────────────────────────────────────────────────────────────────────────────
// Loading overlay
// ─────────────────────────────────────────────────────────────────────────────

function showLoading(msg = 'Processing…') {
    document.getElementById('loading-message').textContent = msg;
    document.getElementById('loading-overlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loading-overlay').style.display = 'none';
}

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

function showSection(name) {
    // Switch from landing to app
    document.getElementById('landing').style.display = 'none';
    document.getElementById('app').style.display = 'flex';

    const sections = ['storyboard', 'upload', 'characters'];
    sections.forEach(s => {
        document.getElementById(`${s}-section`).style.display = s === name ? 'block' : 'none';
    });

    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.section === name);
    });

    state.currentSection = name;
}

function showLanding() {
    document.getElementById('landing').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
}

// ─────────────────────────────────────────────────────────────────────────────
// Project loading
// ─────────────────────────────────────────────────────────────────────────────

async function loadProject() {
    try {
        const data = await api('GET', '/project');
        state.project = data;
        state.shots = data.shots || [];
        state.characters = data.characters || [];
        if (data.title) document.getElementById('project-title').textContent = data.title;
        renderShots();
        renderCharacters();
    } catch (e) {
        console.error('Failed to load project:', e);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Upload handlers
// ─────────────────────────────────────────────────────────────────────────────

function switchUploadTab(tab) {
    ['text', 'file'].forEach(t => {
        document.getElementById(`${t}-tab`).style.display = t === tab ? 'block' : 'none';
        document.querySelector(`[data-tab="${t}"]`).classList.toggle('active', t === tab);
    });
}

async function uploadText() {
    const text = document.getElementById('screenplay-text').value.trim();
    if (!text) { showToast('Please paste some screenplay text first.', 'error'); return; }
    try {
        showLoading('Uploading text…');
        const fd = new FormData();
        fd.append('text', text);
        await api('POST', '/upload/text', fd, true);
        showToast('Screenplay text uploaded.', 'success');
    } catch (e) {
        showToast(`Upload failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

async function uploadFile() {
    if (!state.selectedFile) { showToast('No file selected.', 'error'); return; }
    try {
        showLoading('Uploading file…');
        const fd = new FormData();
        fd.append('file', state.selectedFile);
        const res = await api('POST', '/upload/file', fd, true);
        showToast(`File uploaded. Extracted ${res.text_length} characters.`, 'success');
    } catch (e) {
        showToast(`Upload failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

function loadExample(id) {
    const text = EXAMPLE_SCREENPLAYS[id];
    if (!text) return;
    document.getElementById('screenplay-text').value = text;
    switchUploadTab('text');
    showToast('Example screenplay loaded.', 'info');
}

// ─────────────────────────────────────────────────────────────────────────────
// Parse & Generate
// ─────────────────────────────────────────────────────────────────────────────

async function parseScreenplay() {
    try {
        showLoading('Parsing screenplay with AI…');
        const res = await api('POST', '/parse');
        state.shots = res.shots || [];
        state.characters = res.characters.map(name => ({ name, reference_type: null }));
        if (res.title) {
            document.getElementById('project-title').textContent = res.title;
        }
        renderShots();
        renderCharacters();
        showToast(`Parsed ${res.shots.length} shots across ${res.characters.length} characters.`, 'success');
        showSection('characters');
    } catch (e) {
        showToast(`Parse failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

async function generateStoryboard() {
    try {
        showLoading('Generating storyboard panels… This may take a few minutes.');
        const res = await api('POST', '/generate');
        await loadProject();
        showToast(`Generated ${res.shots_generated} panels.`, 'success');
        showSection('storyboard');
    } catch (e) {
        showToast(`Generation failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Render: Shots
// ─────────────────────────────────────────────────────────────────────────────

function renderShots() {
    const grid = document.getElementById('shots-grid');
    if (!state.shots || state.shots.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <p>No storyboard yet. Upload a screenplay to get started.</p>
                <button class="btn-primary" onclick="app.showSection('upload')">Upload Screenplay</button>
            </div>`;
        return;
    }
    grid.innerHTML = state.shots.map(shot => renderShotCard(shot)).join('');
}

function renderShotCard(shot) {
    const imgSrc = shot.image_path
        ? (() => {
            const norm = shot.image_path.replace(/\\/g, '/');
            const idx  = norm.indexOf('outputs/');
            return idx !== -1 ? `/outputs/${norm.slice(idx + 8)}` : null;
        })()
        : null;
    const imgTag = imgSrc
        ? `<img class="shot-image" src="${imgSrc}" alt="Shot ${shot.shot_number}" loading="lazy"
               onerror="this.src='/static/placeholder.png'">`
        : `<div class="shot-image" style="display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#e0e0e8,#c8c8d8);font-size:2rem;">🎬</div>`;

    const chars = (shot.characters || []).join(', ') || '—';
    return `
        <div class="shot-card" data-shot="${shot.shot_number}">
            ${imgTag}
            <div class="shot-info">
                <div class="shot-number">SHOT ${shot.shot_number}</div>
                <div class="shot-meta">
                    ${shot.shot_type || '—'} · ${(shot.camera_angle || '—').replace(/-/g, ' ')} · ${shot.mood || '—'}
                </div>
                <div class="shot-meta" style="font-weight:500;">CHARS: ${chars}</div>
                <div class="shot-action">${shot.action || ''}</div>
                <div class="shot-actions">
                    <button class="btn-secondary" onclick="app.openEditModal(${shot.shot_number})">Edit</button>
                    <button class="btn-secondary" onclick="app.showAlternatives(${shot.shot_number})">Alternatives</button>
                </div>
            </div>
        </div>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Render: Characters
// ─────────────────────────────────────────────────────────────────────────────

function renderCharacters() {
    const grid = document.getElementById('characters-list');
    if (!state.characters || state.characters.length === 0) {
        grid.innerHTML = `<div class="empty-state"><p>No characters yet. Parse a screenplay first.</p></div>`;
        return;
    }
    grid.innerHTML = state.characters.map(char => renderCharacterCard(char)).join('');
}

function renderCharacterCard(char) {
    const imgSrc = char.reference_image_path
        ? (() => {
            const norm = char.reference_image_path.replace(/\\/g, '/');
            const idx  = norm.indexOf('uploads/');
            return idx !== -1 ? `/uploads/${norm.slice(idx + 8)}` : null;
        })()
        : null;
    const status = char.reference_type || 'pending';

    const sketchOptions = (window._defaultSketches || []).map(s =>
        `<option value="${s.id}">${s.name}</option>`
    ).join('');

    const imgEl = imgSrc
        ? `<img class="character-reference" src="${imgSrc}" alt="${char.name}"
               onerror="this.style.display='none'">`
        : `<div class="character-reference" style="display:flex;align-items:center;justify-content:center;font-size:3rem;background:linear-gradient(135deg,#e0e0e8,#c8c8d8);">👤</div>`;

    return `
        <div class="character-card" id="char-${char.name}">
            <div class="character-header">
                <div class="character-name">${char.name}</div>
                <span class="character-status">${status}</span>
            </div>
            ${imgEl}
            <div class="character-options">
                <select id="ref-type-${char.name}" onchange="app.onReferenceTypeChange('${char.name}')">
                    <option value="">Choose reference type…</option>
                    <option value="uploaded" ${status==='uploaded'?'selected':''}>Upload Image</option>
                    <option value="generated" ${status==='generated'?'selected':''}>Describe Appearance</option>
                    <option value="default" ${status==='default'?'selected':''}>Default Sketch</option>
                </select>

                <div id="upload-ref-${char.name}" class="ref-sub" style="display:none;">
                    <input type="file" id="ref-file-${char.name}" accept=".png,.jpg,.jpeg,.webp">
                </div>
                <div id="desc-ref-${char.name}" class="ref-sub" style="display:none;">
                    <textarea id="ref-desc-${char.name}" placeholder="Describe the character's appearance…"></textarea>
                </div>
                <div id="sketch-ref-${char.name}" class="ref-sub" style="display:none;">
                    <select id="ref-sketch-${char.name}">
                        <option value="">Choose sketch…</option>${sketchOptions}
                    </select>
                </div>

                <button class="btn-primary" onclick="app.saveCharacter('${char.name}')">Save Reference</button>
            </div>
        </div>`;
}

function onReferenceTypeChange(charName) {
    const val = document.getElementById(`ref-type-${charName}`).value;
    ['upload-ref', 'desc-ref', 'sketch-ref'].forEach(prefix => {
        document.getElementById(`${prefix}-${charName}`).style.display = 'none';
    });
    if (val === 'uploaded') document.getElementById(`upload-ref-${charName}`).style.display = 'block';
    if (val === 'generated') document.getElementById(`desc-ref-${charName}`).style.display = 'block';
    if (val === 'default') document.getElementById(`sketch-ref-${charName}`).style.display = 'block';
}

// ─────────────────────────────────────────────────────────────────────────────
// Character: Save reference
// ─────────────────────────────────────────────────────────────────────────────

async function saveCharacter(charName) {
    const refType = document.getElementById(`ref-type-${charName}`).value;
    if (!refType) { showToast('Please choose a reference type.', 'error'); return; }

    try {
        showLoading(`Saving reference for ${charName}…`);
        const fd = new FormData();
        fd.append('name', charName);
        fd.append('reference_type', refType);

        if (refType === 'uploaded') {
            const fileInput = document.getElementById(`ref-file-${charName}`);
            if (!fileInput.files[0]) { showToast('Please select an image file.', 'error'); hideLoading(); return; }
            fd.append('file', fileInput.files[0]);
        } else if (refType === 'generated') {
            const desc = document.getElementById(`ref-desc-${charName}`).value.trim();
            if (!desc) { showToast('Please enter a description.', 'error'); hideLoading(); return; }
            fd.append('description', desc);
        } else if (refType === 'default') {
            const sketchId = document.getElementById(`ref-sketch-${charName}`).value;
            if (!sketchId) { showToast('Please choose a sketch.', 'error'); hideLoading(); return; }
            fd.append('sketch_id', sketchId);
        }

        const res = await api('POST', '/characters', fd, true);
        const idx = state.characters.findIndex(c => c.name === charName);
        if (idx !== -1) state.characters[idx] = res.character;
        else state.characters.push(res.character);
        renderCharacters();
        showToast(`Reference saved for ${charName}.`, 'success');
    } catch (e) {
        showToast(`Failed to save: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shot: Edit modal
// ─────────────────────────────────────────────────────────────────────────────

const SHOT_TYPES = ['wide', 'medium', 'close-up', 'extreme-close-up', 'over-the-shoulder', 'point-of-view'];
const CAMERA_ANGLES = ["eye-level", "high-angle", "low-angle", "bird's-eye", "worm's-eye", "dutch-angle"];
const MOODS = ['happy', 'sad', 'tense', 'dramatic', 'peaceful', 'action', 'romantic', 'mysterious'];

function openEditModal(shotNumber) {
    const shot = state.shots.find(s => s.shot_number === shotNumber);
    if (!shot) return;

    const typeOpts = SHOT_TYPES.map(t => `<option ${shot.shot_type===t?'selected':''}>${t}</option>`).join('');
    const angleOpts = CAMERA_ANGLES.map(a => `<option ${shot.camera_angle===a?'selected':''}>${a}</option>`).join('');
    const moodOpts = MOODS.map(m => `<option ${shot.mood===m?'selected':''}>${m}</option>`).join('');

    document.getElementById('modal-body').innerHTML = `
        <h2 style="margin-bottom:1.5rem;">Edit Shot ${shotNumber}</h2>
        <label>Action Description
            <textarea id="edit-action" style="width:100%;min-height:80px;margin:0.5rem 0 1rem;padding:0.75rem;
                border:1px solid rgba(0,0,0,0.1);border-radius:8px;font-size:0.95rem;">${shot.action || ''}</textarea>
        </label>
        <label>Shot Type
            <select id="edit-type" style="width:100%;margin:0.5rem 0 1rem;padding:0.75rem;
                border:1px solid rgba(0,0,0,0.1);border-radius:8px;font-size:0.95rem;">
                ${typeOpts}
            </select>
        </label>
        <label>Camera Angle
            <select id="edit-angle" style="width:100%;margin:0.5rem 0 1rem;padding:0.75rem;
                border:1px solid rgba(0,0,0,0.1);border-radius:8px;font-size:0.95rem;">
                ${angleOpts}
            </select>
        </label>
        <label>Mood
            <select id="edit-mood" style="width:100%;margin:0.5rem 0 1rem;padding:0.75rem;
                border:1px solid rgba(0,0,0,0.1);border-radius:8px;font-size:0.95rem;">
                ${moodOpts}
            </select>
        </label>
        <button class="btn-primary btn-large" onclick="app.regenerateShot(${shotNumber})"
            style="width:100%;margin-top:0.5rem;">Regenerate Shot</button>`;

    document.getElementById('shot-modal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('shot-modal').style.display = 'none';
}

async function regenerateShot(shotNumber) {
    try {
        closeModal();
        showLoading(`Regenerating shot ${shotNumber}…`);
        const fd = new FormData();
        fd.append('action', document.getElementById('edit-action').value);
        fd.append('shot_type', document.getElementById('edit-type').value);
        fd.append('camera_angle', document.getElementById('edit-angle').value);
        fd.append('mood', document.getElementById('edit-mood').value);
        const res = await api('POST', `/shots/${shotNumber}/regenerate`, fd, true);
        const idx = state.shots.findIndex(s => s.shot_number === shotNumber);
        if (idx !== -1) state.shots[idx] = res.shot;
        renderShots();
        showToast(`Shot ${shotNumber} regenerated.`, 'success');
    } catch (e) {
        showToast(`Regeneration failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shot: Alternatives
// ─────────────────────────────────────────────────────────────────────────────

async function showAlternatives(shotNumber) {
    try {
        showLoading('Generating alternative suggestions…');
        const res = await api('GET', `/shots/${shotNumber}/alternatives`);
        hideLoading();

        const suggestions = res.suggestions || [];
        if (suggestions.length === 0) {
            showToast('No alternative suggestions generated.', 'info'); return;
        }

        const sugHtml = suggestions.map((s, i) => `
            <div style="border:1px solid rgba(0,0,0,0.1);border-radius:10px;padding:1rem;margin-bottom:1rem;">
                <p style="font-weight:600;margin-bottom:0.5rem;">Option ${i + 1}</p>
                <p><strong>Type:</strong> ${s.shot_type} · <strong>Angle:</strong> ${s.camera_angle} · <strong>Mood:</strong> ${s.mood}</p>
                <p style="font-size:0.9rem;color:#5c5c7a;margin-top:0.5rem;">${s.reason}</p>
                <button class="btn-secondary" onclick="app.applyAlternative(${shotNumber},'${s.shot_type}','${s.camera_angle}','${s.mood}')"
                    style="margin-top:0.75rem;">Apply &amp; Regenerate</button>
            </div>`).join('');

        document.getElementById('modal-body').innerHTML =
            `<h2 style="margin-bottom:1.5rem;">Alternatives for Shot ${shotNumber}</h2>${sugHtml}`;
        document.getElementById('shot-modal').style.display = 'flex';
    } catch (e) {
        hideLoading();
        showToast(`Could not fetch alternatives: ${e.message}`, 'error');
    }
}

async function applyAlternative(shotNumber, shotType, cameraAngle, mood) {
    try {
        closeModal();
        showLoading(`Applying alternative to shot ${shotNumber}…`);
        const fd = new FormData();
        fd.append('shot_type', shotType);
        fd.append('camera_angle', cameraAngle);
        fd.append('mood', mood);
        const res = await api('POST', `/shots/${shotNumber}/regenerate`, fd, true);
        const idx = state.shots.findIndex(s => s.shot_number === shotNumber);
        if (idx !== -1) state.shots[idx] = res.shot;
        renderShots();
        showToast(`Shot ${shotNumber} updated with alternative.`, 'success');
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Assemble, Export, Share
// ─────────────────────────────────────────────────────────────────────────────

async function assembleStoryboard() {
    try {
        showLoading('Assembling storyboard sheet…');
        const res = await api('POST', '/assemble');
        showToast('Storyboard sheet assembled.', 'success');
        console.log('Sheet path:', res.sheet_path);
    } catch (e) {
        showToast(`Assembly failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

async function exportPDF() {
    try {
        showLoading('Exporting PDF…');
        const res = await api('POST', '/export/pdf');
        showToast('PDF exported! Starting download…', 'success');
        window.location.href = `/api/export/${res.export_id}/download`;
    } catch (e) {
        showToast(`PDF export failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

async function exportPPTX() {
    try {
        showLoading('Exporting PowerPoint…');
        const res = await api('POST', '/export/pptx');
        showToast('PPTX exported! Starting download…', 'success');
        window.location.href = `/api/export/${res.export_id}/download`;
    } catch (e) {
        showToast(`PPTX export failed: ${e.message}`, 'error');
    } finally {
        hideLoading();
    }
}

async function shareStoryboard() {
    try {
        const res = await api('POST', '/share');
        const shareUrl = `${window.location.origin}/share/${res.project_id}`;
        await navigator.clipboard.writeText(shareUrl);
        showToast('Shareable link copied to clipboard!', 'success');
    } catch (e) {
        showToast(`Share failed: ${e.message}`, 'error');
    }
}


// ─────────────────────────────────────────────────────────────────────────────
// File input wiring
// ─────────────────────────────────────────────────────────────────────────────

function wireFileInputs() {
    // File upload
    const fileInput = document.getElementById('file-input');
    const dropZone = document.getElementById('file-drop-zone');

    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', e => {
        state.selectedFile = e.target.files[0];
        if (state.selectedFile) {
            dropZone.innerHTML = `
                <p>✔ ${state.selectedFile.name}</p>
                <span class="hint">(${(state.selectedFile.size / 1024).toFixed(1)} KB)</span>`;
            document.getElementById('upload-file-btn').disabled = false;
        }
    });

    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', e => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        state.selectedFile = e.dataTransfer.files[0];
        if (state.selectedFile) {
            dropZone.innerHTML = `<p>✔ ${state.selectedFile.name}</p>`;
            document.getElementById('upload-file-btn').disabled = false;
        }
    });

    // Close modal on background click
    document.getElementById('shot-modal').addEventListener('click', e => {
        if (e.target.id === 'shot-modal') closeModal();
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────

async function init() {
    wireFileInputs();

    // Load template documentation
    try {
        const tpl = await api('GET', '/template');
        document.getElementById('template-display').textContent = tpl.template;
    } catch (_) {}

    // Load default sketches
    try {
        const sk = await api('GET', '/default-sketches');
        window._defaultSketches = sk.sketches || [];
    } catch (_) {}

    // Load project
    await loadProject();

    // Restore app view if shots already exist
    if (state.shots.length > 0) {
        showSection('storyboard');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Public app namespace (used by inline onclick handlers)
// ─────────────────────────────────────────────────────────────────────────────

const app = {
    showSection,
    showLanding,
    switchUploadTab,
    uploadText,
    uploadFile,
    loadExample,
    parseScreenplay,
    generateStoryboard,
    saveCharacter,
    onReferenceTypeChange,
    openEditModal,
    closeModal,
    regenerateShot,
    showAlternatives,
    applyAlternative,
    assembleStoryboard,
    exportPDF,
    exportPPTX,
    shareStoryboard,
};

document.addEventListener('DOMContentLoaded', init);
