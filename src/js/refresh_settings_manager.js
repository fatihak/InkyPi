/**
 * RefreshSettingsManager - Unified handler for refresh settings across the application
 * Handles: modal display, prepopulation, form submission, and validation
 */
class RefreshSettingsManager {
    /**
     * @param {string} modalId - ID of the modal element
     * @param {string} prefix - Prefix for form field IDs (e.g., 'add', 'edit', 'modal')
     */
    constructor(modalId, prefix) {
        this.modalId = modalId;
        this.prefix = prefix;
        this.currentData = null; // Store current plugin data for submission

        // Cache DOM elements
        this.modal = null;
        this.radioInterval = null;
        this.radioScheduled = null;
        this.inputInterval = null;
        this.inputScheduled = null;
        this.selectUnit = null;
        this.groupInterval = null;
        this.groupScheduled = null;

        this.initialized = false;
    }

    /**
     * Initialize the manager - must be called after DOM is loaded
     */
    init() {
        if (this.initialized) return;

        this.modal = document.getElementById(this.modalId);
        if (!this.modal) {
            console.error(`RefreshSettingsManager: Modal '${this.modalId}' not found`);
            return;
        }

        // Cache form elements
        this.radioInterval = document.getElementById(`${this.prefix}-refresh-interval`);
        this.radioScheduled = document.getElementById(`${this.prefix}-refresh-scheduled`);
        this.inputInterval = document.getElementById(`${this.prefix}-interval`);
        this.inputScheduled = document.getElementById(`${this.prefix}-scheduled`);
        this.selectUnit = document.getElementById(`${this.prefix}-unit`);
        this.groupInterval = document.getElementById(`${this.prefix}-group-interval`);
        this.groupScheduled = document.getElementById(`${this.prefix}-group-scheduled`);

        if (!this.radioInterval || !this.radioScheduled) {
            console.error(`RefreshSettingsManager: Form elements with prefix '${this.prefix}' not found`);
            return;
        }

        this.setupInteractiveHandlers();
        this.initialized = true;
    }

    /**
     * Set up interactive click handlers for radio groups
     */
    setupInteractiveHandlers() {
        const activateGroup = (radio, input) => {
            radio.checked = true;
            setTimeout(() => input.focus(), 0);
        };

        // Click anywhere in interval group → activate interval
        if (this.groupInterval) {
            this.groupInterval.addEventListener('click', (e) => {
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
                activateGroup(this.radioInterval, this.inputInterval);
            });
        }

        // Click anywhere in scheduled group → activate scheduled
        if (this.groupScheduled) {
            this.groupScheduled.addEventListener('click', (e) => {
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
                activateGroup(this.radioScheduled, this.inputScheduled);
            });
        }

        // Clicking radio buttons → focus inputs
        this.radioInterval.addEventListener('click', () => activateGroup(this.radioInterval, this.inputInterval));
        this.radioScheduled.addEventListener('click', () => activateGroup(this.radioScheduled, this.inputScheduled));

        // Focusing inputs → auto-select their radio
        this.inputInterval.addEventListener('focus', () => (this.radioInterval.checked = true));
        this.inputScheduled.addEventListener('focus', () => (this.radioScheduled.checked = true));
        if (this.selectUnit) {
            this.selectUnit.addEventListener('focus', () => (this.radioInterval.checked = true));
        }
    }

    /**
     * Convert seconds to appropriate unit and value
     * @param {number} seconds - Seconds to convert
     * @returns {{value: number, unit: string}}
     */
    secondsToUnit(seconds) {
        if (seconds % 86400 === 0) {
            return { value: seconds / 86400, unit: 'day' };
        }
        if (seconds % 3600 === 0) {
            return { value: seconds / 3600, unit: 'hour' };
        }
        if (seconds % 60 === 0) {
            return { value: seconds / 60, unit: 'minute' };
        }
        // Default to minutes if not evenly divisible
        return { value: Math.round(seconds / 60), unit: 'minute' };
    }

    /**
     * Prepopulate form with existing refresh settings
     * @param {Object} refreshSettings - Refresh settings object {interval: number} or {scheduled: string}
     */
    prepopulate(refreshSettings) {
        if (!refreshSettings) return;

        if (refreshSettings.interval) {
            const { value, unit } = this.secondsToUnit(refreshSettings.interval);
            this.radioInterval.checked = true;
            this.inputInterval.value = value;
            this.selectUnit.value = unit;
        } else if (refreshSettings.scheduled) {
            this.radioScheduled.checked = true;
            this.inputScheduled.value = refreshSettings.scheduled;
        }
    }

    /**
     * Get current form values as an object
     * @returns {{refreshType: string, interval?: string, unit?: string, refreshTime?: string}}
     */
    getFormData() {
        const refreshType = document.querySelector(`input[name="refreshType"]:checked`)?.value;
        const data = { refreshType };

        if (refreshType === 'interval') {
            data.interval = this.inputInterval.value;
            data.unit = this.selectUnit.value;
        } else if (refreshType === 'scheduled') {
            data.refreshTime = this.inputScheduled.value;
        }

        return data;
    }

    /**
     * Validate form data
     * @param {Object} data - Form data to validate
     * @returns {{valid: boolean, error?: string}}
     */
    validate(data) {
        if (!data.refreshType) {
            return { valid: false, error: 'Please select a refresh type' };
        }

        if (data.refreshType === 'interval') {
            if (!data.interval || data.interval < 1) {
                return { valid: false, error: 'Please enter a valid interval' };
            }
            if (!data.unit) {
                return { valid: false, error: 'Please select a time unit' };
            }
        } else if (data.refreshType === 'scheduled') {
            if (!data.refreshTime) {
                return { valid: false, error: 'Please select a refresh time' };
            }
        }

        return { valid: true };
    }

    /**
     * Open modal with optional prepopulated data
     * @param {Object} data - Optional data for prepopulation
     */
    open(data = null) {
        if (!this.initialized) {
            console.error('RefreshSettingsManager: Not initialized. Call init() first.');
            return;
        }

        this.currentData = data;

        // Prepopulate if data provided
        if (data && data.refreshSettings) {
            this.prepopulate(data.refreshSettings);
        }

        this.modal.style.display = 'block';
    }

    /**
     * Close the modal
     */
    close() {
        if (this.modal) {
            this.modal.style.display = 'none';
        }
    }

    /**
     * Submit the form
     * @param {Function} submitHandler - Async function to handle submission
     *                                   Will be called with (formData, currentData)
     * @returns {Promise<void>}
     */
    async submit(submitHandler) {
        const formData = this.getFormData();
        const validation = this.validate(formData);

        if (!validation.valid) {
            if (window.showResponseModal) {
                showResponseModal('failure', `Error! ${validation.error}`);
            } else {
                alert(validation.error);
            }
            return;
        }

        try {
            await submitHandler(formData, this.currentData);
            this.close();
        } catch (error) {
            console.error('RefreshSettingsManager: Submit error:', error);
            if (window.showResponseModal) {
                showResponseModal('failure', `Error! ${error.message}`);
            } else {
                alert(`Error: ${error.message}`);
            }
        }
    }
}

// Global utility function to create and initialize a manager
function createRefreshSettingsManager(modalId, prefix) {
    const manager = new RefreshSettingsManager(modalId, prefix);
    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => manager.init());
    } else {
        manager.init();
    }
    return manager;
}

