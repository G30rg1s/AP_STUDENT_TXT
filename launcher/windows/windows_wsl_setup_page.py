
import ctypes
import json
import locale
import os
import platform
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk

from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from launcher.windows.windows_wsl_checker import WslChecker, APP_DIR, RESTART_MARKER


# ============================================================
# AUTOMATION PLATFORM - WSL SETUP WIZARD
# ============================================================
#
# REAL installation workflow:
#
# 1. Enable VirtualMachinePlatform (UAC)
# 2. Restart Windows when required
# 3. Install WSL (UAC)
# 4. Set default WSL version to 2
# 5. Install Ubuntu
# 6. Convert Ubuntu from WSL 1 to WSL 2 if needed
# 7. Verify the actual installation
#
# Extra feature:
# Manual Installation Commands window
# - Read-only instructions
# - Copy Selected
# - Copy All
# - No automatic execution
#
# The main launcher runs without administrator privileges.
# Only privileged installation actions request Windows UAC.
#
# No automatic restart.
# No distribution deletion.
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
HELPER_FLAG = "--wsl-elevated-helper"


ACTIONS = {
    "enable_vmp": {
        "label": "Enable Virtual Machine Platform",
        "command": [
            "dism.exe",
            "/Online",
            "/Enable-Feature",
            "/FeatureName:VirtualMachinePlatform",
            "/All",
            "/NoRestart",
        ],
        "elevated": True,
        "restart_after_success": True,
    },

    "install_wsl": {
        "label": "Install Windows Subsystem for Linux",
        "command": [
            "wsl.exe",
            "--install",
            "--no-distribution",
        ],
        "elevated": True,
        "restart_after_success": True,
    },

    "set_wsl2": {
        "label": "Configure WSL 2 as default",
        "command": [
            "wsl.exe",
            "--set-default-version",
            "2",
        ],
        "elevated": False,
        "restart_after_success": False,
    },

    "install_ubuntu": {
        "label": "Download and install Ubuntu",
        "command": [
            "wsl.exe",
            "--install",
            "-d",
            "Ubuntu",
            "--no-launch",
        ],
        "elevated": False,
        "restart_after_success": False,
    },

    "convert_ubuntu": {
        "label": "Convert Ubuntu from WSL 1 to WSL 2",
        "command": [
            "wsl.exe",
            "--set-version",
            "Ubuntu",
            "2",
        ],
        "elevated": False,
        "restart_after_success": False,
    },
}


# ============================================================
# SYSTEM HELPERS
# ============================================================

def detect_operating_system():
    system = platform.system()

    if system == "Windows":
        version = platform.version()

        try:
            build = int(version.split(".")[-1])
        except (ValueError, IndexError):
            build = 0

        if build >= 22000:
            name = "Windows 11"
        else:
            name = f"Windows {platform.release()}"

        return system, f"{name} (Build {version})"

    if system == "Darwin":
        return system, f"macOS {platform.mac_ver()[0]}"

    if system == "Linux":
        try:
            release = platform.freedesktop_os_release()
            return system, release.get(
                "PRETTY_NAME",
                "Linux"
            )
        except (AttributeError, OSError):
            return system, "Linux"

    return system, system


def is_administrator():
    if platform.system() != "Windows":
        return False

    try:
        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )
    except (AttributeError, OSError):
        return False


def decode_bytes(data):
    if not data:
        return ""

    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode(
            "utf-16",
            errors="replace"
        )

    if b"\x00" in data:
        return data.decode(
            "utf-16-le",
            errors="replace"
        )

    try:
        return data.decode("utf-8")
    except UnicodeError:
        encoding = locale.getpreferredencoding(False)

        return data.decode(
            encoding,
            errors="replace"
        )


def command_text(command):
    return subprocess.list2cmdline(command)


def mark_restart_required():
    APP_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    RESTART_MARKER.write_text(
        json.dumps({
            "timestamp": time.time(),
            "reason": "WSL installation phase",
        }),
        encoding="utf-8"
    )


