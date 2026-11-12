/**
 * Dark Mode Toggle Script
 * Handles switching between light and dark themes with localStorage persistence
 */

(function initDarkMode() {
    const THEME_KEY = 'inkypi-theme';
    const DARK_THEME = 'dark';
    const LIGHT_THEME = 'light';

    /**
     * Get the current theme preference
     * @returns {string} The current theme ('light' or 'dark')
     */
    function getCurrentTheme() {
        // Check localStorage first
        let stored = null;
        try { stored = localStorage.getItem(THEME_KEY); } catch (e) { /* storage unavailable */ }
        if (stored) {
            return stored;
        }

        // Check system preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return DARK_THEME;
        }

        return LIGHT_THEME;
    }

    /**
     * Set the theme and update DOM
     * @param {string} theme - The theme to set ('light' or 'dark')
     */
    function setTheme(theme, persist) {
        const html = document.documentElement;

        if (theme === DARK_THEME) {
            html.setAttribute('data-theme', DARK_THEME);
        } else {
            html.removeAttribute('data-theme');
        }

        // Only remember an explicit choice, so the OS theme keeps being followed otherwise
        if (persist) {
            try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* storage unavailable */ }
        }
        updateToggleButtonText(theme);
    }

    /**
     * Update the toggle button hover text based on current theme
     * @param {string} theme - The current theme
     */
    function updateToggleButtonText(theme) {
        document.querySelectorAll('.dark-mode-toggle').forEach(toggleButton => {
            // translated in the UI language (t() is defined by partials/head.html)
            const hoverText = typeof t !== 'function'
                ? (theme === DARK_THEME ? 'Switch to light mode' : 'Switch to dark mode')
                : (theme === DARK_THEME ? t('Switch to light mode') : t('Switch to dark mode'));
            toggleButton.setAttribute('data-hover-text', hoverText);
            toggleButton.setAttribute('title', hoverText);
            toggleButton.setAttribute('aria-label', hoverText);
        });
    }

    /**
     * Toggle between light and dark themes
     */
    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme');
        const newTheme = current === DARK_THEME ? LIGHT_THEME : DARK_THEME;
        setTheme(newTheme, true);
    }

    /**
     * Initialize dark mode on page load
     */
    function initialize() {
        const theme = getCurrentTheme();
        setTheme(theme, false);

        // Add click listener to the dark mode toggle button(s)
        document.querySelectorAll('.dark-mode-toggle').forEach(toggleButton => {
            toggleButton.addEventListener('click', function (e) {
                e.preventDefault();
                toggleTheme();
            });
        });

        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                // Only auto-switch if user hasn't set a preference
                let stored = null;
                try { stored = localStorage.getItem(THEME_KEY); } catch (err) { /* ignore */ }
                if (!stored) {
                    setTheme(e.matches ? DARK_THEME : LIGHT_THEME);
                }
            });
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        initialize();
    }

    // Expose toggle function globally for manual calls
    window.toggleDarkMode = toggleTheme;
})();
