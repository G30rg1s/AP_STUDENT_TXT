
import os
import platform
import queue
import shutil
import subprocess
import threading
import tkinter as tk
import webbrowser

from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk


# ============================================================
# AUTOMATION PLATFORM - DOCKER SETUP
# ============================================================

WINDOWS_DOWNLOAD_URL = (
    "https://docs.docker.com/desktop/setup/install/windows-install/"
)

MAC_DOWNLOAD_URL = (
    "https://docs.docker.com/desktop/setup/install/mac-install/"
)

LINUX_INSTALL_URL = (
    "https://docs.docker.com/engine/install/"
)

WINDOWS_PACKAGE = "Docker.DockerDesktop"

COLORS = {
    "terminal": "#0B1120",
    "text": "#E2E8F0",
    "success": "#4ADE80",
    "warning": "#FBBF24",
    "error": "#F87171",
    "heading": "#38BDF8",
    "timestamp": "#94A3B8",
}


# ============================================================
# OPERATING SYSTEM
# ============================================================

def detect_operating_system():
    system = platform.system()

    if system == "Windows":
        version = platform.version()

        try:
            build = int(version.split(".")[-1])
        except ValueError:
            build = 0

        name = (
            "Windows 11"
            if build >= 22000
            else "Windows " + platform.release()
        )

        return system, f"{name} (Build {version})"

    if system == "Darwin":
        version = platform.mac_ver()[0] or "Unknown"
        return system, "macOS " + version

    if system == "Linux":
        try:
            info = platform.freedesktop_os_release()
            return system, info.get(
                "PRETTY_NAME",
                "Linux"
            )
        except (AttributeError, OSError):
            return system, "Linux"

    return system, system


# ============================================================
# AUTOMATIC DOCKER PATH DETECTION AND REPAIR
# ============================================================

def docker_bin_folders():
    program_files = Path(
        os.environ.get(
            "ProgramFiles",
            r"C:\Program Files"
        )
    )

    local_app = Path(
        os.environ.get(
            "LOCALAPPDATA",
            str(Path.home() / "AppData" / "Local")
        )
    )

    return [
        (
                program_files
                / "Docker"
                / "Docker"
                / "resources"
                / "bin"
        ),
        (
                local_app
                / "Programs"
                / "DockerDesktop"
                / "resources"
                / "bin"
        ),
    ]


def refresh_docker_path():
    """
    Refresh Docker PATH inside this Python process.

    Child processes started after this call inherit
    the updated PATH automatically.

    No administrator rights or registry changes needed.
    """

    if platform.system() != "Windows":
        return False

    current_path = os.environ.get("PATH", "")

    existing_parts = {
        os.path.normcase(
            os.path.normpath(part)
        )
        for part in current_path.split(os.pathsep)
        if part
    }

    new_parts = []

    for folder in docker_bin_folders():
        docker_exe = folder / "docker.exe"

        if not docker_exe.is_file():
            continue

        normalized = os.path.normcase(
            os.path.normpath(str(folder))
        )

        if normalized not in existing_parts:
            new_parts.append(str(folder))
            existing_parts.add(normalized)

    if new_parts:
        os.environ["PATH"] = os.pathsep.join(
            new_parts + [current_path]
        )

    return bool(new_parts)


# ============================================================
# DOCKER SETUP PAGE
# ============================================================

