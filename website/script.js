
/*
 * Automation Platform - Student Download Page
 *
 * Automatically discover the latest available packages
 * for Windows, Linux and macOS from GitHub Releases.
 *
 * Each operating system has its own latest version.
 */

"use strict";

// ========================================
// GITHUB CONFIGURATION
// ========================================

const GITHUB_OWNER = "G30rg1s";
const GITHUB_REPO = "AP_STUDENT_TXT";

const RELEASES_API =
  `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases?per_page=100`;

const RELEASES_PAGE =
  `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/releases`;

const OPERATING_SYSTEMS = [
  "windows",
  "linux",
  "macos"
];

// ========================================
// PACKAGE RECOGNITION
// ========================================

function detectPackageOS(filename) {
  const name = filename.toLowerCase();

  // Windows
  if (
    name.endsWith(".exe") ||
    name.endsWith(".msi")
  ) {
    return "windows";
  }

  // Linux
  if (
    name.endsWith(".appimage") ||
    name.endsWith(".deb") ||
    name.endsWith(".rpm")
  ) {
    return "linux";
  }

  if (
    (name.endsWith(".tar.gz") ||
      name.endsWith(".tgz")) &&
    /linux|ubuntu|debian/.test(name)
  ) {
    return "linux";
  }

  // macOS
  if (
    name.endsWith(".dmg") ||
    name.endsWith(".pkg")
  ) {
    return "macos";
  }

  if (
    name.endsWith(".zip") &&
    /macos|mac-os|mac_os|darwin|osx/.test(name)
  ) {
    return "macos";
  }

  return null;
}

// ========================================
// FIND LATEST PACKAGE PER OS
// ========================================

function findLatestPackages(releases) {
  const packages = {
    windows: null,
    linux: null,
    macos: null
  };

  const published = releases
    .filter(release =>
      !release.draft &&
      Boolean(release.published_at)
    )
    .sort((a, b) =>
      new Date(b.published_at).getTime() -
      new Date(a.published_at).getTime()
    );

  for (const release of published) {
    for (const asset of release.assets || []) {
      if (
        asset.state !== "uploaded" ||
        !asset.browser_download_url
      ) {
        continue;
      }

      const os = detectPackageOS(asset.name);

      if (!os || packages[os]) {
        continue;
      }

      packages[os] = {
        url: asset.browser_download_url,
        filename: asset.name,
        version: release.tag_name,
        beta: Boolean(release.prerelease)
      };
    }

    if (
      OPERATING_SYSTEMS.every(
        os => packages[os] !== null
      )
    ) {
      break;
    }
  }

  return packages;
}

// ========================================
// DOWNLOAD BUTTON MANAGEMENT
// ========================================

function getDownloadElements(os) {
  return {
    button: document.getElementById(
      `${os}-download`
    ),
    label: document.getElementById(
      `${os}-button-label`
    ),
    hint: document.getElementById(
      `${os}-hint`
    )
  };
}

function disableDownload(os, message) {
  const {
    button,
    label,
    hint
  } = getDownloadElements(os);

  if (!button || !label || !hint) {
    return;
  }

  button.removeAttribute("href");
  button.setAttribute("aria-disabled", "true");
  button.setAttribute("tabindex", "-1");

  label.textContent = "Coming soon";
  hint.textContent = message;
}

function enableDownload(os, download) {
  const {
    button,
    label,
    hint
  } = getDownloadElements(os);

  if (!button || !label || !hint) {
    return;
  }

  const osNames = {
    windows: "Windows",
    linux: "Linux",
    macos: "macOS"
  };

  const releaseType = download.beta
    ? "Beta"
    : "Stable";

  button.href = download.url;
  button.removeAttribute("aria-disabled");
  button.removeAttribute("tabindex");
  button.removeAttribute("download");

  label.textContent =
    `Download for ${osNames[os]}`;

  hint.textContent =
    `${releaseType} ${download.version} · ${download.filename}`;
}

// ========================================
// LOAD GITHUB RELEASES
// ========================================

async function loadLatestDownloads() {
  for (const os of OPERATING_SYSTEMS) {
    disableDownload(
      os,
      "Checking available releases..."
    );
  }

  try {
    const response = await fetch(RELEASES_API, {
      headers: {
        Accept: "application/vnd.github+json"
      },
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error(
        `GitHub API error: HTTP ${response.status}`
      );
    }

    const releases = await response.json();

    if (!Array.isArray(releases)) {
      throw new Error(
        "Invalid GitHub API response."
      );
    }

    const packages = findLatestPackages(releases);

    for (const os of OPERATING_SYSTEMS) {
      if (packages[os]) {
        enableDownload(os, packages[os]);
      } else {
        disableDownload(
          os,
          "No published package available yet."
        );
      }
    }
  } catch (error) {
    console.error(
      "Failed to load GitHub releases:",
      error
    );

    for (const os of OPERATING_SYSTEMS) {
      disableDownload(
        os,
        "Unable to check downloads. Please visit GitHub Releases."
      );
    }
  }
}

// ========================================
// OPERATING SYSTEM DETECTION
// ========================================

function detectVisitorOS() {
  const platform =
    navigator.userAgentData?.platform ||
    navigator.platform ||
    navigator.userAgent;

  const normalized =
    String(platform).toLowerCase();

  if (/windows|win32|win64/.test(normalized)) {
    return "windows";
  }

  if (
    /macintosh|macintel|mac os|macos/.test(
      normalized
    )
  ) {
    return "macos";
  }

  if (/linux|x11/.test(normalized)) {
    return "linux";
  }

  return null;
}

// ========================================
// HIGHLIGHT RECOMMENDED PLATFORM
// ========================================

function highlightVisitorPlatform() {
  const detectedOS = detectVisitorOS();

  if (!detectedOS) {
    return;
  }

  const card = document.querySelector(
    `[data-os="${detectedOS}"]`
  );

  if (card) {
    card.classList.add("recommended");
  }

  const note = document.getElementById(
    "platform-note"
  );

  if (note) {
    const names = {
      windows: "Windows",
      linux: "Linux",
      macos: "macOS"
    };

    note.textContent =
      `Detected platform: ${names[detectedOS]}. ` +
      "Choose another package if needed.";
  }
}

// ========================================
// COPYRIGHT YEAR
// ========================================

function updateCopyrightYear() {
  const yearElement =
    document.getElementById("year");

  if (yearElement) {
    yearElement.textContent =
      new Date().getFullYear();
  }
}

// ========================================
// INITIALIZATION
// ========================================

highlightVisitorPlatform();
updateCopyrightYear();
loadLatestDownloads();
