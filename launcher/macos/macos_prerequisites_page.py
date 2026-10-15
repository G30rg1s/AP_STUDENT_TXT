
"""
AUTOMATION PLATFORM - macOS PREREQUISITES WIZARD

macOS equivalent of the Windows WslSetupPage.

STEP 1: macOS system prerequisites
STEP 2: Docker Desktop installation wizard

Features:
- Automatic system diagnostics
- MacOSSystemChecker integration
- State-based setup actions
- User confirmation before real actions
- Thread-safe background workers
- Timestamped terminal logs
- Command timeout and error handling
- Post-action verification
- Manual installation commands
- Copy Selected / Copy All
- Continue / Install Manually Later

Automatic Step 1 remediation:
- Open an installed Docker Desktop application when
  its local engine is not reachable.

Docker installation belongs to Step 2.

No WSL, no systemctl, no sudo, no automatic reboot.
"""

import platform
import queue
import shlex
import subprocess
import threading
import tkinter as tk

from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from launcher.macos.macos_system_checker import (
    MacOSSystemChecker,
)


# ============================================================
# CONFIGURATION
# ============================================================

COLORS = {
    "terminal": "#0B1120",
    "text": "#E2E8F0",
    "success": "#4ADE80",
    "warning": "#FBBF24",
    "error": "#F87171",
    "heading": "#38BDF8",
    "timestamp": "#94A3B8",
}

MAX_COMMAND_SECONDS = 1800

DOCKER_INSTALL_URL = (
    "https://docs.docker.com/desktop/setup/install/mac-install/"
)

HOMEBREW_URL = "https://brew.sh/"

ACTIONS = {
    "open_docker": {
        "label": "Open Docker Desktop",
        "description": (
            "Launch the installed Docker Desktop application."
        ),
        "requires_authorization": False,
        "restart_after_success": False,
    },
}


# ============================================================
# SYSTEM HELPERS
# ============================================================

def detect_operating_system():
    system = platform.system()

    if system == "Darwin":
        version = platform.mac_ver()[0] or "Unknown"
        architecture = platform.machine()

        return (
            system,
            f"macOS {version} ({architecture})",
        )

    return system, system


def command_text(command):
    return shlex.join(command)


def docker_app_path(status):
    """
    Return a verified Docker Desktop application path.

    Only paths detected by MacOSSystemChecker are accepted.
    """
    if status is None:
        return None

    if not status.docker_desktop_installed:
        return None

    raw_path = status.docker_desktop_path

    if not raw_path:
        return None

    path = Path(raw_path)

    if (
            path.is_dir()
            and path.suffix.lower() == ".app"
            and (path / "Contents" / "Info.plist").is_file()
    ):
        return path

    return None


def run_command_with_logs(command, log_callback):
    """
    Execute an approved command and stream its output.

    Called only after explicit user confirmation.
    """
    log_callback(
        "> " + command_text(command)
    )

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    timed_out = threading.Event()

    def stop_if_timeout():
        if process.poll() is None:
            timed_out.set()

            try:
                process.kill()
            except OSError:
                pass

    timer = threading.Timer(
        MAX_COMMAND_SECONDS,
        stop_if_timeout,
    )

    timer.daemon = True
    timer.start()

    output_lines = []

    try:
        if process.stdout:
            for line in process.stdout:
                line = line.rstrip("\r\n")

                if line:
                    output_lines.append(line)
                    log_callback(line)

        code = process.wait()

    finally:
        timer.cancel()

        if process.stdout:
            process.stdout.close()

    if timed_out.is_set():
        raise subprocess.TimeoutExpired(
            command,
            MAX_COMMAND_SECONDS,
        )

    return code, "\n".join(output_lines)


# ============================================================
# macOS PREREQUISITES PAGE
# ============================================================

