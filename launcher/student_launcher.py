
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

from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk


APP_NAME = "Automation Platform"
COMPOSE_PROJECT_NAME = "automation-platform-student"

START_PORT = 8080
MAX_PORT = 8200
HOMEPAGE_PATH = "/automation/homepage"


# ============================================================
# AUTOMATIC DOCKER PATH REPAIR
# ============================================================

def docker_folders():
    if platform.system() != "Windows":
        return []

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
        program_files
        / "Docker"
        / "Docker"
        / "resources"
        / "bin",

        local_app
        / "Programs"
        / "DockerDesktop"
        / "resources"
        / "bin",
        ]


def refresh_docker_path():
    """
    Updates PATH inside the running Launcher.

    All Docker child processes inherit this PATH.

    Does not change permanent Windows settings.
    Does not require administrator permissions.
    """

    if platform.system() != "Windows":
        return []

    current = os.environ.get("PATH", "")

    known = {
        os.path.normcase(os.path.normpath(path))
        for path in current.split(os.pathsep)
        if path
    }

    added = []

    for folder in docker_folders():
        docker_exe = folder / "docker.exe"

        if not docker_exe.is_file():
            continue

        normalized = os.path.normcase(
            os.path.normpath(str(folder))
        )

        if normalized not in known:
            added.append(str(folder))
            known.add(normalized)

    if added:
        os.environ["PATH"] = os.pathsep.join(
            added + [current]
        )

    return added


# ============================================================
# STUDENT LAUNCHER
# ============================================================

