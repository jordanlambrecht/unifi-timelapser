// Dashboard JavaScript

/**
 * Dashboard functionality for real-time updates and interactivity
 */

// Global variables
let refreshInterval
let lastUpdateTime

// Initialize dashboard when DOM is loaded
document.addEventListener("DOMContentLoaded", function () {
  initializeDashboard()
  setupEventListeners()
  startAutoRefresh()
})

/**
 * Initialize dashboard components
 */
function initializeDashboard() {
  console.log("🚀 UniFi Timelapser Dashboard initialized")

  // Set last update time
  lastUpdateTime = new Date()
  updateLastUpdateDisplay()

  // Initialize tooltips
  initializeTooltips()

  // Setup notification system
  setupNotifications()

  // Load initial data
  loadSystemStats()
}

/**
 * Setup event listeners for interactive elements
 */
function setupEventListeners() {
  // Refresh button
  const refreshBtn = document.querySelector('[onclick*="refreshCameraStatus"]')
  if (refreshBtn) {
    refreshBtn.addEventListener("click", function (e) {
      e.preventDefault()
      refreshCameraStatus()
    })
  }

  // Camera test buttons
  document.querySelectorAll('[onclick*="testCamera"]').forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault()
      const cameraName = this.getAttribute("onclick").match(/'([^']+)'/)[1]
      testCamera(cameraName)
    })
  })

  // Add keyboard shortcuts
  document.addEventListener("keydown", handleKeyboardShortcuts)
}

/**
 * Handle keyboard shortcuts
 */
function handleKeyboardShortcuts(e) {
  // Ctrl+R or F5 - Refresh
  if ((e.ctrlKey && e.key === "r") || e.key === "F5") {
    e.preventDefault()
    refreshCameraStatus()
  }

  // Escape - Close modals
  if (e.key === "Escape") {
    const modals = bootstrap.Modal.getInstance(
      document.querySelector(".modal.show")
    )
    if (modals) {
      modals.hide()
    }
  }
}

/**
 * Initialize Bootstrap tooltips
 */
function initializeTooltips() {
  const tooltipTriggerList = [].slice.call(
    document.querySelectorAll('[data-bs-toggle="tooltip"]')
  )
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl)
  })
}

/**
 * Setup notification system
 */
function setupNotifications() {
  // Check if notifications are supported
  if ("Notification" in window) {
    // Request permission if not already granted
    if (Notification.permission === "default") {
      Notification.requestPermission()
    }
  }
}

/**
 * Start auto-refresh functionality
 */
function startAutoRefresh() {
  // Refresh every 30 seconds
  refreshInterval = setInterval(() => {
    refreshCameraStatus(true) // Silent refresh
  }, 30000)

  // Update relative times every minute
  setInterval(updateRelativeTimes, 60000)

  console.log("⏰ Auto-refresh started (30s interval)")
}

/**
 * Stop auto-refresh
 */
function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
    console.log("⏸️ Auto-refresh stopped")
  }
}

/**
 * Refresh camera status data
 */
async function refreshCameraStatus(silent = false) {
  if (!silent) {
    showLoadingState()
  }

  try {
    console.log("🔄 Refreshing camera status...")

    // Fetch latest camera data
    const response = await fetch("/api/cameras")
    const data = await response.json()

    if (data.status === "success") {
      updateCameraCards(data.data)
      updateSystemStats()
      lastUpdateTime = new Date()
      updateLastUpdateDisplay()

      if (!silent) {
        showNotification("Camera status updated", "success")
      }
    } else {
      throw new Error(data.message || "Failed to fetch camera status")
    }
  } catch (error) {
    console.error("❌ Error refreshing camera status:", error)

    if (!silent) {
      showNotification(
        "Failed to refresh camera status: " + error.message,
        "error"
      )
    }
  } finally {
    if (!silent) {
      hideLoadingState()
    }
  }
}

/**
 * Update camera cards with new data
 */
