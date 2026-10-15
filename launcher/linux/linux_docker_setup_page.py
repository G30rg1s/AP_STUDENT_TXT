
"""
AUTOMATION PLATFORM - LINUX DOCKER SETUP

Linux equivalent of the Windows DockerSetupPage.

Features:
- Automatic diagnostics on launch
- Thread-safe event queue
- Timestamped terminal logs
- Docker Engine and Compose v2 checks
- LinuxSystemChecker integration
- User-confirmed installation on Ubuntu/Debian
- Graphical administrator authorization via pkexec
- Installation timeout and error handling
- Official installation documentation
- Continue now / install manually later

Automatic installation uses distribution packages when
available. It never silently adds repositories, modifies
Docker permissions, or changes group membership.
"""

import os
import platform
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
import webbrowser

from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

from launcher.linux.linux_system_checker import (
    LinuxSystemChecker,
)


LINUX_INSTALL_URL = (
    "https://docs.docker.com/engine/install/"
)

UBUNTU_INSTALL_URL = (
    "https://docs.docker.com/engine/install/ubuntu/"
)

DEBIAN_INSTALL_URL = (
    "https://docs.docker.com/engine/install/debian/"
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


class LinuxDockerSetupPage(ttk.Frame):

    def __init__(self, parent, on_continue=None):
        super().__init__(parent, padding=22)

        self.on_continue = on_continue
        self.events = queue.Queue()

        self.busy = False
        self.checked = False
        self.ready = False

        self.system = platform.system()
        self.system_name = self.detect_system()

        self.status = None

        self.status_var = tk.StringVar(
            value="System check pending"
        )

        self.message_var = tk.StringVar(
            value="Preparing Linux Docker diagnostics."
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

        self.after(100, self.process_events)
        self.after(250, self.check_docker)

    @staticmethod
    def detect_system():
        if platform.system() != "Linux":
            return platform.system()

        distro = LinuxSystemChecker.get_distribution()

        return distro["name"]

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
            pady=(0, 12),
        )

        ttk.Label(
            header,
            text="Automation Platform",
            font=("DejaVu Sans", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header,
            text="Student Setup Wizard - Linux Docker",
        ).pack(anchor="w")

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
            text=self.system_name,
            font=("DejaVu Sans", 11, "bold"),
        ).pack(anchor="w")

        status_frame = ttk.LabelFrame(
            self,
            text="Step 2 - Docker Requirements",
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
        ).pack(anchor="w", pady=(7, 0))

        progress_frame = ttk.Frame(self)
        progress_frame.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )
        progress_frame.columnconfigure(0, weight=1)

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
            text="System Diagnostics & Installation Logs",
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

        for name in (
                "success",
                "warning",
                "error",
                "heading",
                "timestamp",
        ):
            self.details_text.tag_configure(
                name,
                foreground=COLORS[name],
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
            "Recheck Linux Docker requirements.",
            self.check_docker,
        )

        self.install_button = self.add_action(
            actions,
            0,
            1,
            "Download & Install Docker Automatically",
            self.install_description,
            self.confirm_installation,
        )

        self.download_button = self.add_action(
            actions,
            1,
            0,
            "Docker Installation Page",
            "Open official Docker installation instructions.",
            self.open_download_page,
        )

        self.continue_button = self.add_action(
            actions,
            1,
            1,
            "Install Manually Later",
            self.continue_description,
            self.continue_to_next,
        )

        self.install_button.configure(state="disabled")

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
            **options,
        ).pack(anchor="w", pady=(5, 0))

        return button

    # ========================================================
    # TERMINAL LOGS
    # ========================================================

    def append_log(self, message, level=None):
        self.details_text.configure(state="normal")

        for line in str(message).splitlines() or [""]:
            stamp = datetime.now().strftime("%H:%M:%S")

            self.details_text.insert(
                tk.END,
                f"[{stamp}] ",
                "timestamp",
            )

            low = line.strip().lower()
            tag = level

            if tag is None:
                if low.startswith((
                        "error:",
                        "failed:",
                        "final status: failed",
                )):
                    tag = "error"

                elif low.startswith((
                        "warning:",
                        "final status: attention",
                )):
                    tag = "warning"

                elif low.startswith((
                        "success:",
                        "final status: ready",
                )):
                    tag = "success"

                elif low.startswith(("===", "> ")):
                    tag = "heading"

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
        self.events.put(("log", (message, level)))

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
                self.after(100, self.process_events)
        except tk.TclError:
            pass

    # ========================================================
    # BUSY STATE
    # ========================================================

    def set_busy(self, busy, label="Operation finished"):
        self.busy = busy

        state = "disabled" if busy else "normal"

        for button in (
                self.check_button,
                self.install_button,
                self.download_button,
                self.continue_button,
        ):
            button.configure(state=state)

        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

        self.progress_var.set(label)

    # ========================================================
    # PROCESS HELPERS
    # ========================================================

    @staticmethod
    def run_command(command, timeout=20):
        return LinuxSystemChecker.run_process(
            command,
            timeout=timeout,
        )

    @staticmethod
    def package_available(name):
        """
        Check whether APT knows the requested package.

        This does not install anything or refresh
        repositories.
        """
        if shutil.which("apt-cache") is None:
            return False

        code, output, _ = LinuxSystemChecker.run_command(
            "apt-cache",
            "show",
            name,
            timeout=10,
        )

        return (
                code == 0
                and bool(
            re.search(
                r"^Package:\s*" + re.escape(name) + r"\s*$",
                output,
                flags=re.MULTILINE,
                )
        )
        )

    @classmethod
    def automatic_install_command(cls, status):
        """
        Return a command only for a supported system
        with packages available in configured repositories.

        No shell=True and no downloaded shell scripts.
        """
        if platform.system() != "Linux":
            return None

        distro = LinuxSystemChecker.get_distribution()

        if distro["id"] not in ("ubuntu", "debian"):
            return None

        if not shutil.which("apt-get"):
            return None

        if not shutil.which("pkexec"):
            return None

        if status.state not in (
                "DOCKER_MISSING",
                "COMPOSE_MISSING",
        ):
            return None

        if not status.docker_installed:
            if not cls.package_available("docker.io"):
                return None

            packages = ["docker.io"]
        else:
            packages = []

        if not status.compose_installed:
            if cls.package_available("docker-compose-v2"):
                packages.append("docker-compose-v2")
            elif cls.package_available("docker-compose-plugin"):
                packages.append("docker-compose-plugin")
            else:
                return None

        if not packages:
            return None

        return [
            shutil.which("pkexec"),
            "apt-get",
            "install",
            "-y",
            *packages,
        ]

    # ========================================================
    # DOCKER CHECK
    # ========================================================

    def check_docker(self):
        if self.busy:
            return

        self.checked = False
        self.ready = False
        self.status = None

        self.clear_logs()

        self.set_busy(
            True,
            "Checking Docker requirements...",
        )

        self.status_var.set(
            "Checking Docker requirements..."
        )

        self.message_var.set(
            "Please wait while Docker is checked."
        )

        self.append_log(
            "=== AUTOMATION PLATFORM LINUX DOCKER CHECK ===",
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
            status = LinuxSystemChecker().check()

            self.log_from_worker(
                "=== LINUX PREREQUISITES ===",
                "heading",
            )

            self.log_from_worker(
                "STATE: " + status.state
            )

            self.log_from_worker(
                "MESSAGE: " + status.message
            )

            self.log_from_worker(
                "=== SYSTEM DIAGNOSTICS ===",
                "heading",
            )

            self.log_from_worker(status.details)

            self.events.put((
                "check_result",
                status,
            ))

        except Exception as error:
            self.events.put((
                "check_error",
                str(error),
            ))

    # ========================================================
    # DISPLAY RESULT
    # ========================================================

    def show_result(self, status):
        self.checked = True
        self.status = status

        self.ready = status.state == "READY"

        self.set_busy(
            False,
            "System check completed",
        )

        titles = {
            "READY": "Docker Ready",
            "DOCKER_MISSING": "Docker Is Not Installed",
            "DAEMON_STOPPED": "Docker Service Is Stopped",
            "PERMISSION_DENIED": "Docker Permission Required",
            "SESSION_REFRESH_REQUIRED": (
                "Session Refresh Required"
            ),
            "COMPOSE_MISSING": (
                "Docker Compose Is Unavailable"
            ),
            "UNSUPPORTED_DISTRIBUTION": (
                "Linux Distribution Not Supported"
            ),
            "UNSUPPORTED_ARCHITECTURE": (
                "Architecture Not Supported"
            ),
            "NOT_APPLICABLE": (
                "Linux Required"
            ),
        }

        self.status_var.set(
            titles.get(
                status.state,
                "Docker Requires Attention",
            )
        )

        self.message_var.set(status.message)

        self.append_log(
            (
                "FINAL STATUS: READY"
                if self.ready
                else "FINAL STATUS: ATTENTION"
            ),
            "success" if self.ready else "warning",
        )

        command = self.automatic_install_command(status)

        self.install_button.configure(
            state=(
                "normal"
                if command is not None
                else "disabled"
            )
        )

        if command:
            self.install_description.set(
                "Install available distribution packages "
                "using APT with administrator confirmation."
            )
        elif self.ready:
            self.install_description.set(
                "Docker is already ready."
            )
        else:
            self.install_description.set(
                "Automatic installation is unavailable "
                "for this state or package configuration. "
                "Use official instructions."
            )

        self.continue_button.configure(
            text=(
                "Continue"
                if self.ready
                else "Install Manually Later"
            )
        )

        self.continue_description.set(
            "Continue to the Automation Platform Launcher."
            if self.ready
            else (
                "You may continue, but Automation Platform "
                "cannot start until Docker Engine and "
                "Docker Compose are working."
            )
        )

    def show_error(self, message):
        self.checked = False
        self.ready = False
        self.status = None

        self.set_busy(
            False,
            "System check failed",
        )

        self.status_var.set(
            "Docker Check Failed"
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
    # OFFICIAL INSTALLATION PAGE
    # ========================================================

    def open_download_page(self):
        distro = LinuxSystemChecker.get_distribution()

        url = {
            "ubuntu": UBUNTU_INSTALL_URL,
            "debian": DEBIAN_INSTALL_URL,
        }.get(
            distro["id"],
            LINUX_INSTALL_URL,
        )

        self.append_log(
            "Opening official Docker installation page.",
            "heading",
        )

        self.append_log(url)

        webbrowser.open(url)

    # ========================================================
    # INSTALLATION CONFIRMATION
    # ========================================================

    def confirm_installation(self):
        if self.busy:
            return

        if not self.checked or self.status is None:
            messagebox.showwarning(
                "Check Required",
                "Click Check Again first.",
                parent=self,
            )
            return

        if self.ready:
            messagebox.showinfo(
                "Docker Ready",
                "Docker requirements are already satisfied.",
                parent=self,
            )
            return

        command = self.automatic_install_command(
            self.status
        )

        if command is None:
            messagebox.showinfo(
                "Manual Installation",
                "Automatic installation is not available "
                "for the current system state.\n\n"
                "Use the official Docker installation page.",
                parent=self,
            )
            return

        display_command = " ".join(command)

        confirmed = messagebox.askyesno(
            "Confirm Docker Installation",
            f"Detected OS: {self.system_name}\n\n"
            f"Real command:\n{display_command}\n\n"
            "This installs packages from configured "
            "APT repositories.\n"
            "Administrator authorization will be requested.\n"
            "Docker service configuration and user permissions "
            "may require additional steps.\n"
            "No automatic reboot will be requested.\n\n"
            "Continue?",
            parent=self,
        )

        if not confirmed:
            self.append_log(
                "WARNING: Installation cancelled by user.",
                "warning",
            )
            return

        self.set_busy(
            True,
            "Installing Docker. Watch the logs...",
        )

        self.status_var.set("Installing Docker...")
        self.message_var.set(
            "Installation running. Please wait."
        )

        self.append_log(
            "=== DOCKER INSTALLATION STARTED ===",
            "heading",
        )

        self.append_log(
            "> " + display_command,
            "heading",
            )

        threading.Thread(
            target=self._install_worker,
            args=(command,),
            daemon=True,
        ).start()

    # ========================================================
    # INSTALLATION WORKER
    # ========================================================

    def _install_worker(self, command):
        process = None
        timer = None
        timed_out = threading.Event()

        try:
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

            def stop_on_timeout():
                if process.poll() is None:
                    timed_out.set()
                    try:
                        process.kill()
                    except OSError:
                        pass

            timer = threading.Timer(
                1800,
                stop_on_timeout,
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
                    "error",
                )

            self.events.put((
                "install_result",
                code,
            ))

        except Exception as error:
            self.log_from_worker(
                "ERROR: " + str(error),
                "error",
                )

            self.events.put((
                "install_result",
                1,
            ))

        finally:
            if timer:
                timer.cancel()

            if process and process.stdout:
                process.stdout.close()

    # ========================================================
    # INSTALLATION FINISHED
    # ========================================================

    def installation_finished(self, code):
        self.set_busy(
            False,
            "Installation attempt finished",
        )

        self.append_log(
            "=== FINAL INSTALLATION RESULT ===",
            "heading",
        )

        if code == 0:
            self.status_var.set(
                "Installation Command Completed"
            )

            self.message_var.set(
                "Installation command completed. "
                "Click Check Again to verify Docker Engine, "
                "Compose and user permissions."
            )

            self.append_log(
                "SUCCESS: Installation command completed.",
                "success",
            )

            self.append_log(
                "FINAL STATUS: VERIFICATION REQUIRED",
                "warning",
            )

            messagebox.showinfo(
                "Docker Installation",
                "Installation command completed.\n\n"
                "Click Check Again to verify Docker.\n"
                "You may need to start the Docker service "
                "or configure user permissions manually.",
                parent=self,
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
                "error",
            )

            self.append_log(
                "FINAL STATUS: FAILED",
                "error",
            )

        self.checked = False
        self.ready = False
        self.status = None

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
                parent=self,
            )

        else:
            messagebox.showinfo(
                "Install Manually Later",
                "You may continue now, but Automation "
                "Platform cannot start until Docker Engine "
                "and Docker Compose are working.",
                parent=self,
            )


# ============================================================
# STANDALONE ENTRY POINT
# ============================================================

def main():
    if platform.system() != "Linux":
        raise SystemExit(
            "Linux Docker Setup can only run on Linux."
        )

    root = tk.Tk()

    root.title(
        "Automation Platform - Linux Docker Setup"
    )

    root.geometry("880x780")
    root.minsize(740, 650)

    page = LinuxDockerSetupPage(root)
    page.pack(fill="both", expand=True)

    root.mainloop()


if __name__ == "__main__":
    main()
