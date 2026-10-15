/**
 * Live Preview Manager for InkyPi Plugin Settings
 *
 * Generates a live preview image when plugin settings change,
 * without pushing to the physical display.
 *
 * Usage in a plugin's settings.html:
 *
 *   <!-- Add preview widget (use any unique prefix for IDs) -->
 *   <div id="preview-widget"></div>
 *
 *   <script>
 *   document.addEventListener('DOMContentLoaded', () => {
 *       PreviewManager.init('your_plugin_id');
 *   });
 *   </script>
 *
 * The widget auto-renders into #preview-widget and listens to all
 * form inputs for changes. Call PreviewManager.refresh() after
 * dynamically adding form elements (e.g. new list items).
 */
const PreviewManager = (() => {
    let timeout = null;
    let pluginId = null;
    let requiredFields = {};
    // Only one request in flight; changes made meanwhile trigger a single rerun
    // with the latest form state once it finishes.
    let inFlight = false;
    let rerun = false;
    // Files the server already saved for a preview, keyed by field + file identity,
    // so later previews send the saved path instead of uploading the file again.
    const uploadedPaths = new Map();

    function fileKey(field, file) {
        return `${field}|${file.name}|${file.size}|${file.lastModified}`;
    }

    function buildFormData(form) {
        const formData = new FormData();
        const pendingUploads = {};
        for (const [field, value] of new FormData(form).entries()) {
            if (value instanceof File && value.name) {
                const key = fileKey(field, value);
                if (uploadedPaths.has(key)) {
                    formData.append(field, uploadedPaths.get(key));
                } else {
                    formData.append(field, value);
                    (pendingUploads[field] = pendingUploads[field] || []).push(key);
                }
            } else {
                formData.append(field, value);
            }
        }
        formData.append('plugin_id', pluginId);
        return { formData, pendingUploads };
    }

    function rememberUploads(pendingUploads, uploadedFiles) {
        for (const [field, keys] of Object.entries(pendingUploads)) {
            const paths = [].concat(uploadedFiles?.[field] ?? []);
            keys.forEach((key, i) => {
                if (paths[i]) uploadedPaths.set(key, paths[i]);
            });
        }
    }

    function render(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.innerHTML = `
            <div class="form-group">
                <label class="form-label">Preview</label>
                <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 200px; max-width: 45%;">
                        <p style="margin: 0 0 5px 0; font-size: 12px; color: var(--text-muted, #666);">Current</p>
                        <div style="border: 1px solid var(--border-color, #ccc); border-radius: 8px; overflow: hidden; background: #f5f5f5;">
                            <img id="preview-current"
                                 src="/static/images/current_image.png?${Date.now()}"
                                 alt="Current Display"
                                 style="width: 100%; display: block;"
                                 onerror="this.style.display='none'">
                        </div>
                    </div>
                    <div style="flex: 1; min-width: 200px; max-width: 45%;">
                        <p style="margin: 0 0 5px 0; font-size: 12px; color: var(--text-muted, #666);">Preview <span id="preview-status" style="font-style: italic;"></span></p>
                        <div style="border: 2px dashed var(--primary-color, #4CAF50); border-radius: 8px; overflow: hidden; background: #f5f5f5;">
                            <img id="preview-image"
                                 alt="Preview with new settings"
                                 style="width: 100%; display: block;">
                        </div>
                    </div>
                </div>
            </div>`;
    }

    function checkRequired() {
        const form = document.querySelector('form');
        if (!form) return null;
        for (const [field, label] of Object.entries(requiredFields)) {
            if (field.endsWith('[]')) {
                const elements = form.querySelectorAll(`[name="${field}"]`);
                const hasValue = Array.from(elements).some(el => el.value.trim());
                if (!hasValue) return label;
            } else {
                const el = form.querySelector(`[name="${field}"]`);
                if (!el || !el.value.trim()) return label;
            }
        }
        return null;
    }

    function generate() {
        clearTimeout(timeout);
        timeout = setTimeout(requestPreview, 500);
    }

    async function requestPreview() {
        if (inFlight) {
            rerun = true;
            return;
        }

        const statusEl = document.getElementById('preview-status');
        const previewImg = document.getElementById('preview-image');
        if (!statusEl || !previewImg) return;

        const missingLabel = checkRequired();
        if (missingLabel) {
            previewImg.style.display = 'none';
            statusEl.textContent = `(${missingLabel})`;
            return;
        }

        const form = document.querySelector('form');
        if (!form) return;

        statusEl.textContent = '(loading...)';
        const { formData, pendingUploads } = buildFormData(form);

        inFlight = true;
        try {
            const response = await fetch('/preview', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            if (result.success) rememberUploads(pendingUploads, result.uploaded_files);
            if (rerun) return; // stale: newer settings are rendered next
            if (result.success) {
                previewImg.src = result.image;
                previewImg.style.display = 'block';
                statusEl.textContent = '';
            } else {
                previewImg.style.display = 'none';
                const err = result.error || '';
                if (err.includes('Chromium') || err.includes('NoneType')) {
                    statusEl.textContent = '(needs Chromium — works on Pi)';
                } else if (err.includes('required')) {
                    // Missing required field — show friendly hint
                    const field = err.match(/(\w+) is required/i);
                    statusEl.textContent = field ? `(no ${field[1].toLowerCase()} set yet)` : '(fill in required fields)';
                } else {
                    // Show the actual error (strip "An error occurred: " prefix)
                    const msg = err.replace(/^An error occurred:\s*/i, '');
                    statusEl.textContent = msg ? `(${msg})` : '(preview unavailable)';
                }
                console.error('Preview error:', err);
            }
        } catch (err) {
            if (rerun) return;
            previewImg.style.display = 'none';
            statusEl.textContent = '(preview unavailable)';
            console.error('Preview error:', err);
        } finally {
            inFlight = false;
            if (rerun) {
                rerun = false;
                requestPreview();
            }
        }
    }

    function listenToForm() {
        document.querySelectorAll('form select, form input, form textarea').forEach(el => {
            if (el.dataset.previewBound) return;
            el.addEventListener('change', generate);
            el.addEventListener('input', generate);
            el.dataset.previewBound = '1';
        });
    }

    return {
        /**
         * Initialize preview for a plugin.
         * @param {string} id - The plugin_id (e.g. 'clock', 'countdown')
         * @param {Object} [options] - Configuration options
         * @param {Object} [options.required] - Map of field names to hint messages for client-side validation
         * @param {string} [options.containerId='preview-widget'] - ID of the container element
         */
        init(id, options = {}) {
            pluginId = id;
            requiredFields = options.required || {};
            render(options.containerId || 'preview-widget');
            listenToForm();
            generate();
        },

        /** Trigger a preview refresh (call after dynamically adding form elements) */
        refresh() {
            listenToForm();
            generate();
        },

        /** Refresh the "current" image (call after a successful Update Now) */
        refreshCurrent() {
            const img = document.getElementById('preview-current');
            if (img) img.src = '/static/images/current_image.png?' + Date.now();
        }
    };
})();