def output_requires_restart(output):
    text = output.casefold()

    phrases = (
        "restart required",
        "reboot required",
        "restart your computer",
        "reboot your computer",
        "απαιτείται επανεκκίνηση",
        "απαιτεί επανεκκίνηση",
    )

    return any(
        phrase in text
        for phrase in phrases
    )


# ============================================================
# REAL COMMAND RUNNER
# ============================================================

def run_command_with_logs(command, log_callback):
    flags = getattr(
        subprocess,
        "CREATE_NO_WINDOW",
        0
    )

    log_callback(
        "> " + command_text(command)
    )

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        bufsize=0,
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
        stop_if_timeout
    )

    timer.daemon = True
    timer.start()

    output_lines = []

    try:
        while True:
            chunk = process.stdout.readline()

            if not chunk:
                break

            line = decode_bytes(chunk).strip(
                "\r\n\x00 "
            )

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
            MAX_COMMAND_SECONDS
        )

    return code, "\n".join(output_lines)


# ============================================================
# ELEVATED HELPER
# ============================================================

def elevated_helper_main(action, workdir):
    if action not in ACTIONS:
        return 2

    if not ACTIONS[action]["elevated"]:
        return 2

    if not is_administrator():
        return 5

    folder = Path(workdir)

    log_path = folder / "output.log"
    result_path = folder / "result.json"

    if not log_path.is_file():
        return 6

    if not result_path.is_file():
        return 6

    result = {
        "action": action,
        "exit_code": None,
        "restart_required": False,
        "error": None,
    }

    try:
        with log_path.open(
                "a",
                encoding="utf-8",
                buffering=1
        ) as logfile:

            def log(line):
                logfile.write(
                    str(line) + "\n"
                )
                logfile.flush()

            log("=== ELEVATED WINDOWS SETUP ===")
            log("Administrator: YES")
            log(
                "Action: " + ACTIONS[action]["label"]
            )

            try:
                code, output = run_command_with_logs(
                    ACTIONS[action]["command"],
                    log
                )

                result["exit_code"] = code

                result["restart_required"] = (
                        code in (3010, 1641)
                        or output_requires_restart(output)
                        or (
                                code == 0
                                and ACTIONS[action]["restart_after_success"]
                        )
                )

                log(
                    f"COMMAND EXIT CODE: {code}"
                )

            except Exception as error:
                result["error"] = str(error)
                log(
                    "ERROR: " + str(error)
                )

    except OSError as error:
        result["error"] = str(error)

    try:
        with result_path.open(
                "r+",
                encoding="utf-8"
        ) as result_file:
            result_file.seek(0)
            result_file.truncate()

            json.dump(
                result,
                result_file
            )

            result_file.flush()
            os.fsync(result_file.fileno())

    except OSError:
        return 8

    successful = (
            not result["error"]
            and result["exit_code"] in (0, 3010, 1641)
    )

    return 0 if successful else 1


# ============================================================
# REQUEST WINDOWS UAC
# ============================================================

def request_uac(action, folder):
    try:
        executable = sys.executable

        if getattr(sys, "frozen", False):
            args = [
                HELPER_FLAG,
                action,
                str(folder),
            ]
        else:
            args = [
                str(Path(__file__).resolve()),
                HELPER_FLAG,
                action,
                str(folder),
            ]

        parameters = subprocess.list2cmdline(args)

        code = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            parameters,
            str(Path(__file__).resolve().parent),
            1,
        )

        if code <= 32:
            return (
                False,
                f"UAC was cancelled or failed (code {code})."
            )

        return True, None

    except Exception as error:
        return False, str(error)


# ============================================================
# WSL SETUP PAGE
# ============================================================

