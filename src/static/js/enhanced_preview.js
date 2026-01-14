class EnhancedDevTools {
  constructor() {
    this.currentView = "html";
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.setupKeyboardShortcuts();
  }

  setupEventListeners() {
    // View toggles
    document
      .getElementById("html-view-btn")
      .addEventListener("click", () => this.setView("html"));
    document
      .getElementById("side-by-side-btn")
      .addEventListener("click", () => this.setView("side-by-side"));
    document
      .getElementById("preview-html-btn")
      .addEventListener("click", () => this.setPreviewView("html"));
    document
      .getElementById("preview-comparison-btn")
      .addEventListener("click", () => this.setPreviewView("comparison"));
  }

  setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey) {
        switch (e.key) {
          case "s":
            e.preventDefault();
            this.setView(this.currentView === "html" ? "side-by-side" : "html");
            break;
          case "d":
            e.preventDefault();
            this.toggleDevTools();
            break;
        }
      }
    });
  }

  setView(view) {
    this.currentView = view;

    // Update UI buttons
    document
      .querySelectorAll("#html-view-btn, #side-by-side-btn")
      .forEach((btn) => {
        btn.classList.remove("active");
      });

    // Update preview area
    const htmlPreview = document.getElementById("html-preview");
    const sideBySideView = document.getElementById("side-by-side-view");

    if (view === "html") {
      document.getElementById("html-view-btn").classList.add("active");
      htmlPreview.style.display = "block";
      sideBySideView.classList.remove("active");
    } else if (view === "side-by-side") {
      document.getElementById("side-by-side-btn").classList.add("active");
      htmlPreview.style.display = "none";
      sideBySideView.classList.add("active");
      this.loadScreenshot();
    }
  }

  setPreviewView(view) {
    // Sync preview view toggle buttons
    document
      .querySelectorAll("#preview-html-btn, #preview-comparison-btn")
      .forEach((btn) => {
        btn.classList.remove("active");
      });

    if (view === "html") {
      document.getElementById("preview-html-btn").classList.add("active");
      this.setView("html");
    } else if (view === "comparison") {
      document.getElementById("preview-comparison-btn").classList.add("active");
      this.setView("side-by-side");
    }
  }

  loadScreenshot() {
    const container = document.getElementById("screenshot-container");
    container.innerHTML = '<div class="loading-spinner"></div>';

    fetch(`/dev/screenshot/{{ plugin_id }}`)
      .then((response) => response.json())
      .then((data) => {
        if (data.screenshot) {
          container.innerHTML = `<img src="${data.screenshot}" style="max-width: 100%; max-height: 100%; border-radius: 4px;" />`;
        } else {
          container.innerHTML =
            '<div style="color: #718096; text-align: center;">Unable to load screenshot</div>';
        }
      })
      .catch((error) => {
        console.error("Error loading screenshot:", error);
        container.innerHTML =
          '<div style="color: #f56565; text-align: center;">Error loading screenshot</div>';
      });
  }

  refreshPlugin() {
    if (window.liveReloadManager) {
      window.liveReloadManager.requestManualReload();
    } else {
      window.location.reload();
    }
  }
}

// Initialize enhanced dev tools when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  window.enhancedDevTools = new EnhancedDevTools();
});
