
"""
AUTOMATION PLATFORM - LINUX PREREQUISITES WIZARD

Linux equivalent of Windows WslSetupPage.

Step 1: Linux system prerequisites
Step 2: Docker installation wizard

Features:
- Automatic system check
- LinuxSystemChecker integration
- State-based setup actions
- User confirmation before system changes
- Background workers and thread-safe UI queue
- Live terminal logs
- Command timeout
- Post-action verification
- Manual installation commands with copy support
- Continue / Install Manually Later

No WSL commands are used.

Docker package installation belongs to Step 2.

Automatic remediation in this module is limited to
starting an inactive Docker systemd service on
supported Ubuntu/Debian installations, with explicit
user approval and PolicyKit authorization.

The application does not automatically reboot,
modify group membership, or overwrite configuration.
"""

import platform
import queue
import shlex
import shutil
import subprocess
import threading
import tkinter as tk

from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

from launcher.linux.linux_system_checker import (
    LinuxSystemChecker,
)


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

ACTIONS = {
    "start_docker": {
        "label": "Start Docker Engine",
        "command": [
            "pkexec",
            "systemctl",
            "start",
            "docker",
        ],
        "requires_authorization": True,
        "restart_after_success": False,
    },
}


def detect_operating_system():
    if platform.system() != "Linux":
        return platform.system(), platform.system()

    distro = LinuxSystemChecker.get_distribution()

    return "Linux", distro["name"]


def command_text(command):
    return shlex.join(command)


def run_command_with_logs(command, log_callback):
    """
    Execute an approved command and stream its output.

    This function is called only after user confirmation.
    """
    log_callback("> " + command_text(command))

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