class WslSetupPage(ttk.Frame):

    def __init__(self, parent, on_continue=None):
        super().__init__(
            parent,
            padding=22
        )

        self.on_continue = on_continue

        self.system, self.system_name = (
            detect_operating_system()
        )

        self.checker = WslChecker()
        self.events = queue.Queue()

        self.current_status = None
        self.busy = False
        self.installing = False

        self.status_var = tk.StringVar(
            value="System check pending"
        )

        self.message_var = tk.StringVar(
            value="Preparing system diagnostics."
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
            self.process_events
        )

        self.after(
            250,
            self.check_wsl
        )

    # ========================================================
    # COMMON BUTTON LAYOUT
    # ========================================================

    def add_action(
            self,
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

        ttk.Label(
            frame,
            text=description,
            wraplength=320,
            justify="left",
            font=("Segoe UI", 9)
        ).pack(
            anchor="w",
            pady=(5, 0)
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
            pady=(0, 12)
        )

        ttk.Label(
            header,
            text="Automation Platform",
            font=("Segoe UI", 21, "bold")
        ).pack(anchor="w")

        ttk.Label(
            header,
            text="Student Setup Wizard - System Requirements",
            font=("Segoe UI", 10)
        ).pack(
            anchor="w",
            pady=(3, 0)
        )

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
            textvariable=self.os_var,
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w")

        status_frame = ttk.LabelFrame(
            self,
            text="Step 1 - WSL 2 & Ubuntu",
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
            wraplength=690,
            justify="left"
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
            textvariable=self.progress_var,
            font=("Segoe UI", 9)
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(5, 0)
        )

        ttk.Label(
            self,
            text="System Diagnostics & Real Installation Logs",
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
            insertbackground="#FFFFFF",
            selectbackground="#334155",
            selectforeground="#FFFFFF",
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

        for tag in (
                "success",
                "warning",
                "error",
                "heading",
                "timestamp"
        ):
            options = {
                "foreground": COLORS[tag]
            }

            if tag == "heading":
                options["font"] = (
                    "Consolas",
                    10,
                    "bold"
                )

            self.details_text.tag_configure(
                tag,
                **options
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
            "Recheck WSL 2 and Ubuntu.",
            self.check_wsl
        )

        self.install_button = self.add_action(
            actions,
            0,
            1,
            "Install/Configure WSL-2 Automatically",
            "Perform the next real setup step (UAC if needed).",
            self.confirm_installation
        )

        # NEW: Read-only manual installation help.
        self.manual_button = self.add_action(
            actions,
            1,
            0,
            "Manual Installation Commands",
            "Read and copy PowerShell commands. Nothing runs automatically.",
            self.show_manual_commands
        )

        self.continue_button = self.add_action(
            actions,
            1,
            1,
            "Install Manually Later",
            "Continue without changing your system.",
            self.continue_to_next
        )

    # ========================================================
    # NEW: MANUAL INSTALLATION INSTRUCTIONS
    # ========================================================

    def manual_instructions(self):
        """
        Create readable instructions based on
        the latest WSL checker result.

        No commands are executed here.
        """

        if self.current_status:
            state = self.current_status.state
            details = self.current_status.details or ""
        else:
            state = "UNKNOWN"
            details = ""

        vmp_missing = bool(
            re.search(
                r"VirtualMachinePlatform:\s*"
                r"(DISABLED|ABSENT|NOT_FOUND)",
                details,
                flags=re.IGNORECASE
            )
        )

        lines = [
            "AUTOMATION PLATFORM - MANUAL WSL 2 & UBUNTU SETUP",
            "=" * 53,
            "",
            f"Detected status: {state}",
            "",
            "IMPORTANT:",
            "- Commands below are for Windows PowerShell.",
            "- Open PowerShell as Administrator for installation commands.",
            "- Run ONE command at a time and wait for completion.",
            "- Restart Windows if requested, then continue.",
            "- This window NEVER executes any command.",
            "",
            ]

        if state == "READY":
            lines.extend([
                "WSL 2 and Ubuntu are already detected as installed.",
                "",
            ])

        if vmp_missing:
            lines.extend([
                "STEP A - ENABLE VIRTUAL MACHINE PLATFORM (ADMIN)",
                "",
                "dism.exe /Online /Enable-Feature "
                "/FeatureName:VirtualMachinePlatform "
                "/All /NoRestart",
                "",
                "Restart Windows before continuing.",
                "",
            ])

        if state == "MISSING":
            lines.extend([
                "STEP B - INSTALL WSL (ADMIN)",
                "",
                "wsl.exe --install --no-distribution",
                "",
                "Restart Windows if required.",
                "",
                "STEP C - SET WSL 2 AS DEFAULT",
                "",
                "wsl.exe --set-default-version 2",
                "",
                "STEP D - INSTALL UBUNTU",
                "",
                "wsl.exe --install -d Ubuntu --no-launch",
                "",
            ])

        elif state == "DEFAULT_WSL1":
            lines.extend([
                "STEP - SET WSL 2 AS DEFAULT",
                "",
                "wsl.exe --set-default-version 2",
                "",
                "STEP - INSTALL UBUNTU (IF MISSING)",
                "",
                "wsl.exe --install -d Ubuntu --no-launch",
                "",
            ])

        elif state == "DISTRO_MISSING":
            lines.extend([
                "STEP - INSTALL UBUNTU",
                "",
                "wsl.exe --install -d Ubuntu --no-launch",
                "",
            ])

        elif state == "DISTRO_WSL1":
            lines.extend([
                "STEP - CONVERT UBUNTU TO WSL 2",
                "",
                "Back up any important Ubuntu files first.",
                "",
                "wsl.exe --set-version Ubuntu 2",
                "",
            ])

        elif state in (
                "NEEDS_ATTENTION",
                "UNKNOWN",
                "RESTART_REQUIRED"
        ):
            lines.extend([
                "DIAGNOSTICS (READ-ONLY)",
                "",
                "wsl.exe --status",
                "",
                "If Windows requested a restart,",
                "restart before retrying.",
                "",
            ])

        lines.extend([
            "VERIFY INSTALLATION",
            "",
            "wsl.exe --status",
            "wsl.exe --version",
            "wsl.exe --list --verbose",
            "",
            "FIRST UBUNTU LAUNCH (OPTIONAL)",
            "",
            "wsl.exe -d Ubuntu",
            "",
            "On first launch, Ubuntu may ask you",
            "to create a Linux user.",
            "",
            "The --no-launch installer deliberately",
            "skips this first-launch step.",
            "",
            "After finishing, return to the Wizard",
            "and press Check Again.",
        ])

        return "\n".join(lines)

    # ========================================================
    # NEW: MANUAL COMMANDS WINDOW
    # ========================================================

    def show_manual_commands(self):
        window = tk.Toplevel(self)

        window.title(
            "WSL 2 & Ubuntu - Manual Installation Commands"
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
            font=("Segoe UI", 16, "bold")
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=18,
            pady=(17, 9)
        )

        content = scrolledtext.ScrolledText(
            window,
            font=("Consolas", 10),
            wrap="word",
            bg=COLORS["terminal"],
            fg=COLORS["text"],
            insertbackground="white",
            selectbackground="#334155",
            selectforeground="white",
            padx=15,
            pady=15,
            undo=False
        )

        content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18
        )

        manual = self.manual_instructions()

        content.insert(
            "1.0",
            manual
        )

        # Read-only, but text remains selectable.
        content.configure(
            state="disabled"
        )

        buttons = ttk.Frame(window)

        buttons.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=18,
            pady=14
        )

        def copy_selection():
            try:
                selected = content.get(
                    tk.SEL_FIRST,
                    tk.SEL_LAST
                )
            except tk.TclError:
                messagebox.showinfo(
                    "Copy",
                    "Select text with the mouse first.",
                    parent=window
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
            command=copy_selection
        ).pack(
            side="left",
            padx=(0, 8)
        )

        ttk.Button(
            buttons,
            text="Copy All",
            command=copy_all
        ).pack(side="left")

        ttk.Button(
            buttons,
            text="Close",
            command=window.destroy
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
                "timestamp"
            )

            normalized = line.strip().lower()

            if level:
                tag = level

            elif normalized.startswith((
                    "error:",
                    "failed:",
                    "final status: failed"
            )):
                tag = "error"

            elif normalized.startswith((
                    "warning:",
                    "final status: attention",
                    "final status: restart"
            )):
                tag = "warning"

            elif normalized.startswith((
                    "===",
                    "> "
            )):
                tag = "heading"

            elif normalized.startswith((
                    "success:",
                    "final status: ready"
            )):
                tag = "success"

            else:
                tag = None

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
    # UI EVENT QUEUE
    # ========================================================

    def process_events(self):
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                message, level = data
                self.append_log(message, level)

            elif kind == "check_result":
                self.show_result(data)

            elif kind == "check_error":
                self.show_error(data)

            elif kind == "install_result":
                self.installation_finished(data)

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
                self.continue_button
        ):
            button.configure(
                state=state
            )

        # Manual help stays available at all times.
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

    def check_wsl(self):
        if self.busy:
            return

        self.current_status = None
        self.clear_logs()

        self.set_busy(
            True,
            "Checking WSL 2 and Ubuntu..."
        )

        self.status_var.set(
            "Checking system requirements..."
        )

        self.message_var.set(
            "Checking Windows features, WSL 2 and Ubuntu."
        )

        self.append_log(
            "=== AUTOMATION PLATFORM SYSTEM CHECK ===",
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

    def _check_worker(self):
        try:
            self.log_from_worker(
                "=== WSL 2 & UBUNTU DIAGNOSTICS ===",
                "heading"
            )

            result = self.checker.check()

            self.log_from_worker(
                result.details
            )

            self.events.put(
                ("check_result", result)
            )

        except Exception as error:
            self.events.put(
                ("check_error", str(error))
            )

    def show_result(self, result):
        self.current_status = result

        self.set_busy(
            False,
            "System check completed"
        )

        labels = {
            "READY": "WSL 2 & Ubuntu Ready",
            "MISSING": "WSL 2 Requirements Missing",
            "DEFAULT_WSL1": "WSL 1 Is Default",
            "DISTRO_MISSING": "Ubuntu Not Installed",
            "DISTRO_WSL1": "Ubuntu Requires WSL 2",
            "RESTART_REQUIRED": "Windows Restart Required",
            "NEEDS_ATTENTION": "WSL Setup Requires Attention",
            "NOT_APPLICABLE": "WSL Not Required",
        }

        self.status_var.set(
            labels.get(
                result.state,
                result.state
            )
        )

        self.message_var.set(
            result.message
        )

        if result.state in (
                "READY",
                "NOT_APPLICABLE"
        ):
            self.append_log(
                "SUCCESS: WSL setup requirements satisfied.",
                "success"
            )

            self.append_log(
                "FINAL STATUS: READY",
                "success"
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
                "warning"
            )

            self.append_log(
                "FINAL STATUS: ATTENTION REQUIRED",
                "warning"
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
            "System check failed"
        )

        self.status_var.set(
            "WSL Check Failed"
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
    # CHOOSE NEXT REQUIRED INSTALLATION ACTION
    # ========================================================

    def get_installation_action(self):
        if self.system != "Windows":
            return None

        if self.current_status is None:
            return None

        status = self.current_status

        if status.state in (
                "READY",
                "NOT_APPLICABLE",
                "RESTART_REQUIRED"
        ):
            return None

        if re.search(
                r"VirtualMachinePlatform:\s*"
                r"(DISABLED|ABSENT|NOT_FOUND)",
                status.details or "",
                flags=re.IGNORECASE
        ):
            return "enable_vmp"

        actions_by_state = {
            "DEFAULT_WSL1": "set_wsl2",
            "DISTRO_MISSING": "install_ubuntu",
            "DISTRO_WSL1": "convert_ubuntu",
            "MISSING": "install_wsl",
        }

        return actions_by_state.get(
            status.state
        )

    # ========================================================
    # CONFIRM REAL INSTALLATION
    # ========================================================

    def confirm_installation(self):
        if self.busy:
            return

        action = self.get_installation_action()

        if action is None:
            messagebox.showinfo(
                "WSL Setup",
                "No supported automatic action is available.\n"
                "Review diagnostics and click Check Again.",
                parent=self
            )
            return

        info = ACTIONS[action]

        if info["elevated"]:
            elevated_text = (
                "Windows will display a UAC prompt."
            )
        else:
            elevated_text = (
                "No UAC prompt is normally required."
            )

        if action == "convert_ubuntu":
            extra = (
                "\n\nBack up important Ubuntu files "
                "before conversion."
            )
        else:
            extra = ""

        confirmed = messagebox.askyesno(
            "Confirm Real WSL Setup",
            "This is a REAL installation operation.\n\n"
            f"Action: {info['label']}\n\n"
            f"Command:\n{command_text(info['command'])}\n\n"
            f"{elevated_text}\n"
            "An internet connection may be required.\n"
            "Windows will not restart automatically."
            f"{extra}\n\n"
            "Continue?",
            parent=self
        )

        if confirmed:
            self.install_wsl(action)
        else:
            self.append_log(
                "WARNING: Setup cancelled by user.",
                "warning"
            )

    # ========================================================
    # START REAL INSTALLATION
    # ========================================================

    def install_wsl(self, action):
        if self.busy:
            return

        if action not in ACTIONS:
            return

        self.installing = True

        self.set_busy(
            True,
            "Running real WSL setup..."
        )

        self.status_var.set(
            ACTIONS[action]["label"] + "..."
        )

        self.message_var.set(
            "Please wait. Watch actual command output below."
        )

        self.append_log(
            "=== REAL WSL INSTALLATION STARTED ===",
            "heading"
        )

        self.append_log(
            "Action: " + ACTIONS[action]["label"]
        )

        threading.Thread(
            target=self._install_worker,
            args=(action,),
            daemon=True
        ).start()

    # ========================================================
    # READ LIVE ELEVATED LOGS
    # ========================================================

    def read_new_logs(self, path, position):
        if not path.exists():
            return position

        try:
            with path.open("rb") as file:
                file.seek(position)
                data = file.read()
                new_position = file.tell()

            if data:
                decoded = data.decode(
                    "utf-8",
                    errors="replace"
                )

                for line in decoded.splitlines():
                    if line.strip():
                        self.log_from_worker(line)

            return new_position

        except OSError:
            return position

    # ========================================================
    # ELEVATED INSTALLATION WITH UAC
    # ========================================================

    def run_elevated_action(self, action):
        with tempfile.TemporaryDirectory(
                prefix="automation_platform_wsl_"
        ) as folder_name:

            folder = Path(folder_name)

            log_path = folder / "output.log"
            result_path = folder / "result.json"

            # Pre-create files before elevation.
            log_path.write_text(
                "",
                encoding="utf-8"
            )

            result_path.write_text(
                "",
                encoding="utf-8"
            )

            self.log_from_worker(
                "Requesting Windows UAC automatically..."
            )

            launched, error = request_uac(
                action,
                folder
            )

            if not launched:
                return {
                    "exit_code": None,
                    "restart_required": False,
                    "error": error or "UAC cancelled.",
                }

            self.log_from_worker(
                "SUCCESS: Elevated helper launched.",
                "success"
            )

            position = 0
            started = time.monotonic()
            result = None

            while True:
                position = self.read_new_logs(
                    log_path,
                    position
                )

                try:
                    raw = result_path.read_text(
                        encoding="utf-8"
                    )

                    if raw.strip():
                        result = json.loads(raw)
                        break

                except (OSError, ValueError):
                    pass

                elapsed = (
                        time.monotonic() - started
                )

                if elapsed > MAX_COMMAND_SECONDS + 120:
                    result = {
                        "exit_code": None,
                        "restart_required": False,
                        "error": (
                            "Timed out waiting for elevated helper; "
                            "check the actual installation state."
                        ),
                    }
                    break

                time.sleep(0.25)

            self.read_new_logs(
                log_path,
                position
            )

            return result

    # ========================================================
    # STANDARD INSTALLATION
    # ========================================================

    def run_standard_action(self, action):
        command = ACTIONS[action]["command"]

        code, output = run_command_with_logs(
            command,
            self.log_from_worker
        )

        self.log_from_worker(
            f"COMMAND EXIT CODE: {code}"
        )

        return {
            "exit_code": code,
            "restart_required": (
                    code in (3010, 1641)
                    or output_requires_restart(output)
            ),
            "error": None,
        }

    # ========================================================
    # INSTALLATION WORKER
    # ========================================================

    def _install_worker(self, action):
        info = ACTIONS[action]

        try:
            if info["elevated"]:
                outcome = self.run_elevated_action(
                    action
                )
            else:
                outcome = self.run_standard_action(
                    action
                )

        except subprocess.TimeoutExpired:
            outcome = {
                "exit_code": None,
                "restart_required": False,
                "error": "Installation command timed out.",
            }

        except Exception as error:
            outcome = {
                "exit_code": None,
                "restart_required": False,
                "error": str(error),
            }

        code = outcome.get("exit_code")

        successful = (
                not outcome.get("error")
                and code in (0, 3010, 1641)
        )

        if successful and (
                outcome.get("restart_required")
                or info["restart_after_success"]
        ):
            try:
                mark_restart_required()
                outcome["restart_required"] = True

            except OSError as error:
                outcome["error"] = (
                        "Could not record restart requirement: "
                        + str(error)
                )

        try:
            self.log_from_worker(
                "=== POST-INSTALLATION CHECK ===",
                "heading"
            )

            status = self.checker.check()

            self.log_from_worker(
                f"Checker state: {status.state}"
            )

            self.log_from_worker(
                status.details
            )

        except Exception as error:
            status = None

            self.log_from_worker(
                "WARNING: Final check failed: "
                + str(error),
                "warning"
            )

        self.events.put((
            "install_result",
            (outcome, status)
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
            "Installation attempt finished"
        )

        self.append_log(
            "=== FINAL INSTALLATION RESULT ===",
            "heading"
        )

        error = outcome.get("error")
        code = outcome.get("exit_code")

        restart_required = outcome.get(
            "restart_required",
            False
        )

        if error or code not in (0, 3010, 1641):
            message = (
                    error
                    or f"Command exited with code {code}."
            )

            self.status_var.set(
                "WSL Installation Failed"
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

        elif restart_required:
            self.status_var.set(
                "Windows Restart Required"
            )

            self.message_var.set(
                "Restart Windows and reopen the Launcher to continue."
            )

            self.append_log(
                "WARNING: Restart required before the next phase.",
                "warning"
            )

            self.append_log(
                "FINAL STATUS: RESTART REQUIRED",
                "warning"
            )

            messagebox.showinfo(
                "Restart Windows",
                "The Windows setup command succeeded.\n\n"
                "Restart Windows manually, then reopen the Launcher.",
                parent=self
            )

        elif status and status.state == "READY":
            self.status_var.set(
                "WSL 2 & Ubuntu Ready"
            )

            self.message_var.set(
                "WSL 2 and Ubuntu verified successfully."
            )

            self.append_log(
                "SUCCESS: WSL 2 and Ubuntu are ready.",
                "success"
            )

            self.append_log(
                "FINAL STATUS: READY",
                "success"
            )

            self.continue_button.configure(
                text="Continue to Docker Setup"
            )

        else:
            if status:
                state = status.state
            else:
                state = "UNKNOWN"

            self.status_var.set(
                "Additional WSL Setup Required"
            )

            self.message_var.set(
                "This step succeeded. "
                "Click Check Again for the next step."
            )

            self.append_log(
                f"WARNING: Next WSL state: {state}",
                "warning"
            )

            self.append_log(
                "FINAL STATUS: NEXT STEP REQUIRED",
                "warning"
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
                and self.current_status.state
                in ("READY", "NOT_APPLICABLE")
        )

        if ready:
            messagebox.showinfo(
                "System Check Complete",
                "WSL requirements satisfied.\n\n"
                "Next: Docker Desktop setup.",
                parent=self
            )
        else:
            messagebox.showinfo(
                "Install Manually Later",
                "You may continue without WSL setup now.\n\n"
                "Automation Platform needs Docker requirements to start.",
                parent=self
            )



# ============================================================
# ENTRY POINT
# ============================================================

def main():

    if (
            len(sys.argv) == 4
            and sys.argv[1] == HELPER_FLAG
    ):
        return elevated_helper_main(
            sys.argv[2],
            sys.argv[3]
        )

    root = tk.Tk()

    root.title(
        "Automation Platform - WSL 2 & Ubuntu Setup"
    )

    root.geometry("900x790")
    root.minsize(740, 650)

    page = WslSetupPage(root)

    page.pack(
        fill="both",
        expand=True
    )

    root.mainloop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
