
import json
import os
import platform
import queue
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser

from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk


APP_NAME = "Automation Platform"
COMPOSE_PROJECT_NAME = "automation-platform-student"

START_PORT = 8080
MAX_PORT = 8200

HOMEPAGE_PATH = "/automation/homepage"


class StudentLauncher:

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} Launcher")
        self.root.geometry("800x730")
        self.root.minsize(670, 600)
        self.root.configure(bg="#f1f5f9")

        self.system = platform.system()
        self.is_frozen = getattr(sys, "frozen", False)

        self.executable = self.get_executable_path()
        self.base_dir = self.find_project_directory()

        self.compose_file = self.base_dir / "compose.yaml"
        self.env_file = self.base_dir / ".env"
        self.icon_file = self.base_dir / "AutomationPlatform.ico"

        self.settings_dir = (
                Path.home() / ".automation-platform-launcher"
        )

        self.settings_file = (
                self.settings_dir / "settings.json"
        )

        self.selected_port = self.load_saved_port()

        self.events = queue.Queue()
        self.busy = False
        self.action_buttons = []

        self.status_text = tk.StringVar(value="Ready")

        self.port_text = tk.StringVar(
            value=f"Port: {self.selected_port}"
        )

        self.url_text = tk.StringVar(
            value=self.application_url()
        )

        self.build_ui()

        self.root.after(100, self.process_events)

        if self.is_frozen:
            self.root.after(
                800,
                self.create_first_run_shortcut
            )

    # ========================================
    # PATHS
    # ========================================

    def get_executable_path(self):
        if self.is_frozen:
            return Path(sys.executable).resolve()

        return Path(__file__).resolve()

    def find_project_directory(self):
        """
        Source mode:
          project/launcher/student_launcher.py
          project/compose.yaml

        Windows packaged mode:
          package/AutomationPlatformLauncher.exe
          package/compose.yaml

        Linux packaged mode:
          package/AutomationPlatformLauncher
          package/compose.yaml

        macOS packaged mode:
          package/AutomationPlatformLauncher.app
          package/compose.yaml
        """

        if not self.is_frozen:
            return self.executable.parent.parent

        if self.system == "Darwin":
            for parent in self.executable.parents:
                if parent.suffix.lower() == ".app":
                    return parent.parent

        return self.executable.parent

    def find_macos_app(self):
        if self.system != "Darwin":
            return None

        for parent in self.executable.parents:
            if parent.suffix.lower() == ".app":
                return parent

        return None

    def application_url(self, port=None):
        if port is None:
            port = self.selected_port

        return (
            f"http://localhost:{int(port)}"
            f"{HOMEPAGE_PATH}"
        )

    def health_check_url(self, port):
        return f"http://127.0.0.1:{int(port)}/"

    # ========================================
    # ENVIRONMENT CONFIGURATION
    # ========================================

    def ensure_environment_file(self):
        """
        Create .env only when it does not exist.

        Never overwrite an existing student's settings.

        The current testing Compose configuration uses
        MySQL password 1234. The generated MySQL values
        are also kept at 1234 for compatibility.
        """

        if self.env_file.is_file():
            return False

        if not self.base_dir.is_dir():
            raise RuntimeError(
                "Application directory does not exist:\n"
                f"{self.base_dir}"
            )

        jwt_secret = secrets.token_hex(32)

        content = (
            "# Automation Platform Student Configuration\n"
            "# Automatically generated on first launch\n"
            "# Do not publish this file\n"
            "\n"
            f"JWT_SECRET={jwt_secret}\n"
            "MYSQL_PASSWORD=1234\n"
            "MYSQL_ROOT_PASSWORD=1234\n"
            "APP_PORT=8080\n"
        )

        try:
            with self.env_file.open(
                    "x",
                    encoding="utf-8",
                    newline="\n"
            ) as file:
                file.write(content)

            if self.system != "Windows":
                self.env_file.chmod(0o600)

        except FileExistsError:
            return False

        except OSError as error:
            raise RuntimeError(
                "Cannot create .env file in:\n"
                f"{self.base_dir}\n\n"
                f"{error}"
            ) from error

        return True

    # ========================================
    # SETTINGS
    # ========================================

    def load_saved_port(self):
        try:
            if self.settings_file.is_file():
                data = json.loads(
                    self.settings_file.read_text(
                        encoding="utf-8"
                    )
                )

                port = int(
                    data.get("port", START_PORT)
                )

                if 1024 <= port <= 65535:
                    return port

        except (
                OSError,
                ValueError,
                TypeError,
                json.JSONDecodeError
        ):
            pass

        return START_PORT

    def save_selected_port(self, port):
        self.selected_port = int(port)

        self.settings_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.settings_file.write_text(
            json.dumps(
                {"port": self.selected_port},
                indent=2
            ),
            encoding="utf-8"
        )

        self.port_text.set(
            f"Port: {self.selected_port}"
        )

        self.url_text.set(
            self.application_url()
        )

    # ========================================
    # USER INTERFACE
    # ========================================

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Action.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(12, 11)
        )

        main = tk.Frame(
            self.root,
            bg="#f1f5f9"
        )

        main.pack(
            fill="both",
            expand=True,
            padx=24,
            pady=18
        )

        tk.Label(
            main,
            text=APP_NAME,
            font=("Segoe UI", 24, "bold"),
            bg="#f1f5f9",
            fg="#1e3a8a"
        ).pack(anchor="w")

        tk.Label(
            main,
            text="Student Launcher - Docker Management",
            font=("Segoe UI", 11),
            bg="#f1f5f9",
            fg="#64748b"
        ).pack(
            anchor="w",
            pady=(3, 15)
        )

        # ====================================
        # APPLICATION STATUS
        # ====================================

        status_frame = tk.Frame(
            main,
            bg="#ffffff",
            highlightbackground="#dbe4f0",
            highlightthickness=1
        )

        status_frame.pack(
            fill="x",
            pady=(0, 12)
        )

        tk.Label(
            status_frame,
            text="Application Status",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#64748b"
        ).pack(
            anchor="w",
            padx=16,
            pady=(12, 3)
        )

        tk.Label(
            status_frame,
            textvariable=self.status_text,
            font=("Segoe UI", 13, "bold"),
            bg="#ffffff",
            fg="#1d4ed8"
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 12)
        )

        # ====================================
        # APPLICATION ADDRESS
        # ====================================

        port_frame = tk.Frame(
            main,
            bg="#ffffff",
            highlightbackground="#dbe4f0",
            highlightthickness=1
        )

        port_frame.pack(
            fill="x",
            pady=(0, 12)
        )

        tk.Label(
            port_frame,
            text="Homepage Address",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#64748b"
        ).pack(
            anchor="w",
            padx=16,
            pady=(12, 4)
        )

        tk.Label(
            port_frame,
            textvariable=self.url_text,
            font=("Consolas", 12, "bold"),
            bg="#ffffff",
            fg="#1d4ed8"
        ).pack(
            anchor="w",
            padx=16
        )

        tk.Label(
            port_frame,
            textvariable=self.port_text,
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#64748b"
        ).pack(
            anchor="w",
            padx=16,
            pady=(3, 12)
        )

        # ====================================
        # BUTTONS
        # ====================================

        actions = tk.Frame(
            main,
            bg="#f1f5f9"
        )

        actions.pack(fill="x")

        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        self.add_button(
            actions,
            "Start Application",
            self.start_application,
            0,
            0
        )

        self.add_button(
            actions,
            "Stop Application",
            self.stop_application,
            0,
            1
        )

        self.add_button(
            actions,
            "Update Application",
            self.update_application,
            1,
            0
        )

        self.add_button(
            actions,
            "Open Homepage",
            self.open_application,
            1,
            1,
            lock_during_action=False
        )

        self.add_button(
            actions,
            "Choose Port",
            self.choose_port,
            2,
            0
        )

        self.add_button(
            actions,
            "Check Status",
            self.check_status,
            2,
            1
        )

        self.add_button(
            actions,
            "View Logs",
            self.view_logs,
            3,
            0
        )

        self.add_button(
            actions,
            "Desktop Shortcut",
            self.create_desktop_shortcut,
            3,
            1,
            lock_during_action=False
        )

        # ====================================
        # LOGS
        # ====================================

        tk.Label(
            main,
            text="Activity & Logs",
            font=("Segoe UI", 12, "bold"),
            bg="#f1f5f9",
            fg="#0f172a"
        ).pack(
            anchor="w",
            pady=(15, 8)
        )

        self.output = scrolledtext.ScrolledText(
            main,
            height=9,
            state="disabled",
            wrap="word",
            font=("Consolas", 9),
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#ffffff",
            relief="flat",
            padx=12,
            pady=12
        )

        self.output.pack(
            fill="both",
            expand=True
        )

        self.log("Launcher ready.")
        self.log(f"Operating system: {self.system}")
        self.log(f"Project directory: {self.base_dir}")
        self.log(f"Selected port: {self.selected_port}")
        self.log(f"Homepage: {self.application_url()}")
        self.log("Docker Desktop / Docker Engine is required.")

        try:
            created = self.ensure_environment_file()

            if created:
                self.log(
                    "First launch: .env configuration created."
                )
            else:
                self.log(
                    "Existing .env configuration preserved."
                )

        except Exception as error:
            self.log(
                f"Environment configuration error: {error}"
            )
            self.status_text.set(
                "Configuration error - check logs"
            )

    def add_button(
            self,
            parent,
            text,
            command,
            row,
            column,
            lock_during_action=True
    ):
        button = ttk.Button(
            parent,
            text=text,
            command=command,
            style="Action.TButton"
        )

        button.grid(
            row=row,
            column=column,
            sticky="ew",
            padx=5,
            pady=5
        )

        if lock_during_action:
            self.action_buttons.append(button)

    def log(self, message):
        self.output.configure(state="normal")

        self.output.insert(
            "end",
            f"{message}\n"
        )

        self.output.see("end")
        self.output.configure(state="disabled")

    def process_events(self):
        while True:
            try:
                event_type, value = (
                    self.events.get_nowait()
                )

            except queue.Empty:
                break

            if event_type == "log":
                self.log(value)

            elif event_type == "status":
                self.status_text.set(value)

            elif event_type == "done":
                self.busy = False

                for button in self.action_buttons:
                    button.configure(state="normal")

            elif event_type == "open_browser":
                webbrowser.open(value)

        self.root.after(
            100,
            self.process_events
        )

    # ========================================
    # PORT DETECTION
    # ========================================

    @staticmethod
    def port_is_available(port):
        if not 1024 <= int(port) <= 65535:
            return False

        with socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
        ) as sock:
            try:
                sock.bind(
                    ("127.0.0.1", int(port))
                )

                return True

            except OSError:
                return False

    def find_available_port(
            self,
            start_port=START_PORT
    ):
        for port in range(
                start_port,
                MAX_PORT + 1
        ):
            if self.port_is_available(port):
                return port

        raise RuntimeError(
            "No available port found between "
            f"{start_port} and {MAX_PORT}."
        )

    def get_existing_backend_port(self):
        try:
            output = self.docker_compose(
                "port",
                "backend",
                "8080",
                timeout=15,
                selected_port=self.selected_port
            )

            for line in output.splitlines():
                match = re.search(
                    r":(\d+)\s*$",
                    line.strip()
                )

                if match:
                    return int(match.group(1))

        except Exception:
            pass

        return None

    def ask_for_available_port(
            self,
            title,
            message
    ):
        suggested = self.find_available_port()

        accepted = messagebox.askyesno(
            title,
            f"{message}\n\n"
            f"Suggested available port: {suggested}\n\n"
            f"Homepage:\n"
            f"{self.application_url(suggested)}\n\n"
            "Use this port?\n\n"
            "Choose No to enter another port."
        )

        if accepted:
            selected = suggested

        else:
            selected = simpledialog.askinteger(
                "Manual Port Selection",
                "Enter an available port (1024 - 65535):",
                initialvalue=suggested,
                minvalue=1024,
                maxvalue=65535,
                parent=self.root
            )

            if selected is None:
                return None

            if not self.port_is_available(selected):
                messagebox.showerror(
                    "Port Unavailable",
                    f"Port {selected} is already occupied."
                )

                return None

        return selected

    def choose_port(self):
        if self.busy:
            return

        existing = self.get_existing_backend_port()

        if existing is not None:
            self.save_selected_port(existing)

            messagebox.showinfo(
                "Application Port",
                "The Docker backend is already running "
                f"on port {existing}.\n\n"
                "Stop the backend before changing its port."
            )

            return

        selected = self.ask_for_available_port(
            "Automatic Port Selection",
            "The Launcher searched for a free host port."
        )

        if selected is None:
            return

        self.save_selected_port(selected)

        self.log(
            f"Selected application port: {selected}"
        )

        self.log(
            f"Homepage: {self.application_url()}"
        )

    def confirm_port_before_start(self):
        existing = self.get_existing_backend_port()

        if existing is not None:
            self.save_selected_port(existing)

            self.log(
                f"Using existing Docker backend port: {existing}"
            )

            return True

        if self.port_is_available(self.selected_port):
            return True

        selected = self.ask_for_available_port(
            "Port Already Occupied",
            f"Port {self.selected_port} is occupied."
        )

        if selected is None:
            return False

        self.save_selected_port(selected)

        self.log(
            f"Host port selected: {selected}"
        )

        return True

    # ========================================
    # DOCKER
    # ========================================

    def docker_environment(self, selected_port=None):
        env = os.environ.copy()

        port = (
            selected_port
            if selected_port is not None
            else self.selected_port
        )

        env["APP_PORT"] = str(port)

        return env

    def run_command(
            self,
            arguments,
            timeout=300,
            selected_port=None
    ):
        creationflags = (
            subprocess.CREATE_NO_WINDOW
            if self.system == "Windows"
            else 0
        )

        result = subprocess.run(
            arguments,
            cwd=self.base_dir,
            env=self.docker_environment(selected_port),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if output:
            self.events.put(
                ("log", output)
            )

        if result.returncode != 0:
            raise RuntimeError(
                error or
                f"Command failed ({result.returncode})."
            )

        return output

    def find_docker_executable(self):
        docker = shutil.which("docker")

        if docker:
            return docker

        candidates = []

        if self.system == "Windows":
            candidates.append(
                Path(
                    "C:/Program Files/Docker/"
                    "Docker/resources/bin/docker.exe"
                )
            )

        elif self.system == "Darwin":
            candidates.extend([
                Path("/usr/local/bin/docker"),
                Path("/opt/homebrew/bin/docker"),
                Path.home() / ".docker/bin/docker"
            ])

        elif self.system == "Linux":
            candidates.extend([
                Path("/usr/bin/docker"),
                Path("/usr/local/bin/docker"),
                Path.home() / ".docker/bin/docker"
            ])

        for path in candidates:
            if path.is_file():
                return str(path)

        raise RuntimeError(
            "Docker was not found.\n"
            "Install and start Docker Desktop "
            "or a compatible Docker Engine."
        )

    def docker_compose(
            self,
            *arguments,
            timeout=300,
            selected_port=None
    ):
        if not self.compose_file.is_file():
            raise RuntimeError(
                "Missing compose.yaml:\n"
                f"{self.compose_file}"
            )

        self.ensure_environment_file()

        docker = self.find_docker_executable()

        return self.run_command(
            [
                docker,
                "compose",
                "-p",
                COMPOSE_PROJECT_NAME,
                "-f",
                str(self.compose_file),
                *arguments
            ],
            timeout=timeout,
            selected_port=selected_port
        )

    # ========================================
    # BACKGROUND EXECUTION
    # ========================================

    def execute_async(self, title, action):
        if self.busy:
            return

        self.busy = True
        self.status_text.set(title)

        for button in self.action_buttons:
            button.configure(state="disabled")

        def worker():
            try:
                self.events.put(
                    ("log", f"\n--- {title} ---")
                )

                action()

            except subprocess.TimeoutExpired:
                self.events.put(
                    ("log", "Operation timed out.")
                )

                self.events.put(
                    ("status", "Operation timed out")
                )

            except Exception as error:
                self.events.put(
                    ("log", f"Error: {error}")
                )

                self.events.put(
                    ("status", "Error - check logs")
                )

            finally:
                self.events.put(
                    ("done", None)
                )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    # ========================================
    # BACKEND READINESS
    # ========================================

    def backend_is_ready(self, port):
        url = self.health_check_url(port)

        try:
            with urllib.request.urlopen(
                    url,
                    timeout=2
            ) as response:
                return response.status < 500

        except urllib.error.HTTPError as error:
            return error.code < 500

        except (
                urllib.error.URLError,
                TimeoutError,
                OSError
        ):
            return False

    def wait_for_backend(
            self,
            port,
            timeout=90
    ):
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if self.backend_is_ready(port):
                return True

            time.sleep(2)

        return False

    # ========================================
    # START APPLICATION
    # ========================================

    def start_application(self):
        if not self.confirm_port_before_start():
            return

        port = self.selected_port

        def action():
            self.docker_compose(
                "up",
                "-d",
                timeout=900,
                selected_port=port
            )

            self.events.put(
                ("log", "Docker Compose started.")
            )

            self.events.put(
                ("status", "Waiting for backend...")
            )

            if self.wait_for_backend(port):
                url = self.application_url(port)

                self.events.put(
                    ("status", f"Running on port {port}")
                )

                self.events.put(
                    ("log", f"Backend is responding on port {port}")
                )

                self.events.put(
                    ("log", f"Opening homepage: {url}")
                )

                self.events.put(
                    ("open_browser", url)
                )

            else:
                self.events.put(
                    ("status", "Backend not ready - check logs")
                )

                self.events.put(
                    (
                        "log",
                        "Backend did not respond within "
                        "90 seconds. Check Docker logs."
                    )
                )

        self.execute_async(
            "Starting application...",
            action
        )

    # ========================================
    # STOP APPLICATION
    # ========================================

    def stop_application(self):
        def action():
            self.docker_compose("stop")

            self.events.put(
                ("status", "Stopped")
            )

            self.events.put(
                ("log", "Application containers stopped.")
            )

        self.execute_async(
            "Stopping application...",
            action
        )

    # ========================================
    # UPDATE APPLICATION
    # ========================================

    def update_application(self):
        confirmed = messagebox.askyesno(
            "Update Application",
            "Download the latest Docker images "
            "and restart the application?\n\n"
            "The existing data volumes will be preserved."
        )

        if not confirmed:
            return

        if not self.confirm_port_before_start():
            return

        port = self.selected_port

        def action():
            self.docker_compose(
                "pull",
                timeout=1200,
                selected_port=port
            )

            self.docker_compose(
                "up",
                "-d",
                "--remove-orphans",
                timeout=900,
                selected_port=port
            )

            self.events.put(
                ("status", "Waiting for updated backend...")
            )

            if self.wait_for_backend(port):
                url = self.application_url(port)

                self.events.put(
                    ("status", f"Updated - port {port}")
                )

                self.events.put(
                    ("log", "Application update completed.")
                )

                self.events.put(
                    ("log", f"Opening homepage: {url}")
                )

                self.events.put(
                    ("open_browser", url)
                )

            else:
                self.events.put(
                    ("status", "Update started - check logs")
                )

        self.execute_async(
            "Updating application...",
            action
        )

    # ========================================
    # OPEN HOMEPAGE
    # ========================================

    def open_application(self):
        port = self.selected_port

        existing = self.get_existing_backend_port()

        if existing is not None:
            port = existing

            if port != self.selected_port:
                self.save_selected_port(port)

        url = self.application_url(port)

        self.log(
            f"Opening homepage: {url}"
        )

        webbrowser.open(url)

    # ========================================
    # CHECK STATUS
    # ========================================

    def check_status(self):
        def action():
            self.docker_compose(
                "ps",
                "-a"
            )

            self.events.put(
                ("status", "Status checked")
            )

        self.execute_async(
            "Checking Docker status...",
            action
        )

    # ========================================
    # VIEW LOGS
    # ========================================

    def view_logs(self):
        def action():
            self.docker_compose(
                "logs",
                "--tail",
                "80",
                timeout=30
            )

            self.events.put(
                ("status", "Logs loaded")
            )

        self.execute_async(
            "Loading logs...",
            action
        )

    # ========================================
    # DESKTOP DIRECTORY
    # ========================================

    def find_desktop_directory(self):

        if self.system == "Windows":
            try:
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-Command",
                        "[Environment]::GetFolderPath("
                        "'DesktopDirectory')"
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                desktop_path = result.stdout.strip()

                if (
                        result.returncode == 0
                        and desktop_path
                ):
                    desktop = Path(desktop_path)

                    if desktop.is_dir():
                        return desktop

            except Exception:
                pass

        elif self.system == "Linux":
            xdg = shutil.which("xdg-user-dir")

            if xdg:
                try:
                    result = subprocess.run(
                        [xdg, "DESKTOP"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )

                    desktop_path = result.stdout.strip()

                    if (
                            result.returncode == 0
                            and desktop_path
                    ):
                        desktop = Path(
                            desktop_path
                        ).expanduser()

                        if desktop.is_dir():
                            return desktop

                except Exception:
                    pass

        desktop = Path.home() / "Desktop"

        if desktop.is_dir():
            return desktop

        return None

    # ========================================
    # SHORTCUT PATH
    # ========================================

    def shortcut_path(self, desktop):
        if self.system == "Windows":
            return (
                    desktop /
                    "Automation Platform Launcher.lnk"
            )

        if self.system == "Darwin":
            return (
                    desktop /
                    "Automation Platform Launcher.command"
            )

        return (
                desktop /
                "automation-platform-launcher.desktop"
        )

    # ========================================
    # AUTOMATIC DESKTOP SHORTCUT
    # ========================================

    def create_first_run_shortcut(self):
        try:
            desktop = self.find_desktop_directory()

            if desktop is None:
                self.log(
                    "Desktop folder not found. "
                    "Use the Desktop Shortcut button later."
                )
                return

            shortcut = self.shortcut_path(desktop)

            if not shortcut.exists():
                self.create_desktop_shortcut(
                    show_message=False
                )

        except Exception as error:
            self.log(
                "Automatic shortcut creation skipped: "
                f"{error}"
            )

    def create_desktop_shortcut(
            self,
            show_message=True
    ):
        desktop = self.find_desktop_directory()

        if desktop is None:
            if show_message:
                messagebox.showerror(
                    "Desktop Not Found",
                    "The Desktop directory could not be located."
                )
            else:
                self.log("Desktop directory not found.")

            return

        shortcut = self.shortcut_path(desktop)

        try:
            if self.system == "Windows":
                self.create_windows_shortcut(shortcut)

            elif self.system == "Linux":
                self.create_linux_shortcut(shortcut)

            elif self.system == "Darwin":
                self.create_macos_shortcut(shortcut)

            else:
                raise RuntimeError(
                    f"Unsupported operating system: {self.system}"
                )

            self.log(
                f"Desktop shortcut created: {shortcut}"
            )

            if show_message:
                messagebox.showinfo(
                    "Desktop Shortcut",
                    "Shortcut created successfully:\n\n"
                    f"{shortcut}"
                )

        except Exception as error:
            self.log(
                f"Shortcut error: {error}"
            )

            if show_message:
                messagebox.showerror(
                    "Shortcut Error",
                    str(error)
                )

    # ========================================
    # LAUNCH COMMAND
    # ========================================

    def launch_command(self):
        if self.is_frozen:
            return (
                str(self.executable),
                []
            )

        return (
            sys.executable,
            [str(Path(__file__).resolve())]
        )

    # ========================================
    # WINDOWS SHORTCUT
    # ========================================

    def create_windows_shortcut(self, shortcut):
        executable, arguments = self.launch_command()

        def ps_quote(value):
            return "'" + str(value).replace(
                "'",
                "''"
            ) + "'"

        arguments_string = (
            subprocess.list2cmdline(arguments)
            if arguments
            else ""
        )

        # Use our ICO directly, not the Windows EXE icon cache.
        if self.icon_file.is_file():
            icon_location = f"{self.icon_file},0"
        else:
            icon_location = f"{executable},0"

        script = (
            "$shell = New-Object -ComObject WScript.Shell; "
            f"$shortcut = $shell.CreateShortcut({ps_quote(shortcut)}); "
            f"$shortcut.TargetPath = {ps_quote(executable)}; "
            f"$shortcut.Arguments = {ps_quote(arguments_string)}; "
            f"$shortcut.WorkingDirectory = {ps_quote(self.base_dir)}; "
            f"$shortcut.IconLocation = {ps_quote(icon_location)}; "
            "$shortcut.Save();"
        )

        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                script
            ],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or "Windows shortcut creation failed."
            )

    # ========================================
    # LINUX SHORTCUT
    # ========================================

    def create_linux_shortcut(self, shortcut):
        executable, arguments = self.launch_command()

        def desktop_quote(value):
            escaped = str(value).replace(
                "\\",
                "\\\\"
            ).replace(
                '"',
                '\\"'
            ).replace(
                "$",
                "\\$"
            ).replace(
                "`",
                "\\`"
            )

            return f'"{escaped}"'

        parts = [executable, *arguments]

        command = " ".join(
            desktop_quote(part)
            for part in parts
        )

        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Automation Platform Launcher\n"
            "Comment=Start and manage Automation Platform\n"
            f"Exec={command}\n"
            f"Path={self.base_dir}\n"
            "Terminal=false\n"
            "Categories=Development;\n"
        )

        shortcut.write_text(
            content,
            encoding="utf-8"
        )

        shortcut.chmod(
            shortcut.stat().st_mode | 0o111
        )

    # ========================================
    # MACOS SHORTCUT
    # ========================================

    def create_macos_shortcut(self, shortcut):
        macos_app = self.find_macos_app()

        if self.is_frozen and macos_app is not None:
            command = (
                    "open " +
                    shlex.quote(str(macos_app))
            )

        else:
            executable, arguments = self.launch_command()

            command = " ".join(
                shlex.quote(str(part))
                for part in [executable, *arguments]
            )

        content = (
            "#!/bin/bash\n"
            f"cd {shlex.quote(str(self.base_dir))}\n"
            f"{command}\n"
        )

        shortcut.write_text(
            content,
            encoding="utf-8"
        )

        shortcut.chmod(
            shortcut.stat().st_mode | 0o111
        )


if __name__ == "__main__":
    root = tk.Tk()
    StudentLauncher(root)
    root.mainloop()
