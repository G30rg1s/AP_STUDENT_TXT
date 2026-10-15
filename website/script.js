
/*
 * Automation Platform - Student Download Page
 *
 * Official GitHub Releases:
 * https://github.com/G30rg1s/automation-platform-student/releases
 *
 * Windows: Stable v1.0.1
 * Linux: Beta v1.1.0-beta.1
 * macOS: Beta v1.1.0-beta.1
 */

// ========================================
// OFFICIAL DOWNLOAD URLS
// ========================================

const downloads = {
  windows:
    "https://github.com/G30rg1s/automation-platform-student/releases/download/v1.0.1/AutomationPlatform-Setup-Test.exe",

  linux:
    "https://github.com/G30rg1s/automation-platform-student/releases/download/v1.1.0-beta.1/AutomationPlatform-Linux-Release.tar.gz",

  macos:
    "https://github.com/G30rg1s/automation-platform-student/releases/download/v1.1.0-beta.1/AutomationPlatform-macOS-Release.zip"
};

// ========================================
// DOWNLOAD DETAILS
// ========================================

const downloadDetails = {
  windows: {
    label: "Download for Windows",
    hint: "Windows installer (.exe) - Stable v1.0.1"
  },

  linux: {
    label: "Download for Linux (Beta)",
    hint: "Linux package (.tar.gz) - Beta v1.1.0-beta.1"
  },

  macos: {
    label: "Download for macOS (Beta)",
    hint: "macOS application (.zip) - Beta v1.1.0-beta.1"
  }
};

// ========================================
// CONFIGURE DOWNLOAD BUTTONS
// ========================================

for (const [os, url] of Object.entries(downloads)) {
  const button = document.getElementById(
    `${os}-download`
  );

  const label = document.getElementById(
    `${os}-button-label`
  );

  const hint = document.getElementById(
    `${os}-hint`
  );

  if (!button || !label || !hint) {
    continue;
  }

  // Keep button disabled if no valid download URL exists.
  if (!url || !/^https:\/\//i.test(url)) {
    button.removeAttribute("href");

    button.setAttribute(
      "aria-disabled",
      "true"
    );

    button.setAttribute(
      "tabindex",
      "-1"
    );

    continue;
  }

  // Official GitHub Release download URL.
  button.href = url;

  // Enable the button.
  button.removeAttribute("aria-disabled");
  button.removeAttribute("tabindex");

  // GitHub download URLs are cross-origin.
  // Let the browser handle the download normally.
  button.removeAttribute("download");

  // Update button label and package information.
  const details = downloadDetails[os];

  if (details) {
    label.textContent = details.label;
    hint.textContent = details.hint;
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

  const note = document.getElementById(
    "platform-note"
  );

  const name =
    detectedOS === "macos"
      ? "macOS"
      : detectedOS === "linux"
        ? "Linux"
        : "Windows";

  if (note) {
    note.textContent =
      `Detected platform: ${name}. ` +
      "Choose another package if needed.";
  }
}

// ========================================
// COPYRIGHT YEAR
// ========================================

const yearElement = document.getElementById(
  "year"
);

if (yearElement) {
  yearElement.textContent =
    new Date().getFullYear();
}
