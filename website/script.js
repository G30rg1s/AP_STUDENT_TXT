/*
 * Add each public, tested release asset URL below when available.
 * Example:
 * windows: "https://github.com/OWNER/REPOSITORY/releases/download/v1.0.0/AutomationPlatform-Windows.zip"
 * Do not use a local C:\\ path or a private GitHub Release URL.
 */
const downloads = {
  windows: "",
  linux: "",
  macos: ""
};

for (const [os, url] of Object.entries(downloads)) {
  const button = document.getElementById(`${os}-download`);
  const label = document.getElementById(`${os}-button-label`);
  const hint = document.getElementById(`${os}-hint`);
  if (!button || !url || !/^https:\/\//i.test(url)) continue;
  button.href = url;
  button.removeAttribute("aria-disabled");
  button.removeAttribute("tabindex");
  button.setAttribute("download", "");
  label.textContent = "Download package";
  hint.textContent = "Download from the official Automation Platform release.";
}

const platform = navigator.userAgentData?.platform || navigator.platform || navigator.userAgent;
const normalized = String(platform).toLowerCase();
const detectedOS = /windows|win32|win64/.test(normalized) ? "windows"
  : /macintosh|macintel|mac os|macos/.test(normalized) ? "macos"
  : /linux|x11/.test(normalized) ? "linux" : null;
if (detectedOS) {
  const card = document.querySelector(`[data-os="${detectedOS}"]`);
  if (card) card.classList.add("recommended");
  const note = document.getElementById("platform-note");
  const name = detectedOS === "macos" ? "macOS" : detectedOS[0].toUpperCase() + detectedOS.slice(1);
  if (note) note.textContent = `Detected platform: ${name}. Choose another package if needed.`;
}
document.getElementById("year").textContent = new Date().getFullYear();