class StudentLauncher:

    def __init__(self, root):
        self.root = root

        self.root.title(f"{APP_NAME} Launcher")
        self.root.geometry("800x730")
        self.root.minsize(670, 600)
        self.root.configure(bg="#f1f5f9")

        self.system = platform.system()
        self.is_frozen = getattr(sys, "frozen", False)

        self.executable = Path(
            sys.executable if self.is_frozen else __file__
        ).resolve()

        self.base_dir = self.find_project_directory()

        self.compose_file = self.base_dir / "compose.yaml"
        self.icon_file = self.base_dir / "AutomationPlatform.ico"

        # Windows: preserve existing paths and configuration.
        if self.system == "Windows":
            self.env_file = self.base_dir / ".env"

            self.settings_dir = (
                    Path.home() / ".automation-platform-launcher"
            )

        # Linux / macOS: keep private configuration
        # in the user's home directory.
        else:
            self.settings_dir = (
                    Path.home() / ".automation-platform-student"
            )

            self.env_file = self.settings_dir / ".env"

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

        added = refresh_docker_path()

        self.log("Launcher ready.")
        self.log(f"Operating system: {self.system}")
        self.log(f"Project directory: {self.base_dir}")
        self.log(f"Selected port: {self.selected_port}")
        self.log(f"Homepage: {self.application_url()}")

        if added:
            self.log(
                "SUCCESS: Docker PATH updated automatically."
            )

            for folder in added:
                self.log(
                    f"Docker binaries directory: {folder}"
                )
        else:
            self.log(
                "Docker PATH check completed."
            )

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
                f"Error: Environment configuration: {error}"
            )

            self.status_text.set(
                "Configuration error"
            )

        self.root.after(
            100,
            self.process_events
        )

        if self.is_frozen:
            self.root.after(
                800,
                self.create_first_run_shortcut
            )

    # ========================================================
    # PROJECT PATHS
    # ========================================================

    def find_project_directory(self):
        if not self.is_frozen:
            return self.executable.parent.parent

        if self.system == "Darwin":
            for parent in self.executable.parents:
                if parent.suffix.lower() == ".app":
                    return parent.parent

        return self.executable.parent

    def find_macos_app(self):
        if self.system == "Darwin":
            for parent in self.executable.parents:
                if parent.suffix.lower() == ".app":
                    return parent

        return None

    def application_url(self, port=None):
        selected = (
            port if port is not None
            else self.selected_port
        )

        return (
            f"http://localhost:{int(selected)}"
            f"{HOMEPAGE_PATH}"
        )

    # ========================================================
    # .ENV CONFIGURATION
    # ========================================================

    def ensure_environment_file(self):
        """
        Windows:
            Use the existing project .env.

        Linux/macOS:
            Store the private .env in the user's home
            directory and preserve an existing configuration.

        Never overwrite an existing .env file.
        """

        if self.env_file.is_file():
            return False

        if not self.base_dir.is_dir():
            raise RuntimeError(
                f"Project directory not found: {self.base_dir}"
            )

        if self.env_file.exists():
            raise RuntimeError(
                f"Configuration path is not a file: {self.env_file}"
            )

        self.env_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        content = None

        # On Linux/macOS, preserve any existing project .env.
        if self.system != "Windows":
            legacy_env = self.base_dir / ".env"

            if legacy_env.is_file():
                content = legacy_env.read_text(
                    encoding="utf-8"
                )

        if content is None:
            content = (
                "# Automation Platform Student Configuration\n"
                "# Do not publish this file\n"
                "\n"
                f"JWT_SECRET={secrets.token_hex(32)}\n"
                "MYSQL_PASSWORD=1234\n"
                "MYSQL_ROOT_PASSWORD=1234\n"
                "APP_PORT=8080\n"
            )

        try:
            if self.system == "Windows":
                with self.env_file.open(
                        "x",
                        encoding="utf-8",
                        newline="\n"
                ) as stream:
                    stream.write(content)

            else:
                descriptor = os.open(
                    str(self.env_file),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600
                )

                with os.fdopen(
                        descriptor,
                        "w",
                        encoding="utf-8",
                        newline="\n"
                ) as stream:
                    stream.write(content)

            return True

        except FileExistsError:
            return False

    # ========================================================
    # SAVED PORT
    # ========================================================

    def load_saved_port(self):
        try:
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

        except (OSError, ValueError, TypeError):
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

    # ========================================================
    # USER INTERFACE
    # ========================================================

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

        self.info_panel(
            main,
            "Application Status",
            self.status_text,
            13
        )

        address = tk.Frame(
            main,
            bg="white",
            highlightbackground="#dbe4f0",
            highlightthickness=1
        )

        address.pack(
            fill="x",
            pady=(0, 12)
        )

        tk.Label(
            address,
            text="Homepage Address",
            font=("Segoe UI", 10, "bold"),
            bg="white",
            fg="#64748b"
        ).pack(
            anchor="w",
            padx=16,
            pady=(12, 4)
        )

        tk.Label(
            address,
            textvariable=self.url_text,
            font=("Consolas", 12, "bold"),
            bg="white",
            fg="#1d4ed8"
        ).pack(
            anchor="w",
            padx=16
        )

        tk.Label(
            address,
            textvariable=self.port_text,
            font=("Segoe UI", 10),
            bg="white",
            fg="#64748b"
        ).pack(
            anchor="w",
            padx=16,
            pady=(3, 12)
        )

        actions = tk.Frame(
            main,
            bg="#f1f5f9"
        )

        actions.pack(fill="x")
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        buttons = [
            (
                "Start Application",
                self.start_application,
                True
            ),
            (
                "Stop Application",
                self.stop_application,
                True
            ),
            (
                "Update Application",
                self.update_application,
                True
            ),
            (
                "Open Homepage",
                self.open_application,
                False
            ),
            (
                "Choose Port",
                self.choose_port,
                True
            ),
            (
                "Check Status",
                self.check_status,
                True
            ),
            (
                "View Logs",
                self.view_logs,
                True
            ),
            (
                "Desktop Shortcut",
                self.create_desktop_shortcut,
                False
            ),
        ]

        for index, (label, callback, lock) in enumerate(buttons):
            button = ttk.Button(
                actions,
                text=label,
                command=callback,
                style="Action.TButton"
            )

            button.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=5,
                pady=5
            )

            if lock:
                self.action_buttons.append(button)

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
            font=("Consolas", 10),
            bg="#0B1120",
            fg="#E2E8F0",
            insertbackground="white",
            selectbackground="#334155",
            selectforeground="white",
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=14
        )

        self.output.pack(
            fill="both",
            expand=True
        )

        for tag, color in (
                ("success", "#4ADE80"),
                ("warning", "#FBBF24"),
                ("error", "#F87171"),
                ("heading", "#38BDF8"),
                ("timestamp", "#94A3B8")
        ):
            self.output.tag_configure(
                tag,
                foreground=color
            )

    @staticmethod
    def info_panel(parent, heading, variable, size):
        panel = tk.Frame(
            parent,
            bg="white",
            highlightbackground="#dbe4f0",
            highlightthickness=1
        )

        panel.pack(
            fill="x",
            pady=(0, 12)
        )

        tk.Label(
            panel,
            text=heading,
            font=("Segoe UI", 10, "bold"),
            bg="white",
            fg="#64748b"
        ).pack(
            anchor="w",
            padx=16,
            pady=(12, 3)
        )

        tk.Label(
            panel,
            textvariable=variable,
            font=("Segoe UI", size, "bold"),
            bg="white",
            fg="#1d4ed8"
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 12)
        )

    # ========================================================
    # LOGGING
    # ========================================================

    def log(self, message):
        self.output.configure(
            state="normal"
        )

        for line in str(message).splitlines() or [""]:
            stamp = datetime.now().strftime(
                "%H:%M:%S"
            )

            self.output.insert(
                tk.END,
                f"[{stamp}] ",
                "timestamp"
            )

            text = line.strip().lower()

            if (
                    text.startswith("error")
                    or any(
                token in text
                for token in (
                        "failed",
                        "timed out",
                        "denied"
                )
            )
            ):
                tag = "error"

            elif text.startswith((
                    "---",
                    ">",
                    "container "
            )):
                tag = "heading"

            elif any(
                    token in text
                    for token in (
                            "warning",
                            "not found",
                            "not ready",
                            "unavailable"
                    )
            ):
                tag = "warning"

            elif any(
                    token in text
                    for token in (
                            "success",
                            "ready",
                            "running",
                            "started",
                            "completed",
                            "healthy"
                    )
            ):
                tag = "success"

            else:
                tag = None

            self.output.insert(
                tk.END,
                line + "\n",
                tag
            )

        self.output.see(tk.END)

        self.output.configure(
            state="disabled"
        )

    # ========================================================
    # BACKGROUND EVENT QUEUE
    # ========================================================

    def process_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()

                if kind == "log":
                    self.log(value)

                elif kind == "status":
                    self.status_text.set(value)

                elif kind == "done":
                    self.busy = False

                    for button in self.action_buttons:
                        button.configure(
                            state="normal"
                        )

                elif kind == "open_browser":
                    webbrowser.open(value)

        except queue.Empty:
            pass

        try:
            if self.root.winfo_exists():
                self.root.after(
                    100,
                    self.process_events
                )

        except tk.TclError:
            pass

    # ========================================================
    # PORT UTILITIES
    # ========================================================

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

    def find_available_port(self, start_port=START_PORT):
        for port in range(
                start_port,
                MAX_PORT + 1
        ):
            if self.port_is_available(port):
                return port

        raise RuntimeError(
            f"No free port from {start_port} to {MAX_PORT}."
        )

    def get_existing_backend_port(self):
        try:
            output = self.docker_compose(
                "port",
                "backend",
                "8080",
                timeout=15
            )

            for line in output.splitlines():
                found = re.search(
                    r":(\d+)\s*$",
                    line
                )

                if found:
                    return int(found.group(1))

        except Exception:
            pass

        return None

    def ask_for_available_port(self, title, message):
        suggested = self.find_available_port()

        accepted = messagebox.askyesno(
            title,
            f"{message}\n\n"
            f"Suggested available port: {suggested}\n\n"
            f"Homepage:\n"
            f"{self.application_url(suggested)}\n\n"
            "Use this port?\n\n"
            "Choose No to enter another port.",
            parent=self.root
        )

        if accepted:
            return suggested

        selected = simpledialog.askinteger(
            "Manual Port Selection",
            "Enter an available port (1024-65535):",
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
                f"Port {selected} is occupied.",
                parent=self.root
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
                f"Backend already uses port {existing}.\n"
                "Stop it before changing.",
                parent=self.root
            )
            return

        selected = self.ask_for_available_port(
            "Automatic Port Selection",
            "The Launcher found a free host port."
        )

        if selected is not None:
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
        return True

    # ========================================================
    # DOCKER ENVIRONMENT
    # ========================================================

    def docker_environment(self, selected_port=None):
        refresh_docker_path()

        env = os.environ.copy()

        env["APP_PORT"] = str(
            selected_port
            if selected_port is not None
            else self.selected_port
        )

        return env

    def find_docker_executable(self):
        refresh_docker_path()

        docker = shutil.which("docker")

        if docker:
            return docker

        for folder in docker_folders():
            candidate = folder / "docker.exe"

            if candidate.is_file():
                return str(candidate)

        if self.system == "Darwin":
            candidates = [
                Path("/usr/local/bin/docker"),
                Path("/opt/homebrew/bin/docker"),
                Path.home() / ".docker/bin/docker",
                ]

        elif self.system == "Linux":
            candidates = [
                Path("/usr/bin/docker"),
                Path("/usr/local/bin/docker"),
            ]

        else:
            candidates = []

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)

        raise RuntimeError(
            "Docker CLI not found.\n"
            "Install or start Docker, then retry."
        )


    # ========================================================
    # AUTOMATIC DOCKER DESKTOP STARTUP
    # ========================================================

    def ensure_docker_ready(self, timeout=120):
        docker = self.find_docker_executable()
        env = self.docker_environment(self.selected_port)

        flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if self.system == "Windows"
            else 0
        )

        def engine_is_ready():
            try:
                result = subprocess.run(
                    [docker, "info", "--format", "{{.ServerVersion}}"],
                    cwd=self.base_dir,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=8,
                    creationflags=flags
                )
                return result.returncode == 0

            except (OSError, subprocess.TimeoutExpired):
                return False

        if engine_is_ready():
            self.events.put((
                "log",
                "Docker Engine is already running."
            ))
            return

        if self.system != "Windows":
            raise RuntimeError(
                "Docker Engine is not running. "
                "Start Docker and try again."
            )

        docker_desktop = Path(
            os.environ.get(
                "PROGRAMFILES",
                r"C:\Program Files"
            )
        ) / "Docker" / "Docker" / "Docker Desktop.exe"

        if not docker_desktop.is_file():
            raise RuntimeError(
                "Docker Desktop executable not found. "
                "Install Docker Desktop or start it manually."
            )

        self.events.put((
            "log",
            "Docker Engine is stopped. Starting Docker Desktop..."
        ))

        subprocess.Popen(
            [str(docker_desktop)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags
        )

        self.events.put((
            "status",
            "Waiting for Docker Desktop..."
        ))

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if engine_is_ready():
                self.events.put((
                    "log",
                    "Docker Engine is ready."
                ))
                return

            time.sleep(3)

        raise RuntimeError(
            "Docker Desktop did not become ready within "
            f"{timeout} seconds. Open Docker Desktop "
            "and check its status."
        )


    # ========================================================
    # REAL DOCKER COMMANDS
    # ========================================================

    def run_command(
            self,
            arguments,
            timeout=300,
            selected_port=None
    ):
        env = self.docker_environment(selected_port)

        if self.system == "Windows":
            flags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0
            )
        else:
            flags = 0

        result = subprocess.run(
            arguments,
            cwd=self.base_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=flags
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if output:
            self.events.put(
                ("log", output)
            )

        if result.returncode != 0:
            raise RuntimeError(
                error
                or output
                or f"Command failed ({result.returncode})."
            )

        if error:
            self.events.put(
                ("log", error)
            )

        return output

    def docker_compose(
            self,
            *arguments,
            timeout=300,
            selected_port=None
    ):
        if not self.compose_file.is_file():
            raise RuntimeError(
                f"Missing compose.yaml: {self.compose_file}"
            )

        self.ensure_environment_file()

        docker = self.find_docker_executable()

        return self.run_command(
            [
                docker,
                "compose",
                "--env-file",
                str(self.env_file),
                "-p",
                COMPOSE_PROJECT_NAME,
                "-f",
                str(self.compose_file),
                *arguments
            ],
            timeout=timeout,
            selected_port=selected_port
        )

    # ========================================================
    # ASYNC EXECUTION
    # ========================================================

    def execute_async(self, title, action):
        if self.busy:
            return

        self.busy = True
        self.status_text.set(title)

        for button in self.action_buttons:
            button.configure(
                state="disabled"
            )

        def worker():
            try:
                self.events.put((
                    "log",
                    f"\n--- {title} ---"
                ))

                action()

            except subprocess.TimeoutExpired:
                self.events.put((
                    "log",
                    "Error: Operation timed out."
                ))

                self.events.put((
                    "status",
                    "Operation timed out"
                ))

            except Exception as error:
                self.events.put((
                    "log",
                    f"Error: {error}"
                ))

                self.events.put((
                    "status",
                    "Error - check logs"
                ))

            finally:
                self.events.put(
                    ("done", None)
                )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    # ========================================================
    # BACKEND READINESS
    # ========================================================

    @staticmethod
    def backend_is_ready(port):
        url = f"http://127.0.0.1:{int(port)}/"

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

    def wait_for_backend(self, port, timeout=90):
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if self.backend_is_ready(port):
                return True

            time.sleep(2)

        return False

    # ========================================================
    # START APPLICATION
    # ========================================================

    def start_application(self):
        if self.busy:
            return

        if not self.confirm_port_before_start():
            return

        port = self.selected_port

        def action():
            self.ensure_docker_ready()

            self.docker_compose(
                "up",
                "-d",
                timeout=900,
                selected_port=port
            )

            self.events.put((
                "log",
                "Docker Compose started."
            ))

            self.events.put((
                "status",
                "Waiting for backend..."
            ))

            if self.wait_for_backend(port):
                url = self.application_url(port)

                self.events.put((
                    "status",
                    f"Running on port {port}"
                ))

                self.events.put((
                    "log",
                    f"Backend is responding on port {port}"
                ))

                self.events.put((
                    "log",
                    f"Opening homepage: {url}"
                ))

                self.events.put((
                    "open_browser",
                    url
                ))

            else:
                self.events.put((
                    "status",
                    "Backend not ready - check logs"
                ))

                self.events.put((
                    "log",
                    "Backend did not respond within "
                    "90 seconds. Check Docker logs."
                ))

        self.execute_async(
            "Starting application...",
            action
        )

    # ========================================================
    # STOP APPLICATION
    # ========================================================

    def stop_application(self):
        def action():
            self.docker_compose("stop")

            self.events.put((
                "status",
                "Stopped"
            ))

            self.events.put((
                "log",
                "Application containers stopped."
            ))

        self.execute_async(
            "Stopping application...",
            action
        )

    # ========================================================
    # UPDATE APPLICATION
    # ========================================================

    def update_application(self):
        if self.busy:
            return

        confirmed = messagebox.askyesno(
            "Update Application",
            "Download the latest Docker images "
            "and restart?\n\n"
            "Existing data volumes are preserved.",
            parent=self.root
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

            self.events.put((
                "status",
                "Waiting for updated backend..."
            ))

            if self.wait_for_backend(port):
                url = self.application_url(port)

                self.events.put((
                    "status",
                    f"Updated - port {port}"
                ))

                self.events.put((
                    "log",
                    "Application update completed."
                ))

                self.events.put((
                    "open_browser",
                    url
                ))

            else:
                self.events.put((
                    "status",
                    "Update started - check logs"
                ))

        self.execute_async(
            "Updating application...",
            action
        )

    # ========================================================
    # OPEN HOMEPAGE
    # ========================================================

    def open_application(self):
        existing = self.get_existing_backend_port()

        port = (
            existing
            if existing is not None
            else self.selected_port
        )

        if port != self.selected_port:
            self.save_selected_port(port)

        url = self.application_url(port)

        self.log(
            f"Opening homepage: {url}"
        )

        webbrowser.open(url)

    # ========================================================
    # CHECK STATUS
    # ========================================================

    def check_status(self):
        def action():
            self.docker_compose(
                "ps",
                "-a"
            )

            self.events.put((
                "status",
                "Status checked"
            ))

        self.execute_async(
            "Checking Docker status...",
            action
        )

    # ========================================================
    # VIEW LOGS
    # ========================================================

    def view_logs(self):
        def action():
            self.docker_compose(
                "logs",
                "--tail",
                "80",
                timeout=30
            )

            self.events.put((
                "status",
                "Logs loaded"
            ))

        self.execute_async(
            "Loading logs...",
            action
        )

    # ========================================================
    # DESKTOP DIRECTORY
    # ========================================================

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
                    timeout=10,
                    creationflags=getattr(
                        subprocess,
                        "CREATE_NO_WINDOW",
                        0
                    )
                )

                if result.returncode == 0:
                    candidate = Path(
                        result.stdout.strip()
                    )

                    if candidate.is_dir():
                        return candidate

            except (
                    OSError,
                    subprocess.TimeoutExpired
            ):
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

                    candidate = Path(
                        result.stdout.strip()
                    ).expanduser()

                    if (
                            result.returncode == 0
                            and candidate.is_dir()
                    ):
                        return candidate

                except (
                        OSError,
                        subprocess.TimeoutExpired
                ):
                    pass

        candidate = Path.home() / "Desktop"

        return candidate if candidate.is_dir() else None

    # ========================================================
    # DESKTOP SHORTCUT
    # ========================================================

    def shortcut_path(self, desktop):
        if self.system == "Windows":
            return (
                    desktop
                    / "Automation Platform Launcher.lnk"
            )

        if self.system == "Darwin":
            return (
                    desktop
                    / "Automation Platform Launcher.command"
            )

        return (
                desktop
                / "automation-platform-launcher.desktop"
        )

    def create_first_run_shortcut(self):
        try:
            desktop = self.find_desktop_directory()

            if (
                    desktop
                    and not self.shortcut_path(desktop).exists()
            ):
                self.create_desktop_shortcut(
                    show_message=False
                )

        except Exception as error:
            self.log(
                "Automatic shortcut creation skipped: "
                + str(error)
            )

    def launch_command(self):
        if self.is_frozen:
            # The unified executable accepts --launcher.
            return str(self.executable), ["--launcher"]

        return (
            sys.executable,
            [str(Path(__file__).resolve())]
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
                    "Cannot locate the Desktop folder.",
                    parent=self.root
                )
            return

        shortcut = self.shortcut_path(desktop)

        try:
            executable, arguments = self.launch_command()

            if self.system == "Windows":

                def ps_quote(value):
                    return (
                            "'"
                            + str(value).replace("'", "''")
                            + "'"
                    )

                args = (
                    subprocess.list2cmdline(arguments)
                    if arguments
                    else ""
                )

                if self.icon_file.is_file():
                    icon = f"{self.icon_file},0"
                else:
                    icon = f"{executable},0"

                script = (
                    "$shell = New-Object "
                    "-ComObject WScript.Shell; "
                    f"$shortcut = $shell.CreateShortcut("
                    f"{ps_quote(shortcut)}); "
                    f"$shortcut.TargetPath = "
                    f"{ps_quote(executable)}; "
                    f"$shortcut.Arguments = "
                    f"{ps_quote(args)}; "
                    f"$shortcut.WorkingDirectory = "
                    f"{ps_quote(self.base_dir)}; "
                    f"$shortcut.IconLocation = "
                    f"{ps_quote(icon)}; "
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
                    creationflags=getattr(
                        subprocess,
                        "CREATE_NO_WINDOW",
                        0
                    )
                )

                if result.returncode != 0:
                    raise RuntimeError(
                        result.stderr.strip()
                        or "Shortcut creation failed."
                    )

            elif self.system == "Linux":
                parts = [executable, *arguments]

                command = " ".join(
                    '"'
                    + str(part)
                    .replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("$", "\\$")
                    + '"'
                    for part in parts
                )

                content = (
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    "Name=Automation Platform Launcher\n"
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

            elif self.system == "Darwin":
                app = self.find_macos_app()

                if self.is_frozen and app:
                    command = (
                            "open "
                            + shlex.quote(str(app))
                            + " --args --launcher"
                    )
                else:
                    command = " ".join(
                        shlex.quote(str(part))
                        for part in (
                            executable,
                            *arguments
                        )
                    )

                shortcut.write_text(
                    "#!/bin/bash\n"
                    f"cd {shlex.quote(str(self.base_dir))}\n"
                    f"{command}\n",
                    encoding="utf-8"
                )

                shortcut.chmod(
                    shortcut.stat().st_mode | 0o111
                )

            else:
                raise RuntimeError(
                    "Unsupported operating system: "
                    + self.system
                )

            self.log(
                f"Desktop shortcut created: {shortcut}"
            )

            if show_message:
                messagebox.showinfo(
                    "Desktop Shortcut",
                    f"Shortcut created:\n{shortcut}",
                    parent=self.root
                )

        except Exception as error:
            self.log(
                f"Error: Shortcut creation: {error}"
            )

            if show_message:
                messagebox.showerror(
                    "Shortcut Error",
                    str(error),
                    parent=self.root
                )


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    root = tk.Tk()
    StudentLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