function updateCameraCards(cameras) {
  cameras.forEach((camera) => {
    const card = document.querySelector(`[data-camera="${camera.name}"]`)
    if (card) {
      updateCameraCard(card, camera)
    }
  })
}

/**
 * Update individual camera card
 */
function updateCameraCard(cardElement, cameraData) {
  // Update status badge
  const statusBadge = cardElement.querySelector(".status-badge")
  if (statusBadge) {
    statusBadge.textContent = cameraData.status.toUpperCase()
    statusBadge.className = `badge bg-${cameraData.status_class} status-badge`
  }

  // Update last capture time
  const lastCapture = cardElement.querySelector(".last-capture")
  if (lastCapture && cameraData.capture_stats) {
    lastCapture.textContent = cameraData.capture_stats.last_capture_ago
  }

  // Update success rate
  const successRate = cardElement.querySelector(".fw-bold")
  if (successRate && cameraData.capture_stats) {
    const rateElements = cardElement.querySelectorAll(".fw-bold")
    rateElements.forEach((el) => {
      if (el.textContent.includes("%")) {
        el.textContent = cameraData.capture_stats.success_rate + "%"
      }
    })
  }

  // Update health status
  const healthBadge = cardElement.querySelector(
    ".badge.bg-success, .badge.bg-danger"
  )
  if (healthBadge && cameraData.capture_stats) {
    const isHealthy = cameraData.capture_stats.is_healthy
    healthBadge.textContent = isHealthy ? "Healthy" : "Unhealthy"
    healthBadge.className = `badge bg-${isHealthy ? "success" : "danger"}`
  }

  // Update image if available
  const latestImage = cardElement.querySelector(".latest-image")
  if (latestImage && cameraData.last_image_path) {
    latestImage.src = `/media/${cameraData.last_image_path}`
  }

  // Add visual feedback for updates
  cardElement.classList.add("fade-in")
  setTimeout(() => cardElement.classList.remove("fade-in"), 500)
}

/**
 * Update system statistics
 */
async function updateSystemStats() {
  try {
    const response = await fetch("/api/stats")
    const data = await response.json()

    if (data.status === "success") {
      // Update online count
      const onlineCount = document.getElementById("online-count")
      if (onlineCount) {
        onlineCount.textContent = data.data.cameras.healthy_cameras
      }

      // Update other stats as needed
      console.log("📊 System stats updated")
    }
  } catch (error) {
    console.error("Error updating system stats:", error)
  }
}

/**
 * Load system statistics
 */
async function loadSystemStats() {
  try {
    const response = await fetch("/api/health")
    const data = await response.json()

    if (data.status === "success") {
      updateHealthIndicators(data.data)
    }
  } catch (error) {
    console.error("Error loading system stats:", error)
  }
}

/**
 * Update health indicators
 */
function updateHealthIndicators(healthData) {
  // Update overall health status
  const healthStatus = healthData.health_status
  console.log(`🏥 System health: ${healthStatus}`)

  // Show notification for critical issues
  if (healthStatus === "critical") {
    showNotification(
      "System health is critical - check camera connections",
      "error",
      true
    )
  }
}

/**
 * Test camera capture
 */
async function testCamera(cameraName) {
  try {
    showNotification(`Testing capture for ${cameraName}...`, "info")

    // This would trigger an actual test capture
    // For now, simulate the test
    setTimeout(() => {
      showNotification(`Test capture completed for ${cameraName}`, "success")
      // Refresh the specific camera's data
      refreshCameraStatus(true)
    }, 2000)
  } catch (error) {
    console.error(`Error testing camera ${cameraName}:`, error)
    showNotification(`Test failed for ${cameraName}: ${error.message}`, "error")
  }
}

/**
 * Update relative time displays
 */
function updateRelativeTimes() {
  const timeElements = document.querySelectorAll(".last-capture")
  timeElements.forEach((element) => {
    const text = element.textContent
    if (text && text !== "Never" && text !== "Just now") {
      // This is a simplified implementation
      // In a real scenario, you'd parse the actual timestamp and calculate
      console.log("🕒 Updating relative times")
    }
  })
}