class LinuxPrerequisitesPage(ttk.Frame):

    def __init__(self, parent, on_continue=None):
        super().__init__(parent, padding=22)

        self.on_continue = on_continue

        self.system, self.system_name = (
            detect_operating_system()
        )

        self.checker = LinuxSystemChecker()
        self.events = queue.Queue()

        self.current_status = None
        self.busy = False
        self.installing = False

        self.status_var = tk.StringVar(
            value="System check pending"
        )

        self.message_var = tk.StringVar(
            value="Preparing Linux diagnostics."
        )

        self.os_var = tk.StringVar(
            value=self.system_name
        )

        self.progress_var = tk.StringVar(
            value="Waiting to start"
        )

        self.build_ui()

        self.after(100, self.process_events)
        self.after(250, self.check_system)

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

        ttk.Label(
            frame,
            text=description,
            wraplength=320,
            justify="left",
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
            font=("DejaVu Sans", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header,
            text="Student Setup Wizard - System Requirements",
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
            font=("DejaVu Sans", 11, "bold"),
        ).pack(anchor="w")

        status_frame = ttk.LabelFrame(
            self,
            text="Step 1 - Linux Prerequisites",
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
            font=("DejaVu Sans", 12, "bold"),
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
            text="System Diagnostics & Real Installation Logs",
            font=("DejaVu Sans", 10, "bold"),
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
            font=("DejaVu Sans Mono", 9),
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

        for tag in COLORS:
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
            "Recheck Linux system prerequisites.",
            self.check_system,
        )

        self.install_button = self.add_action(
            actions,
            0,
            1,
            "Install/Configure Automatically",
            "Perform the next supported setup action.",
            self.confirm_installation,
        )

        self.manual_button = self.add_action(
            actions,
            1,
            0,
            "Manual Installation Commands",
            "Read and copy commands. Nothing runs automatically.",
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
            "AUTOMATION PLATFORM - LINUX SETUP",
            "=" * 42,
            "",
            f"Detected status: {state}",
            "",
            "IMPORTANT:",
            "- Commands below are for Linux.",
            "- Use only commands appropriate to your system.",
            "- Read each command before executing it.",
            "- Administrator authorization may be required.",
            "- This window NEVER executes commands.",
            "",
            ]

        if state == "READY":
            lines.extend([
                "All requirements are satisfied.",
                "",
            ])

        elif state == "UNSUPPORTED_DISTRIBUTION":
            lines.extend([
                "AUTOMATIC SETUP NOT SUPPORTED",
                "",
                "The current setup supports Ubuntu/Debian.",
                "Do not execute Ubuntu/Debian installation",
                "commands on another distribution.",
                "",
            ])

        elif state == "UNSUPPORTED_ARCHITECTURE":
            lines.extend([
                "ARCHITECTURE NOT SUPPORTED",
                "",
                "Verify that your Linux machine and Docker",
                "packages support this CPU architecture.",
                "",
                "uname -m",
                "",
            ])

        elif state == "DOCKER_MISSING":
            lines.extend([
                "DOCKER ENGINE INSTALLATION",
                "",
                "Docker is missing or its CLI is unusable.",
                "",
                "Use Step 2 - Linux Docker Setup.",
                "",
                "Official documentation:",
                "https://docs.docker.com/engine/install/",
                "",
            ])

        elif state == "DAEMON_STOPPED":
            lines.extend([
                "START DOCKER SERVICE",
                "",
                "sudo systemctl start docker",
                "",
                "VERIFY:",
                "systemctl is-active docker",
                "docker info",
                "",
                "If systemd is not managing your Docker",
                "daemon, use the service instructions",
                "for your installation.",
                "",
            ])

        elif state == "SESSION_REFRESH_REQUIRED":
            lines.extend([
                "USER SESSION REFRESH REQUIRED",
                "",
                "Your Docker group membership is configured",
                "but is not active in the current session.",
                "",
                "Log out of the desktop session completely.",
                "Then log back in and reopen this wizard.",
                "",
                "VERIFY:",
                "id -nG",
                "docker info",
                "",
            ])

        elif state == "PERMISSION_DENIED":
            lines.extend([
                "DOCKER PERMISSION PROBLEM",
                "",
                "Check current groups:",
                "id -nG",
                "",
                "Check Docker:",
                "docker info",
                "",
                "If you choose Docker group access,",
                "understand that membership effectively",
                "grants root-level privileges.",
                "",
                "For a standard rootful Docker Engine:",
                "sudo usermod -aG docker \"$USER\"",
                "",
                "Log out and log back in afterward.",
                "",
                "Do not change socket permissions",
                "with chmod 666.",
                "",
            ])

        elif state == "COMPOSE_MISSING":
            lines.extend([
                "DOCKER COMPOSE V2 MISSING",
                "",
                "Use Step 2 - Linux Docker Setup to install",
                "Compose from configured repositories.",
                "",
                "VERIFY:",
                "docker compose version",
                "",
            ])

        elif state == "NEEDS_ATTENTION":
            lines.extend([
                "ADDITIONAL DIAGNOSTICS",
                "",
                "docker --version",
                "docker info",
                "docker context show",
                "docker compose version",
                "",
                "If systemd manages Docker:",
                "systemctl status docker --no-pager",
                "",
            ])

        elif state == "NOT_APPLICABLE":
            lines.extend([
                "This setup page is intended for Linux.",
                "",
            ])

        else:
            lines.extend([
                "Run Check Again for diagnostics.",
                "",
            ])

        lines.extend([
            "GENERAL VERIFICATION",
            "",
            "uname -m",
            "docker --version",
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
            "Linux - Manual Installation Commands"
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
            font=("DejaVu Sans", 15, "bold"),
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=18,
            pady=(17, 9),
        )

        content = scrolledtext.ScrolledText(
            window,
            font=("DejaVu Sans Mono", 9),
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

        for line in str(message).splitlines() or [""]:
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

            elif normalized.startswith(("===", "> ")):
                tag = "heading"

            else:
                tag = None

            self.details_text.insert(
                tk.END,
                line + "\n",
                tag,
                )

        self.details_text.see(tk.END)
        self.details_text.configure(state="disabled")

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
                self.after(100, self.process_events)
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
            button.configure(state=state)

        # Manual instructions remain available.
        self.manual_button.configure(state="normal")

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
            "Checking Linux prerequisites...",
        )

        self.status_var.set(
            "Checking system requirements..."
        )

        self.message_var.set(
            "Checking Linux and Docker prerequisites."
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
                "=== LINUX PREREQUISITES DIAGNOSTICS ===",
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
            "READY": "Linux Requirements Ready",
            "DOCKER_MISSING": "Docker Installation Required",
            "DAEMON_STOPPED": "Docker Service Is Stopped",
            "PERMISSION_DENIED": "Docker Permission Required",
            "SESSION_REFRESH_REQUIRED": (
                "New Login Session Required"
            ),
            "COMPOSE_MISSING": "Docker Compose Is Missing",
            "UNSUPPORTED_DISTRIBUTION": (
                "Unsupported Linux Distribution"
            ),
            "UNSUPPORTED_ARCHITECTURE": (
                "Unsupported CPU Architecture"
            ),
            "NEEDS_ATTENTION": (
                "Linux Setup Requires Attention"
            ),
            "NOT_APPLICABLE": "Linux Required",
        }

        self.status_var.set(
            labels.get(
                result.state,
                result.state,
            )
        )

        self.message_var.set(result.message)

        if result.state == "READY":
            self.append_log(
                "SUCCESS: Linux Docker requirements satisfied.",
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
            "Linux Check Failed"
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
        if self.system != "Linux":
            return None

        status = self.current_status

        if status is None:
            return None

        if status.state != "DAEMON_STOPPED":
            return None

        distro = LinuxSystemChecker.get_distribution()

        if distro["id"] not in (
                "ubuntu",
                "debian",
        ):
            return None

        if (
                shutil.which("pkexec") is None
                or shutil.which("systemctl") is None
        ):
            return None

        service = self.checker.check_docker_service()

        if (
                service["active"] is False
                and service["status"] in (
                "inactive",
                "failed",
                "deactivating",
        )
        ):
            return "start_docker"

        return None

    # ========================================================
    # CONFIRM AUTOMATIC ACTION
    # ========================================================

    def confirm_installation(self):
        if self.busy:
            return

        action = self.get_installation_action()

        if action is None:
            messagebox.showinfo(
                "Linux Setup",
                "No supported automatic action is available "
                "for the current state.\n\n"
                "Review the diagnostics or use "
                "Manual Installation Commands.",
                parent=self,
            )
            return

        info = ACTIONS[action]

        command = [
            shutil.which("pkexec") or "pkexec",
            shutil.which("systemctl") or "systemctl",
            "start",
            "docker",
            ]

        confirmed = messagebox.askyesno(
            "Confirm Linux Setup",
            "This is a REAL system operation.\n\n"
            f"Action: {info['label']}\n\n"
            f"Command:\n{command_text(command)}\n\n"
            "Linux will request administrator "
            "authorization through PolicyKit.\n"
            "No automatic reboot will occur.\n\n"
            "Continue?",
            parent=self,
        )

        if confirmed:
            self.install_system(action, command)
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
            "Running Linux setup...",
        )

        self.status_var.set(
            ACTIONS[action]["label"] + "..."
        )

        self.message_var.set(
            "Please wait. Watch command output below."
        )

        self.append_log(
            "=== REAL LINUX SETUP STARTED ===",
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

        try:
            self.log_from_worker(
                "=== POST-INSTALLATION CHECK ===",
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
                "Linux Setup Failed"
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
                "Linux Requirements Ready"
            )

            self.message_var.set(
                "All Linux Docker requirements verified."
            )

            self.append_log(
                "SUCCESS: Linux setup is ready.",
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
                "Additional Linux Setup Required"
            )

            self.message_var.set(
                "This action completed. "
                "Click Check Again for the next step."
            )

            self.append_log(
                f"WARNING: Next Linux state: {next_state}",
                "warning",
            )

            self.append_log(
                "FINAL STATUS: NEXT STEP REQUIRED",
                "warning",
            )

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
                "Linux requirements satisfied.\n\n"
                "Next: Docker Engine setup.",
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Install Manually Later",
                "You may continue without completing "
                "Linux setup now.\n\n"
                "Automation Platform requires working "
                "Docker Engine and Compose to start.",
                parent=self,
            )


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    if platform.system() != "Linux":
        raise SystemExit(
            "Linux Prerequisites Wizard runs only on Linux."
        )

    root = tk.Tk()

    root.title(
        "Automation Platform - Linux Prerequisites"
    )

    root.geometry("900x790")
    root.minsize(740, 650)

    page = LinuxPrerequisitesPage(root)

    page.pack(
        fill="both",
        expand=True,
    )

    root.mainloop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
