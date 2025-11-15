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
        const stored = localStorage.getItem(THEME_KEY);
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
    function setTheme(theme) {
        const html = document.documentElement;

        if (theme === DARK_THEME) {
            html.setAttribute('data-theme', DARK_THEME);
        } else {
            html.removeAttribute('data-theme');
        }

        localStorage.setItem(THEME_KEY, theme);
        updateToggleButtonText(theme);
    }

    /**
     * Update the toggle button hover text based on current theme
     * @param {string} theme - The current theme
     */
    function updateToggleButtonText(theme) {
        const toggleButton = document.querySelector('.dark-mode-toggle');
        if (toggleButton) {
            const hoverText = theme === DARK_THEME ? 'Toggle Light Mode' : 'Toggle Dark Mode';
            toggleButton.setAttribute('data-hover-text', hoverText);
        }
    }

    /**
     * Toggle between light and dark themes
     */
    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme');
        const newTheme = current === DARK_THEME ? LIGHT_THEME : DARK_THEME;
        setTheme(newTheme);
    }

    /**
     * Initialize dark mode on page load
     */
    function initialize() {
        const theme = getCurrentTheme();
        setTheme(theme);

        // Add click listener to the dark mode toggle button
        const toggleButton = document.querySelector('.dark-mode-toggle');
        if (toggleButton) {
            toggleButton.addEventListener('click', function (e) {
                e.preventDefault();
                toggleTheme();
            });
        }

        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                // Only auto-switch if user hasn't set a preference
                if (!localStorage.getItem(THEME_KEY)) {
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
