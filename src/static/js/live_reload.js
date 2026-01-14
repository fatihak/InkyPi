// Live Reload JavaScript for Development Mode

const LIVE_RELOAD_PATHS = ["/dev/enhanced-preview/", "/dev/dashboard"];

class LiveReloadManager {
  constructor() {
    this.socket = null;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start with 1 second
    this.pingInterval = null;
    this.reloadNotification = null;

    if (this.isLiveReloadEnabled()) {
      this.init();
    }
  }

  isLiveReloadEnabled() {
    return LIVE_RELOAD_PATHS.some((path) =>
      window.location.pathname.includes(path)
    );
  }

  init() {
    this.connect();
  }

  connect() {
    try {
      // Connect to Socket.IO server
      this.socket = io({
        transports: ["websocket", "polling"],
        upgrade: true,
        rememberUpgrade: true,
      });

      this.socket.on("connect", () => {
        console.log("🔄 Live reload connected");
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.startPing();
        this.showNotification("Live reload active", "success");
      });

      this.socket.on("disconnect", () => {
        console.log("❌ Live reload disconnected");
        this.isConnected = false;
        this.stopPing();
        this.showNotification("Live reload disconnected", "warning");
      });

      this.socket.on("connected", (data) => {
        console.log("✅ Server confirms connection:", data.message);
      });

      this.socket.on("reload", (data) => {
        console.log("🔄 Reload signal received:", data);
        this.handleReload(data);
      });

      this.socket.on("pong", (data) => {
        // Ping-pong successful, connection is alive
        console.debug("🏓 Ping-pong successful");
      });

      this.socket.on("connect_error", (error) => {
        console.error("❌ Live reload connection error:", error);
        this.isConnected = false;
        this.handleConnectionError();
      });
    } catch (error) {
      console.error("❌ Failed to initialize live reload:", error);
    }
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
    this.stopPing();
    this.isConnected = false;
  }

  handleConnectionError() {
    this.isConnected = false;
    this.stopPing();

    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * this.reconnectAttempts;

      console.log(
        `🔄 Attempting reconnect ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`
      );

      setTimeout(() => {
        this.connect();
      }, delay);
    } else {
      console.error("❌ Max reconnection attempts reached");
      this.showNotification("Live reload connection failed", "error");
    }
  }

  startPing() {
    // Send ping every 30 seconds to keep connection alive
    this.pingInterval = setInterval(() => {
      if (this.isConnected && this.socket) {
        this.socket.emit("ping");
      }
    }, 30000);
  }

  stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  handleReload(data) {
    const timestamp = new Date(data.timestamp).toLocaleTimeString();
    const source = data.source || "file change";
    const file = data.file || "unknown file";

    console.log(`🔄 Reloading due to ${source}: ${file} at ${timestamp}`);

    // Show notification
    this.showNotification(`Reloading: ${file}`, "info");

    // Reload the page after a short delay to show the notification
    setTimeout(() => {
      window.location.reload();
    }, 500);
  }

  showNotification(message, type = "info") {
    // Remove existing notification
    if (this.reloadNotification) {
      this.reloadNotification.remove();
    }

    // Create notification
    const notification = document.createElement("div");
    notification.style.cssText = `
            position: fixed;
            top: 50px;
            right: 10px;
            z-index: 10000;
            padding: 12px 16px;
            border-radius: 4px;
            font-family: Arial, sans-serif;
            font-size: 14px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            max-width: 300px;
        `;

    // Set color based on type
    const colors = {
      success: "#d4edda",
      error: "#f8d7da",
      warning: "#fff3cd",
      info: "#d1ecf1",
    };

    const textColors = {
      success: "#155724",
      error: "#721c24",
      warning: "#856404",
      info: "#0c5460",
    };

    notification.style.background = colors[type] || colors.info;
    notification.style.color = textColors[type] || textColors.info;
    notification.textContent = message;

    document.body.appendChild(notification);
    this.reloadNotification = notification;

    // Auto-remove after 3 seconds
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, 3000);
  }
}

// Initialize live reload when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  window.liveReloadManager = new LiveReloadManager();
});

// Clean up on page unload
window.addEventListener("beforeunload", () => {
  if (window.liveReloadManager) {
    window.liveReloadManager.disconnect();
  }
});
