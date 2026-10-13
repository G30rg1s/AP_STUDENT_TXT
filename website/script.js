
/*
 * Automation Platform - Student Download Page
 *
 * Official GitHub Releases:
 * https://github.com/G30rg1s/automation-platform-student/releases
 *
 * Linux and macOS downloads will be enabled
 * when their packages are available.
 */

const downloads = {
  windows: "https://github.com/G30rg1s/automation-platform-student/releases/download/v1.0.0/AutomationPlatform-Setup.exe",
  linux: "",
  macos: ""
};

// ========================================
// CONFIGURE DOWNLOAD BUTTONS
// ========================================

for (const [os, url] of Object.entries(downloads)) {
  const button = document.getElementById(`${os}-download`);
  const label = document.getElementById(`${os}-button-label`);
  const hint = document.getElementById(`${os}-hint`);

  if (!button || !label || !hint) {
    continue;
  }

  if (!url || !/^https:\/\//i.test(url)) {
    continue;
  }

  button.href = url;

  button.removeAttribute("aria-disabled");
  button.removeAttribute("tabindex");
  button.removeAttribute("download");

  if (os === "windows") {
    label.textContent = "Download for Windows";

    hint.textContent =
      "Download Automation Platform Setup (.exe) - Version 1.0.0";
  } else {
    label.textContent = "Download package";

    hint.textContent =
      "Download from the official Automation Platform release.";
  }
}

// ========================================
// OPERATING SYSTEM DETECTION
// ========================================

const platform =
  navigator.userAgentData?.platform ||
  navigator.platform ||
  navigator.userAgent;

const normalized = String(platform).toLowerCase();

const detectedOS =
  /windows|win32|win64/.test(normalized)
    ? "windows"
    : /macintosh|macintel|mac os|macos/.test(normalized)
      ? "macos"
      : /linux|x11/.test(normalized)
        ? "linux"
        : null;

// ========================================
// HIGHLIGHT RECOMMENDED DOWNLOAD
// ========================================

if (detectedOS) {
  const card = document.querySelector(
    `[data-os="${detectedOS}"]`
  );

  if (card) {
    card.classList.add("recommended");
  }

  const note = document.getElementById("platform-note");

  const name =
    detectedOS === "macos"
      ? "macOS"
      : detectedOS[0].toUpperCase() +
        detectedOS.slice(1);

  if (note) {
    note.textContent =
      `Detected platform: ${name}. Choose another package if needed.`;
  }
}

// ========================================
// COPYRIGHT YEAR
// ========================================

const yearElement = document.getElementById("year");

if (yearElement) {
  yearElement.textContent = new Date().getFullYear();
}