class DockerSetupPage(ttk.Frame):

    def __init__(self, parent, on_continue=None):
        super().__init__(
            parent,
            padding=22
        )

        self.on_continue = on_continue

        self.system, self.system_name = (
            detect_operating_system()
        )

        self.events = queue.Queue()

        self.busy = False
        self.checked = False

        self.wsl_ready = False
        self.docker_installed = False
        self.engine_running = False
        self.compose_ready = False
        self.ready = False

        self.status_var = tk.StringVar(
            value="System check pending"
        )

        self.message_var = tk.StringVar(
            value="Preparing Docker diagnostics."
        )

        self.progress_var = tk.StringVar(
            value="Waiting to start"
        )

        self.install_description = tk.StringVar(
            value="Automatic installation where supported."
        )

        self.continue_description = tk.StringVar(
            value="Continue setup without installing Docker."
        )

        self.build_ui()
        self.update_install_description()

        self.after(
            100,
            self.process_events
        )

        self.after(
            250,
            self.check_docker
        )

    # ========================================================
    # INTERFACE
    # ========================================================

    def build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)

        header = ttk.Frame(self)

        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 12)
        )

        ttk.Label(
            header,
            text="Automation Platform",
            font=("Segoe UI", 21, "bold")
        ).pack(anchor="w")

        ttk.Label(
            header,
            text="Student Setup Wizard - Docker Requirements"
        ).pack(anchor="w")

        os_frame = ttk.LabelFrame(
            self,
            text="Detected Operating System",
            padding=14
        )

        os_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10)
        )

        ttk.Label(
            os_frame,
            text=self.system_name,
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w")

        status_frame = ttk.LabelFrame(
            self,
            text="Step 2 - Docker Requirements",
            padding=14
        )

        status_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 10)
        )

        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 13, "bold")
        ).pack(anchor="w")

        ttk.Label(
            status_frame,
            textvariable=self.message_var,
            wraplength=690
        ).pack(
            anchor="w",
            pady=(7, 0)
        )

        progress_frame = ttk.Frame(self)

        progress_frame.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 12)
        )

        progress_frame.columnconfigure(
            0,
            weight=1
        )

        self.progress = ttk.Progressbar(
            progress_frame,
            mode="indeterminate"
        )

        self.progress.grid(
            row=0,
            column=0,
            sticky="ew"
        )

        ttk.Label(
            progress_frame,
            textvariable=self.progress_var
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(5, 0)
        )

        ttk.Label(
            self,
            text="System Diagnostics & Installation Logs",
            font=("Segoe UI", 11, "bold")
        ).grid(
            row=4,
            column=0,
            sticky="w",
            pady=(0, 7)
        )

        self.details_text = scrolledtext.ScrolledText(
            self,
            height=12,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            bg=COLORS["terminal"],
            fg=COLORS["text"],
            insertbackground="white",
            selectbackground="#334155",
            selectforeground="white",
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=14
        )

        self.details_text.grid(
            row=5,
            column=0,
            sticky="nsew",
            pady=(0, 12)
        )

        for name in (
                "success",
                "warning",
                "error",
                "heading",
                "timestamp"
        ):
            self.details_text.tag_configure(
                name,
                foreground=COLORS[name]
            )

        actions = ttk.Frame(self)

        actions.grid(
            row=6,
            column=0,
            sticky="ew"
        )

        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        self.check_button = self.add_action(
            actions,
            0,
            0,
            "Check Again",
            "Recheck Docker requirements.",
            self.check_docker
        )

        self.install_button = self.add_action(
            actions,
            0,
            1,
            "Download & Install Docker Automatically",
            self.install_description,
            self.confirm_installation
        )

        self.download_button = self.add_action(
            actions,
            1,
            0,
            "Docker Installation Page",
            "Open the official Docker installation instructions.",
            self.open_download_page
        )

        self.continue_button = self.add_action(
            actions,
            1,
            1,
            "Install Manually Later",
            self.continue_description,
            self.continue_to_next
        )

    @staticmethod
    def add_action(
            parent,
            row,
            column,
            title,
            description,
            command
    ):
        frame = ttk.Frame(parent)

        frame.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=5,
            pady=5
        )

        button = ttk.Button(
            frame,
            text=title,
            command=command
        )

        button.pack(fill="x")

        if isinstance(description, tk.StringVar):
            label_args = {
                "textvariable": description
            }
        else:
            label_args = {
                "text": description
            }

        ttk.Label(
            frame,
            wraplength=320,
            justify="left",
            font=("Segoe UI", 9),
            **label_args
        ).pack(
            anchor="w",
            pady=(5, 0)
        )

        return button

    # ========================================================
    # INSTALLATION DESCRIPTION
    # ========================================================

    def update_install_description(self):
        descriptions = {
            "Windows": (
                "Install Docker Desktop using WinGet."
            ),
            "Darwin": (
                "Install Docker Desktop using Homebrew, "
                "if available."
            ),
            "Linux": (
                "Use official installation instructions "
                "for your Linux distribution."
            ),
        }

        self.install_description.set(
            descriptions.get(
                self.system,
                "Automatic installation unavailable."
            )
        )

    # ========================================================
    # DARK TERMINAL
    # ========================================================

    def append_log(self, message, level=None):
        self.details_text.configure(
            state="normal"
        )

        for line in str(message).splitlines() or [""]:
            stamp = datetime.now().strftime(
                "%H:%M:%S"
            )

            self.details_text.insert(
                tk.END,
                f"[{stamp}] ",
                "timestamp"
            )

            low = line.strip().lower()
            tag = level

            if tag is None:
                if low.startswith((
                        "error:",
                        "failed:",
                        "final status: failed"
                )):
                    tag = "error"

                elif low.startswith((
                        "warning:",
                        "final status: attention",
                        "final status: restart"
                )):
                    tag = "warning"

                elif low.startswith((
                        "success:",
                        "final status: ready"
                )):
                    tag = "success"

                elif low.startswith((
                        "===",
                        "> "
                )):
                    tag = "heading"

            self.details_text.insert(
                tk.END,
                line + "\n",
                tag
            )

        self.details_text.see(tk.END)

        self.details_text.configure(
            state="disabled"
        )

    def clear_logs(self):
        self.details_text.configure(
            state="normal"
        )

        self.details_text.delete(
            "1.0",
            tk.END
        )

        self.details_text.configure(
            state="disabled"
        )

    def log_from_worker(self, message, level=None):
        self.events.put(
            ("log", (message, level))
        )

    # ========================================================
    # THREAD-SAFE UI EVENTS
    # ========================================================

    def process_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()

                if kind == "log":
                    self.append_log(*data)

                elif kind == "check_result":
                    self.show_result(data)

                elif kind == "check_error":
                    self.show_error(data)

                elif kind == "install_result":
                    self.installation_finished(data)

        except queue.Empty:
            pass

        try:
            if self.winfo_exists():
                self.after(
                    100,
                    self.process_events
                )
        except tk.TclError:
            pass

    # ========================================================
    # BUSY STATE
    # ========================================================

    def set_busy(
            self,
            busy,
            label="Operation finished"
    ):
        self.busy = busy

        state = (
            "disabled"
            if busy
            else "normal"
        )

        for button in (
                self.check_button,
                self.install_button,
                self.download_button,
                self.continue_button
        ):
            button.configure(
                state=state
            )

        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

        self.progress_var.set(label)

    # ========================================================
    # PROCESS EXECUTION
    # ========================================================

    @staticmethod
    def run_command(command, timeout=20):
        if platform.system() == "Windows":
            flags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0
            )
        else:
            flags = 0

        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=flags
            )

            return (
                result.returncode,
                result.stdout.strip()
            )

        except FileNotFoundError:
            return 127, "Command not found."

        except subprocess.TimeoutExpired:
            return 124, "Command timed out."

        except OSError as error:
            return 1, str(error)

    # ========================================================
    # WINDOWS DOCKER DETECTION
    # ========================================================

    @staticmethod
    def windows_desktop_installed():
        if platform.system() != "Windows":
            return False

        program_files = Path(
            os.environ.get(
                "ProgramFiles",
                r"C:\Program Files"
            )
        )

        local_app = Path(
            os.environ.get(
                "LOCALAPPDATA",
                str(Path.home() / "AppData" / "Local")
            )
        )

        applications = [
            (
                    program_files
                    / "Docker"
                    / "Docker"
                    / "Docker Desktop.exe"
            ),
            (
                    local_app
                    / "Programs"
                    / "DockerDesktop"
                    / "Docker Desktop.exe"
            ),
        ]

        if any(
                path.is_file()
                for path in applications
        ):
            return True

        try:
            import winreg

            uninstall_path = (
                r"SOFTWARE\Microsoft\Windows"
                r"\CurrentVersion\Uninstall"
            )

            hives = (
                winreg.HKEY_LOCAL_MACHINE,
                winreg.HKEY_CURRENT_USER
            )

            views = (
                winreg.KEY_WOW64_64KEY,
                winreg.KEY_WOW64_32KEY
            )

            for hive in hives:
                for view in views:
                    try:
                        with winreg.OpenKey(
                                hive,
                                uninstall_path,
                                0,
                                winreg.KEY_READ | view
                        ) as root:

                            index = 0

                            while True:
                                try:
                                    subkey = winreg.EnumKey(
                                        root,
                                        index
                                    )
                                    index += 1

                                except OSError:
                                    break

                                try:
                                    with winreg.OpenKey(
                                            root,
                                            subkey
                                    ) as entry:

                                        name, _ = (
                                            winreg.QueryValueEx(
                                                entry,
                                                "DisplayName"
                                            )
                                        )

                                        if (
                                                "docker desktop"
                                                in str(name).lower()
                                        ):
                                            return True

                                except OSError:
                                    continue

                    except OSError:
                        continue

        except ImportError:
            pass

        return False

    # ========================================================
    # DOCKER CLI
    # ========================================================

    def find_docker_cli(self):
        refresh_docker_path()

        found = shutil.which("docker")

        if found:
            return found

        if self.system == "Windows":
            for folder in docker_bin_folders():
                cli = folder / "docker.exe"

                if cli.is_file():
                    return str(cli)

        elif self.system == "Darwin":
            paths = (
                "/usr/local/bin/docker",
                "/opt/homebrew/bin/docker",
                str(
                    Path.home()
                    / ".docker"
                    / "bin"
                    / "docker"
                ),
            )

            for path in paths:
                if Path(path).is_file():
                    return path

        elif self.system == "Linux":
            for path in (
                    "/usr/bin/docker",
                    "/usr/local/bin/docker"
            ):
                if Path(path).is_file():
                    return path

        return None

    # ========================================================
    # DOCKER INSTALLATION
    # ========================================================

    def docker_installed_on_system(self):
        if self.system == "Windows":
            return self.windows_desktop_installed()

        if self.system == "Darwin":
            return any(
                path.exists()
                for path in (
                    Path("/Applications/Docker.app"),
                    (
                            Path.home()
                            / "Applications"
                            / "Docker.app"
                    )
                )
            )

        return self.find_docker_cli() is not None

    # ========================================================
    # CHECK DOCKER
    # ========================================================

    def check_docker(self):
        if self.busy:
            return

        self.checked = False
        self.ready = False

        self.clear_logs()

        self.set_busy(
            True,
            "Checking Docker requirements..."
        )

        self.status_var.set(
            "Checking Docker requirements..."
        )

        self.message_var.set(
            "Please wait while Docker is checked."
        )

        self.append_log(
            "=== AUTOMATION PLATFORM DOCKER CHECK ===",
            "heading"
        )

        self.append_log(
            "Detected Operating System: "
            + self.system_name
        )

        threading.Thread(
            target=self._check_worker,
            daemon=True
        ).start()

    # ========================================================
    # BACKGROUND DOCKER CHECK
    # ========================================================

    def _check_worker(self):
        try:
            if refresh_docker_path():
                self.log_from_worker(
                    "SUCCESS: Docker PATH updated automatically.",
                    "success"
                )

            wsl_ready = True

            if self.system == "Windows":
                from launcher.windows.windows_wsl_checker import WslChecker

                self.log_from_worker(
                    "=== WSL 2 CHECK ===",
                    "heading"
                )

                wsl_status = WslChecker().check()

                wsl_ready = (
                        wsl_status.state == "READY"
                )

                if wsl_ready:
                    self.log_from_worker(
                        "SUCCESS: WSL 2 is ready.",
                        "success"
                    )
                else:
                    self.log_from_worker(
                        "WARNING: WSL 2 is not ready.",
                        "warning"
                    )

                    self.log_from_worker(
                        wsl_status.message
                    )

            self.log_from_worker(
                "=== DOCKER INSTALLATION CHECK ===",
                "heading"
            )

            installed = (
                self.docker_installed_on_system()
            )

            if installed:
                self.log_from_worker(
                    "SUCCESS: Docker installation found.",
                    "success"
                )
            else:
                self.log_from_worker(
                    "WARNING: Docker installation not found.",
                    "warning"
                )

            cli = self.find_docker_cli()

            if cli:
                self.log_from_worker(
                    "Docker CLI: " + cli
                )
            else:
                self.log_from_worker(
                    "WARNING: Docker CLI was not found.",
                    "warning"
                )

            engine_running = False
            compose_ready = False

            if cli:
                self.log_from_worker(
                    "=== DOCKER ENGINE CHECK ===",
                    "heading"
                )

                self.log_from_worker(
                    "> docker info --format {{.ServerVersion}}",
                    "heading"
                )

                code, output = self.run_command(
                    [
                        cli,
                        "info",
                        "--format",
                        "{{.ServerVersion}}"
                    ]
                )

                engine_running = (code == 0)

                if engine_running:
                    self.log_from_worker(
                        "SUCCESS: Docker Engine is running.",
                        "success"
                    )
                else:
                    self.log_from_worker(
                        "WARNING: Docker Engine is not responding.",
                        "warning"
                    )

                if output:
                    self.log_from_worker(output)

                self.log_from_worker(
                    "=== DOCKER COMPOSE CHECK ===",
                    "heading"
                )

                self.log_from_worker(
                    "> docker compose version",
                    "heading"
                )

                code, output = self.run_command(
                    [
                        cli,
                        "compose",
                        "version"
                    ]
                )

                compose_ready = (code == 0)

                if compose_ready:
                    self.log_from_worker(
                        "SUCCESS: Docker Compose is available.",
                        "success"
                    )
                else:
                    self.log_from_worker(
                        "WARNING: Docker Compose is unavailable.",
                        "warning"
                    )

                if output:
                    self.log_from_worker(output)

            self.events.put((
                "check_result",
                {
                    "wsl_ready": wsl_ready,
                    "installed": installed,
                    "engine_running": engine_running,
                    "compose_ready": compose_ready,
                }
            ))

        except Exception as error:
            self.events.put((
                "check_error",
                str(error)
            ))

    # ========================================================
    # DISPLAY CHECK RESULT
    # ========================================================

    def show_result(self, result):
        self.checked = True

        self.wsl_ready = result["wsl_ready"]
        self.docker_installed = result["installed"]
        self.engine_running = result["engine_running"]
        self.compose_ready = result["compose_ready"]

        self.ready = all((
            self.wsl_ready,
            self.docker_installed,
            self.engine_running,
            self.compose_ready
        ))

        self.set_busy(
            False,
            "System check completed"
        )

        if self.ready:
            title = "Docker Ready"
            message = (
                "Docker Engine and Docker Compose are ready."
            )
            final = "FINAL STATUS: READY"

        elif not self.wsl_ready:
            title = "WSL 2 Requires Attention"
            message = (
                "Complete WSL 2 setup before Docker Desktop."
            )
            final = "FINAL STATUS: WSL 2 REQUIRED"

        elif not self.docker_installed:
            title = "Docker Is Not Installed"
            message = (
                "Install Docker Desktop using the "
                "automatic installer."
            )
            final = "FINAL STATUS: INSTALLATION REQUIRED"

        elif not self.engine_running:
            title = "Docker Engine Is Not Running"
            message = (
                "Start Docker Desktop, complete first-run "
                "setup, then click Check Again."
            )
            final = "FINAL STATUS: ENGINE NOT READY"

        else:
            title = "Docker Compose Is Unavailable"
            message = (
                "Docker Engine works but Compose "
                "is unavailable."
            )
            final = "FINAL STATUS: COMPOSE REQUIRED"

        self.status_var.set(title)
        self.message_var.set(message)

        self.append_log(
            final,
            "success" if self.ready else "warning"
        )

        can_install = (
                not self.ready
                and self.wsl_ready
                and not self.docker_installed
                and self.automatic_install_command() is not None
        )

        self.install_button.configure(
            state="normal" if can_install else "disabled"
        )

        self.continue_button.configure(
            text=(
                "Continue"
                if self.ready
                else "Install Manually Later"
            )
        )

        self.continue_description.set(
            "Continue to the main application launcher."
            if self.ready
            else (
                "Continue setup, but starting the "
                "application requires Docker."
            )
        )

    def show_error(self, message):
        self.checked = False
        self.ready = False

        self.set_busy(
            False,
            "System check failed"
        )

        self.status_var.set(
            "Docker Check Failed"
        )

        self.message_var.set(message)

        self.append_log(
            "ERROR: " + message,
            "error"
        )

        self.append_log(
            "FINAL STATUS: FAILED",
            "error"
        )

        self.install_button.configure(
            state="disabled"
        )

    # ========================================================
    # OFFICIAL DOCKER INSTALLATION PAGE
    # ========================================================

    def open_download_page(self):
        url = {
            "Windows": WINDOWS_DOWNLOAD_URL,
            "Darwin": MAC_DOWNLOAD_URL
        }.get(
            self.system,
            LINUX_INSTALL_URL
        )

        self.append_log(
            "Opening official Docker installation page.",
            "heading"
        )

        self.append_log(url)
        webbrowser.open(url)

    # ========================================================
    # AUTOMATIC INSTALLATION COMMAND
    # ========================================================

    def automatic_install_command(self):
        if self.system == "Windows":
            winget = shutil.which("winget")

            if winget:
                return [
                    winget,
                    "install",
                    "--id",
                    WINDOWS_PACKAGE,
                    "--exact",
                    "--source",
                    "winget",
                    "--accept-package-agreements",
                    "--accept-source-agreements"
                ]

        elif self.system == "Darwin":
            brew = shutil.which("brew")

            if brew:
                return [
                    brew,
                    "install",
                    "--cask",
                    "docker"
                ]

        return None

    # ========================================================
    # USER CONFIRMATION
    # ========================================================

    def confirm_installation(self):
        if self.busy:
            return

        if not self.checked:
            messagebox.showwarning(
                "Check Required",
                "Click Check Again first.",
                parent=self
            )
            return

        if not self.wsl_ready:
            messagebox.showwarning(
                "WSL 2 Required",
                "Complete WSL 2 setup first.",
                parent=self
            )
            return

        if self.docker_installed:
            messagebox.showinfo(
                "Docker Already Installed",
                "Start Docker Desktop and click Check Again.",
                parent=self
            )
            return

        command = self.automatic_install_command()

        if not command:
            messagebox.showinfo(
                "Manual Installation",
                "Use the official Docker installation page.",
                parent=self
            )
            return

        if self.system == "Windows":
            display_command = subprocess.list2cmdline(
                command
            )
        else:
            display_command = " ".join(command)

        confirmed = messagebox.askyesno(
            "Confirm Docker Installation",
            f"Detected OS: {self.system_name}\n\n"
            f"Real command:\n{display_command}\n\n"
            "This downloads and installs software.\n"
            "Administrator permission may be requested.\n"
            "No automatic restart will occur.\n\n"
            "Continue?",
            parent=self
        )

        if not confirmed:
            self.append_log(
                "WARNING: Installation cancelled by user.",
                "warning"
            )
            return

        self.set_busy(
            True,
            "Installing Docker. Watch the logs..."
        )

        self.status_var.set(
            "Installing Docker..."
        )

        self.message_var.set(
            "Installation running. Please wait."
        )

        self.append_log(
            "=== DOCKER INSTALLATION STARTED ===",
            "heading"
        )

        self.append_log(
            "> " + display_command,
            "heading"
        )

        threading.Thread(
            target=self._install_worker,
            args=(command,),
            daemon=True
        ).start()

    # ========================================================
    # REAL INSTALLATION WORKER
    # ========================================================

    def _install_worker(self, command):
        process = None
        timer = None

        timed_out = threading.Event()

        try:
            if self.system == "Windows":
                flags = getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0
                )
            else:
                flags = 0

            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags
            )

            def stop_on_timeout():
                if process.poll() is None:
                    timed_out.set()

                    try:
                        process.kill()
                    except OSError:
                        pass

            timer = threading.Timer(
                1800,
                stop_on_timeout
            )

            timer.daemon = True
            timer.start()

            for line in process.stdout:
                if line.strip():
                    self.log_from_worker(
                        line.rstrip("\r\n")
                    )

            code = process.wait()

            if timed_out.is_set():
                code = 124

                self.log_from_worker(
                    "ERROR: Installation timed out.",
                    "error"
                )

            self.events.put((
                "install_result",
                code
            ))

        except Exception as error:
            self.log_from_worker(
                "ERROR: " + str(error),
                "error"
            )

            self.events.put((
                "install_result",
                1
            ))

        finally:
            if timer:
                timer.cancel()

            if process and process.stdout:
                process.stdout.close()

    # ========================================================
    # INSTALLATION FINISHED - REFRESH DOCKER PATH
    # ========================================================

    def installation_finished(self, code):
        if refresh_docker_path():
            self.append_log(
                "SUCCESS: Docker PATH updated automatically.",
                "success"
            )

        self.set_busy(
            False,
            "Installation attempt finished"
        )

        self.append_log(
            "=== FINAL INSTALLATION RESULT ===",
            "heading"
        )

        if code == 0:
            self.status_var.set(
                "Installation Command Completed"
            )

            self.message_var.set(
                "Start Docker Desktop, complete first-run "
                "setup, then click Check Again."
            )

            self.append_log(
                "SUCCESS: Installation command completed.",
                "success"
            )

            self.append_log(
                "FINAL STATUS: VERIFICATION REQUIRED",
                "warning"
            )

            messagebox.showinfo(
                "Docker Installation",
                "Installation command completed.\n\n"
                "Start Docker Desktop if needed, "
                "complete first-run setup, "
                "then click Check Again.",
                parent=self
            )

        else:
            self.status_var.set(
                "Docker Installation Requires Attention"
            )

            self.message_var.set(
                "Review installation logs or use "
                "the official installation page."
            )

            self.append_log(
                f"ERROR: Installation returned exit code {code}.",
                "error"
            )

            self.append_log(
                "FINAL STATUS: FAILED",
                "error"
            )

        self.checked = False
        self.ready = False

        self.install_button.configure(
            state="disabled"
        )

    # ========================================================
    # CONTINUE
    # ========================================================

    def continue_to_next(self):
        if self.busy:
            return

        if self.on_continue:
            self.on_continue(self.ready)
            return

        if self.ready:
            messagebox.showinfo(
                "Docker Setup Complete",
                "Docker requirements satisfied.\n"
                "Next: Automation Platform Launcher.",
                parent=self
            )
        else:
            messagebox.showinfo(
                "Install Manually Later",
                "You may continue now, but Automation "
                "Platform cannot start until Docker Engine "
                "and Docker Compose are working.",
                parent=self
            )



# ============================================================
# STANDALONE ENTRY POINT
# ============================================================

def main():
    root = tk.Tk()

    root.title(
        "Automation Platform - Docker Setup"
    )

    root.geometry("880x780")
    root.minsize(740, 650)

    page = DockerSetupPage(root)

    page.pack(
        fill="both",
        expand=True
    )

    root.mainloop()


if __name__ == "__main__":
    main()