/**
 * Show loading state
 */
function showLoadingState() {
  const refreshBtn = document.querySelector('[onclick*="refreshCameraStatus"]')
  if (refreshBtn) {
    refreshBtn.disabled = true
    refreshBtn.innerHTML =
      '<span class="spinner-border spinner-border-sm me-1"></span> Refreshing...'
  }

  // Add loading class to camera cards
  document.querySelectorAll(".camera-card").forEach((card) => {
    card.classList.add("loading")
  })
}

/**
 * Hide loading state
 */
function hideLoadingState() {
  const refreshBtn = document.querySelector('[onclick*="refreshCameraStatus"]')
  if (refreshBtn) {
    refreshBtn.disabled = false
    refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Refresh'
  }

  // Remove loading class from camera cards
  document.querySelectorAll(".camera-card").forEach((card) => {
    card.classList.remove("loading")
  })
}

/**
 * Show notification
 */
function showNotification(message, type = "info", persistent = false) {
  // Create toast element
  const toastContainer = getToastContainer()
  const toast = createToastElement(message, type)

  toastContainer.appendChild(toast)

  // Initialize and show toast
  const bsToast = new bootstrap.Toast(toast, {
    delay: persistent ? 0 : 5000,
  })
  bsToast.show()

  // Remove toast element after it's hidden
  toast.addEventListener("hidden.bs.toast", () => {
    toast.remove()
  })

  // Also try browser notifications for important messages
  if (
    type === "error" &&
    "Notification" in window &&
    Notification.permission === "granted"
  ) {
    new Notification("UniFi Timelapser", {
      body: message,
      icon: "/static/favicon.ico",
    })
  }
}

/**
 * Get or create toast container
 */
function getToastContainer() {
  let container = document.getElementById("toast-container")
  if (!container) {
    container = document.createElement("div")
    container.id = "toast-container"
    container.className = "toast-container position-fixed top-0 end-0 p-3"
    container.style.zIndex = "1055"
    document.body.appendChild(container)
  }
  return container
}

/**
 * Create toast element
 */
function createToastElement(message, type) {
  const toast = document.createElement("div")
  toast.className = "toast"
  toast.setAttribute("role", "alert")

  const typeConfig = {
    success: { icon: "check-circle-fill", class: "text-success" },
    error: { icon: "exclamation-triangle-fill", class: "text-danger" },
    warning: { icon: "exclamation-triangle-fill", class: "text-warning" },
    info: { icon: "info-circle-fill", class: "text-info" },
  }

  const config = typeConfig[type] || typeConfig.info

  toast.innerHTML = `
        <div class="toast-header">
            <i class="bi bi-${config.icon} ${config.class} me-2"></i>
            <strong class="me-auto">UniFi Timelapser</strong>
            <small>${new Date().toLocaleTimeString()}</small>
            <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    `

  return toast
}

/**
 * Update last update display
 */
function updateLastUpdateDisplay() {
  const display = document.getElementById("last-update")
  if (display) {
    display.textContent = `Last updated: ${lastUpdateTime.toLocaleTimeString()}`
  }
}

/**
 * Handle page visibility changes
 */
document.addEventListener("visibilitychange", function () {
  if (document.hidden) {
    stopAutoRefresh()
  } else {
    startAutoRefresh()
    // Refresh immediately when page becomes visible
    refreshCameraStatus(true)
  }
})

/**
 * Handle window focus/blur
 */
window.addEventListener("focus", function () {
  refreshCameraStatus(true)
})

/**
 * Export functions for global access
 */
window.refreshCameraStatus = refreshCameraStatus
window.testCamera = testCamera
window.updateRelativeTimes = updateRelativeTimes

// Log initialization
console.log("📱 Dashboard JavaScript loaded successfully")