class MacOSPrerequisitesPage(ttk.Frame):

    def __init__(self, parent, on_continue=None):
        super().__init__(parent, padding=22)

        self.on_continue = on_continue

        self.system, self.system_name = (
            detect_operating_system()
        )

        self.checker = MacOSSystemChecker()

        self.events = queue.Queue()

        self.current_status = None
        self.busy = False
        self.installing = False

        self.status_var = tk.StringVar(
            value="System check pending"
        )

        self.message_var = tk.StringVar(
            value="Preparing macOS diagnostics."
        )

        self.os_var = tk.StringVar(
            value=self.system_name
        )

        self.progress_var = tk.StringVar(
            value="Waiting to start"
        )

        self.build_ui()

        self.after(
            100,
            self.process_events,
        )

        self.after(
            250,
            self.check_system,
        )

    # ========================================================
    # COMMON BUTTON LAYOUT
    # ========================================================

    @staticmethod
    def add_action(
            parent,
            row,
            column,
            title,
            description,
            command,
    ):
        frame = ttk.Frame(parent)

        frame.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=5,
            pady=5,
        )

        button = ttk.Button(
            frame,
            text=title,
            command=command,
        )

        button.pack(fill="x")

        options = (
            {"textvariable": description}
            if isinstance(description, tk.StringVar)
            else {"text": description}
        )

        ttk.Label(
            frame,
            wraplength=320,
            justify="left",
            font=("Helvetica", 9),
            **options,
        ).pack(
            anchor="w",
            pady=(5, 0),
        )

        return button

    # ========================================================
    # MAIN USER INTERFACE
    # ========================================================

    def build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)

        header = ttk.Frame(self)

        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )

        ttk.Label(
            header,
            text="Automation Platform",
            font=("Helvetica", 21, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header,
            text=(
                "Student Setup Wizard - "
                "System Requirements"
            ),
        ).pack(
            anchor="w",
            pady=(3, 0),
        )

        os_frame = ttk.LabelFrame(
            self,
            text="Detected Operating System",
            padding=14,
        )

        os_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )

        ttk.Label(
            os_frame,
            textvariable=self.os_var,
            font=("Helvetica", 12, "bold"),
        ).pack(anchor="w")

        status_frame = ttk.LabelFrame(
            self,
            text="Step 1 - macOS Prerequisites",
            padding=14,
        )

        status_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )

        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("Helvetica", 13, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            status_frame,
            textvariable=self.message_var,
            wraplength=690,
            justify="left",
        ).pack(
            anchor="w",
            pady=(7, 0),
        )

        progress_frame = ttk.Frame(self)

        progress_frame.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )

        progress_frame.columnconfigure(
            0,
            weight=1,
        )

        self.progress = ttk.Progressbar(
            progress_frame,
            mode="indeterminate",
        )

        self.progress.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        ttk.Label(
            progress_frame,
            textvariable=self.progress_var,
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(5, 0),
        )

        ttk.Label(
            self,
            text=(
                "System Diagnostics & "
                "Real Installation Logs"
            ),
            font=("Helvetica", 11, "bold"),
        ).grid(
            row=4,
            column=0,
            sticky="w",
            pady=(0, 7),
        )

        self.details_text = scrolledtext.ScrolledText(
            self,
            height=12,
            wrap="word",
            state="disabled",
            font=("Menlo", 10),
            bg=COLORS["terminal"],
            fg=COLORS["text"],
            insertbackground="white",
            selectbackground="#334155",
            selectforeground="white",
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=14,
        )

        self.details_text.grid(
            row=5,
            column=0,
            sticky="nsew",
            pady=(0, 12),
        )

        for tag in (
                "success",
                "warning",
                "error",
                "heading",
                "timestamp",
        ):
            self.details_text.tag_configure(
                tag,
                foreground=COLORS[tag],
            )

        actions = ttk.Frame(self)

        actions.grid(
            row=6,
            column=0,
            sticky="ew",
        )

        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        self.check_button = self.add_action(
            actions,
            0,
            0,
            "Check Again",
            "Recheck macOS system requirements.",
            self.check_system,
        )

        self.install_button = self.add_action(
            actions,
            0,
            1,
            "Install/Configure Automatically",
            (
                "Perform the next supported "
                "macOS setup action."
            ),
            self.confirm_installation,
        )

        self.manual_button = self.add_action(
            actions,
            1,
            0,
            "Manual Installation Commands",
            (
                "Read and copy macOS instructions. "
                "Nothing runs automatically."
            ),
            self.show_manual_commands,
        )

        self.continue_button = self.add_action(
            actions,
            1,
            1,
            "Install Manually Later",
            "Continue without changing your system.",
            self.continue_to_next,
        )

        self.install_button.configure(
            state="disabled"
        )

    # ========================================================
    # MANUAL INSTRUCTIONS
    # ========================================================

    def manual_instructions(self):
        status = self.current_status

        state = (
            status.state
            if status
            else "UNKNOWN"
        )

        lines = [
            "AUTOMATION PLATFORM - macOS SETUP",
            "=" * 44,
            "",
            f"Detected status: {state}",
            "",
            "IMPORTANT:",
            "- These instructions are for macOS.",
            "- Run commands in Terminal.",
            "- Review each command before executing it.",
            "- Administrator approval may be required.",
            "- This window NEVER executes commands.",
            "",
            ]

        if status:
            lines.extend([
                f"macOS version: {status.macos_version}",
                f"Architecture: {status.architecture}",
                f"Docker context: {status.docker_context}",
                "",
            ])

        if state == "READY":
            lines.extend([
                "All requirements are satisfied.",
                "",
                "Docker Desktop, Engine and Compose",
                "have been verified.",
                "",
            ])

        elif state == "UNSUPPORTED_ARCHITECTURE":
            lines.extend([
                "UNSUPPORTED ARCHITECTURE",
                "",
                "Check the Mac architecture:",
                "",
                "uname -m",
                "",
                "Official Docker requirements:",
                DOCKER_INSTALL_URL,
                "",
            ])

        elif state == "MACOS_VERSION_NEEDS_ATTENTION":
            lines.extend([
                "macOS VERSION REQUIRES ATTENTION",
                "",
                "Check your installed macOS version:",
                "",
                "sw_vers",
                "",
                "Verify compatibility with the Docker",
                "Desktop version you intend to install.",
                "",
                DOCKER_INSTALL_URL,
                "",
            ])

        elif state == "DOCKER_MISSING":
            lines.extend([
                "INSTALL DOCKER DESKTOP",
                "",
                "Docker Desktop was not detected.",
                "",
                "Use Step 2 - macOS Docker Setup.",
                "",
                "Official Docker installation page:",
                DOCKER_INSTALL_URL,
                "",
                "If Homebrew is already installed:",
                "",
                "brew install --cask docker",
                "",
                "Complete first-run setup in Docker Desktop.",
                "",
            ])

        elif state == "DOCKER_CLI_MISSING":
            lines.extend([
                "DOCKER CLI NOT AVAILABLE",
                "",
                "Docker Desktop exists but the docker",
                "command is unavailable.",
                "",
                "Check CLI discovery:",
                "",
                "command -v docker",
                "ls -l /usr/local/bin/docker",
                "ls -l /opt/homebrew/bin/docker",
                "ls -l \"$HOME/.docker/bin/docker\"",
                "",
                "Check Docker Desktop settings for",
                "the configured CLI tools location.",
                "",
                "Do not overwrite existing system links",
                "without checking where they point.",
                "",
            ])

        elif state == "DOCKER_DESKTOP_STOPPED":
            lines.extend([
                "START DOCKER DESKTOP",
                "",
                "Open the installed application:",
                "",
                "open -a Docker",
                "",
                "Complete first-run setup if requested.",
                "Wait until Docker Engine is ready.",
                "",
                "VERIFY:",
                "",
                "docker info",
                "docker compose version",
                "",
            ])

        elif state == "PERMISSION_DENIED":
            lines.extend([
                "DOCKER PERMISSION PROBLEM",
                "",
                "Review the current Docker connection:",
                "",
                "docker context show",
                "docker context ls",
                "docker info",
                "",
                "Check Docker Desktop permissions",
                "and the selected Docker context.",
                "",
                "Do not use chmod 666 on Docker sockets.",
                "",
            ])

        elif state == "REMOTE_DOCKER_CONTEXT":
            lines.extend([
                "REMOTE DOCKER CONTEXT DETECTED",
                "",
                "Inspect the active connection:",
                "",
                "docker context ls",
                "docker context show",
                "",
                "If Docker Desktop is installed,",
                "inspect the available local contexts.",
                "",
                "A common local Desktop context is:",
                "",
                "docker context use desktop-linux",
                "",
                "Run that command ONLY if this context",
                "exists and matches your configuration.",
                "",
                "Also check DOCKER_HOST and DOCKER_CONTEXT",
                "environment overrides.",
                "",
            ])

        elif state == "COMPOSE_MISSING":
            lines.extend([
                "DOCKER COMPOSE V2 MISSING",
                "",
                "Check the Compose plugin:",
                "",
                "docker compose version",
                "",
                "Docker Desktop normally includes Compose.",
                "Review Docker Desktop installation",
                "and CLI configuration.",
                "",
                DOCKER_INSTALL_URL,
                "",
            ])

        elif state == "NEEDS_ATTENTION":
            lines.extend([
                "ADDITIONAL DIAGNOSTICS",
                "",
                "sw_vers",
                "uname -m",
                "command -v docker",
                "docker --version",
                "docker context show",
                "docker context ls",
                "docker info",
                "docker compose version",
                "",
                "Review errors reported by the checker.",
                "",
            ])

        elif state == "NOT_APPLICABLE":
            lines.extend([
                "This setup page is intended for macOS.",
                "",
            ])

        else:
            lines.extend([
                "Click Check Again for diagnostics.",
                "",
            ])

        lines.extend([
            "GENERAL VERIFICATION",
            "",
            "sw_vers",
            "uname -m",
            "docker --version",
            "docker context show",
            "docker info",
            "docker compose version",
            "",
            "Return to the wizard and click Check Again.",
        ])

        return "\n".join(lines)

    # ========================================================
    # MANUAL COMMANDS WINDOW
    # ========================================================

    def show_manual_commands(self):
        window = tk.Toplevel(self)

        window.title(
            "macOS - Manual Installation Commands"
        )

        window.geometry("780x620")
        window.minsize(560, 420)

        window.transient(
            self.winfo_toplevel()
        )

        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)

        ttk.Label(
            window,
            text="Manual Installation Commands",
            font=("Helvetica", 16, "bold"),
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=18,
            pady=(17, 9),
        )

        content = scrolledtext.ScrolledText(
            window,
            font=("Menlo", 10),
            wrap="word",
            bg=COLORS["terminal"],
            fg=COLORS["text"],
            insertbackground="white",
            selectbackground="#334155",
            selectforeground="white",
            padx=15,
            pady=15,
            undo=False,
        )

        content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
        )

        manual = self.manual_instructions()

        content.insert("1.0", manual)
        content.configure(state="disabled")

        buttons = ttk.Frame(window)

        buttons.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=18,
            pady=14,
        )

        def copy_selection():
            try:
                selected = content.get(
                    tk.SEL_FIRST,
                    tk.SEL_LAST,
                )

            except tk.TclError:
                messagebox.showinfo(
                    "Copy",
                    "Select text with the mouse first.",
                    parent=window,
                )
                return

            window.clipboard_clear()
            window.clipboard_append(selected)
            window.update_idletasks()

        def copy_all():
            window.clipboard_clear()
            window.clipboard_append(manual)
            window.update_idletasks()

        ttk.Button(
            buttons,
            text="Copy Selected",
            command=copy_selection,
        ).pack(
            side="left",
            padx=(0, 8),
        )

        ttk.Button(
            buttons,
            text="Copy All",
            command=copy_all,
        ).pack(side="left")

        ttk.Button(
            buttons,
            text="Close",
            command=window.destroy,
        ).pack(side="right")

        content.focus_set()

    # ========================================================
    # LOG TERMINAL
    # ========================================================

    def append_log(self, message, level=None):
        self.details_text.configure(
            state="normal"
        )

        lines = str(message).splitlines() or [""]

        for line in lines:
            timestamp = datetime.now().strftime(
                "%H:%M:%S"
            )

            self.details_text.insert(
                tk.END,
                f"[{timestamp}] ",
                "timestamp",
            )

            normalized = line.strip().lower()

            if level:
                tag = level

            elif normalized.startswith((
                    "error:",
                    "failed:",
                    "final status: failed",
            )):
                tag = "error"

            elif normalized.startswith((
                    "warning:",
                    "final status: attention",
                    "final status: next",
            )):
                tag = "warning"

            elif normalized.startswith((
                    "success:",
                    "final status: ready",
            )):
                tag = "success"

            elif normalized.startswith((
                    "===",
                    "> ",
            )):
                tag = "heading"

            else:
                tag = None

            self.details_text.insert(
                tk.END,
                line + "\n",
                tag,
                )

        self.details_text.see(tk.END)

        self.details_text.configure(
            state="disabled"
        )

    def clear_logs(self):
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.configure(state="disabled")

    def log_from_worker(self, message, level=None):
        self.events.put(
            ("log", (message, level))
        )

    # ========================================================
    # UI EVENT QUEUE
    # ========================================================

    def process_events(self):
        try:
            while True:
                try:
                    kind, data = self.events.get_nowait()

                except queue.Empty:
                    break

                if kind == "log":
                    self.append_log(*data)

                elif kind == "check_result":
                    self.show_result(data)

                elif kind == "check_error":
                    self.show_error(data)

                elif kind == "install_result":
                    self.installation_finished(data)

        except tk.TclError:
            return

        try:
            if self.winfo_exists():
                self.after(
                    100,
                    self.process_events,
                )

        except tk.TclError:
            pass

    # ========================================================
    # BUSY STATE
    # ========================================================

    def set_busy(self, busy, label=None):
        self.busy = busy

        state = (
            "disabled"
            if busy
            else "normal"
        )

        for button in (
                self.check_button,
                self.install_button,
                self.continue_button,
        ):
            button.configure(
                state=state
            )

        # Manual instructions remain available.
        self.manual_button.configure(
            state="normal"
        )

        if busy:
            self.progress.start(12)

            self.progress_var.set(
                label or "Working..."
            )

        else:
            self.progress.stop()

            self.progress_var.set(
                label or "Operation finished"
            )

    # ========================================================
    # SYSTEM CHECK
    # ========================================================

    def check_system(self):
        if self.busy:
            return

        self.current_status = None
        self.clear_logs()

        self.set_busy(
            True,
            "Checking macOS prerequisites...",
        )

        self.status_var.set(
            "Checking system requirements..."
        )

        self.message_var.set(
            "Checking macOS and Docker prerequisites."
        )

        self.append_log(
            "=== AUTOMATION PLATFORM SYSTEM CHECK ===",
            "heading",
        )

        self.append_log(
            "Detected Operating System: "
            + self.system_name
        )

        threading.Thread(
            target=self._check_worker,
            daemon=True,
        ).start()

    def _check_worker(self):
        try:
            self.log_from_worker(
                "=== macOS PREREQUISITES DIAGNOSTICS ===",
                "heading",
            )

            result = self.checker.check()

            self.log_from_worker(
                "Checker state: " + result.state
            )

            self.log_from_worker(result.details)

            self.events.put(
                ("check_result", result)
            )

        except Exception as error:
            self.events.put(
                ("check_error", str(error))
            )

    # ========================================================
    # DISPLAY CHECK RESULT
    # ========================================================

    def show_result(self, result):
        self.current_status = result

        self.set_busy(
            False,
            "System check completed",
        )

        labels = {
            "READY": "macOS Requirements Ready",
            "DOCKER_MISSING": "Docker Desktop Not Installed",
            "DOCKER_CLI_MISSING": "Docker CLI Unavailable",
            "DOCKER_DESKTOP_STOPPED": (
                "Docker Desktop Is Not Running"
            ),
            "PERMISSION_DENIED": (
                "Docker Permission Required"
            ),
            "REMOTE_DOCKER_CONTEXT": (
                "Remote Docker Context Selected"
            ),
            "COMPOSE_MISSING": (
                "Docker Compose Is Missing"
            ),
            "UNSUPPORTED_ARCHITECTURE": (
                "Unsupported Mac Architecture"
            ),
            "MACOS_VERSION_NEEDS_ATTENTION": (
                "macOS Version Requires Attention"
            ),
            "NEEDS_ATTENTION": (
                "macOS Setup Requires Attention"
            ),
            "NOT_APPLICABLE": "macOS Required",
        }

        self.status_var.set(
            labels.get(
                result.state,
                result.state,
            )
        )

        self.message_var.set(
            result.message
        )

        if result.state == "READY":
            self.append_log(
                "SUCCESS: macOS Docker requirements satisfied.",
                "success",
            )

            self.append_log(
                "FINAL STATUS: READY",
                "success",
            )

            self.install_button.configure(
                state="disabled"
            )

            self.continue_button.configure(
                text="Continue to Docker Setup"
            )

        else:
            self.append_log(
                "WARNING: " + result.message,
                "warning",
                )

            self.append_log(
                "FINAL STATUS: ATTENTION REQUIRED",
                "warning",
            )

            action = self.get_installation_action()

            self.install_button.configure(
                state=(
                    "normal"
                    if action
                    else "disabled"
                )
            )

            self.continue_button.configure(
                text="Install Manually Later"
            )

    def show_error(self, message):
        self.current_status = None

        self.set_busy(
            False,
            "System check failed",
        )

        self.status_var.set(
            "macOS Check Failed"
        )

        self.message_var.set(message)

        self.append_log(
            "ERROR: " + message,
            "error",
            )

        self.append_log(
            "FINAL STATUS: FAILED",
            "error",
        )

        self.install_button.configure(
            state="disabled"
        )

    # ========================================================
    # CHOOSE NEXT AUTOMATIC ACTION
    # ========================================================

    def get_installation_action(self):
        if self.system != "Darwin":
            return None

        status = self.current_status

        if status is None:
            return None

        if status.state != "DOCKER_DESKTOP_STOPPED":
            return None

        if docker_app_path(status) is None:
            return None

        return "open_docker"

    # ========================================================
    # CONFIRM AUTOMATIC ACTION
    # ========================================================

    def confirm_installation(self):
        if self.busy:
            return

        action = self.get_installation_action()

        if action is None:
            messagebox.showinfo(
                "macOS Setup",
                "No supported automatic action is available "
                "for the current state.\n\n"
                "Review diagnostics or use "
                "Manual Installation Commands.",
                parent=self,
            )
            return

        app_path = docker_app_path(
            self.current_status
        )

        if app_path is None:
            messagebox.showerror(
                "Docker Desktop",
                "Docker Desktop could not be located.",
                parent=self,
            )
            return

        command = [
            "open",
            str(app_path),
        ]

        confirmed = messagebox.askyesno(
            "Confirm macOS Setup",
            "This will launch an installed application.\n\n"
            f"Action: {ACTIONS[action]['label']}\n\n"
            f"Command:\n{command_text(command)}\n\n"
            "Docker Desktop may display first-run setup "
            "or request system permissions.\n"
            "No automatic reboot will occur.\n\n"
            "Continue?",
            parent=self,
        )

        if confirmed:
            self.install_system(
                action,
                command,
            )

        else:
            self.append_log(
                "WARNING: Setup cancelled by user.",
                "warning",
            )

    # ========================================================
    # START REAL ACTION
    # ========================================================

    def install_system(self, action, command):
        if self.busy:
            return

        if action not in ACTIONS:
            return

        self.installing = True

        self.set_busy(
            True,
            "Running macOS setup...",
        )

        self.status_var.set(
            ACTIONS[action]["label"] + "..."
        )

        self.message_var.set(
            "Please wait. Watch command output below."
        )

        self.append_log(
            "=== REAL macOS SETUP STARTED ===",
            "heading",
        )

        self.append_log(
            "Action: " + ACTIONS[action]["label"]
        )

        threading.Thread(
            target=self._install_worker,
            args=(action, command),
            daemon=True,
        ).start()

    # ========================================================
    # INSTALLATION WORKER
    # ========================================================

    def _install_worker(self, action, command):
        outcome = {
            "action": action,
            "exit_code": None,
            "restart_required": False,
            "error": None,
        }

        try:
            code, output = run_command_with_logs(
                command,
                self.log_from_worker,
            )

            outcome["exit_code"] = code

            self.log_from_worker(
                f"COMMAND EXIT CODE: {code}"
            )

        except subprocess.TimeoutExpired:
            outcome["error"] = (
                "System command timed out."
            )

        except Exception as error:
            outcome["error"] = str(error)

        if outcome["error"] is None and outcome["exit_code"] == 0:
            self.log_from_worker(
                "Docker Desktop launch requested. "
                "Waiting briefly before verification."
            )

            # 'open' returning 0 means the launch request
            # succeeded, not that Docker Engine is ready.
            threading.Event().wait(3)

        try:
            self.log_from_worker(
                "=== POST-ACTION CHECK ===",
                "heading",
            )

            status = self.checker.check()

            self.log_from_worker(
                f"Checker state: {status.state}"
            )

            self.log_from_worker(status.details)

        except Exception as error:
            status = None

            self.log_from_worker(
                "WARNING: Final check failed: "
                + str(error),
                "warning",
                )

        self.events.put((
            "install_result",
            (outcome, status),
        ))

    # ========================================================
    # INSTALLATION RESULT
    # ========================================================

    def installation_finished(self, data):
        outcome, status = data

        self.installing = False
        self.current_status = status

        self.set_busy(
            False,
            "Setup attempt finished",
        )

        self.append_log(
            "=== FINAL INSTALLATION RESULT ===",
            "heading",
        )

        error = outcome.get("error")
        code = outcome.get("exit_code")

        if error or code != 0:
            message = (
                    error
                    or f"Command exited with code {code}."
            )

            self.status_var.set(
                "macOS Setup Failed"
            )

            self.message_var.set(message)

            self.append_log(
                "ERROR: " + message,
                "error",
                )

            self.append_log(
                "FINAL STATUS: FAILED",
                "error",
            )

        elif status and status.state == "READY":
            self.status_var.set(
                "macOS Requirements Ready"
            )

            self.message_var.set(
                "Docker Desktop and Compose verified."
            )

            self.append_log(
                "SUCCESS: macOS setup is ready.",
                "success",
            )

            self.append_log(
                "FINAL STATUS: READY",
                "success",
            )

            self.continue_button.configure(
                text="Continue to Docker Setup"
            )

        else:
            next_state = (
                status.state
                if status
                else "UNKNOWN"
            )

            self.status_var.set(
                "Additional macOS Setup Required"
            )

            self.message_var.set(
                "Docker Desktop launch was requested. "
                "Complete first-run setup, wait for "
                "the Engine to start, then click Check Again."
            )

            self.append_log(
                f"WARNING: Next macOS state: {next_state}",
                "warning",
            )

            self.append_log(
                "FINAL STATUS: NEXT STEP REQUIRED",
                "warning",
            )

        # Recheck before another automatic action.
        self.install_button.configure(
            state="disabled"
        )

    # ========================================================
    # CONTINUE OR SKIP
    # ========================================================

    def continue_to_next(self):
        if self.busy:
            return

        if self.on_continue:
            self.on_continue(
                self.current_status
            )
            return

        ready = (
                self.current_status is not None
                and self.current_status.state == "READY"
        )

        if ready:
            messagebox.showinfo(
                "System Check Complete",
                "macOS requirements satisfied.\n\n"
                "Next: Docker Desktop setup.",
                parent=self,
            )

        else:
            messagebox.showinfo(
                "Install Manually Later",
                "You may continue without completing "
                "macOS setup now.\n\n"
                "Automation Platform requires working "
                "Docker Desktop and Compose to start.",
                parent=self,
            )


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    if platform.system() != "Darwin":
        raise SystemExit(
            "macOS Prerequisites Wizard runs only on macOS."
        )

    root = tk.Tk()

    root.title(
        "Automation Platform - macOS Prerequisites"
    )

    root.geometry("900x790")
    root.minsize(740, 650)

    page = MacOSPrerequisitesPage(root)

    page.pack(
        fill="both",
        expand=True,
    )

    root.mainloop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
