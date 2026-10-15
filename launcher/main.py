
"""
AUTOMATION PLATFORM - STUDENT MAIN LAUNCHER

Cross-platform entry point.

Automatically detects:
    Windows
    Linux
    macOS

Opens the appropriate setup wizard for each operating
system while keeping the Student Launcher common.

Windows:
    Step 1: Windows WSL Setup
    Step 2: Windows Docker Setup

Linux:
    Step 1: Linux Prerequisites
    Step 2: Linux Docker Setup

macOS:
    Step 1: macOS Prerequisites
    Step 2: macOS Docker Setup

Step 3 on all systems:
    Student Launcher

Supports Python development mode and PyInstaller
frozen executable mode.

Preserves the Windows WSL elevated helper.
"""

import importlib
import os
import platform
import subprocess
import sys
import tkinter as tk

from pathlib import Path
from tkinter import messagebox, ttk


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_NAME = "Automation Platform"

LAUNCHER_DIR = Path(__file__).resolve().parent
PROJECT_DIR = LAUNCHER_DIR.parent

BACKGROUND = "#F1F5F9"
TEXT = "#0F172A"
SECONDARY = "#64748B"
PRIMARY = "#1E3A8A"
ACCENT = "#2563EB"


# ============================================================
# OPERATING SYSTEM PAGE CONFIGURATION
# ============================================================

OS_PAGES = {
    "Windows": {
        "prerequisites": {
            "filename": "windows_wsl_setup_page.py",
            "module": "launcher.windows.windows_wsl_setup_page",
            "description": "WSL 2 & Ubuntu Setup Wizard",
            "folder": "windows",
        },
        "docker": {
            "filename": "windows_docker_setup_page.py",
            "module": "launcher.windows.windows_docker_setup_page",
            "description": "Docker Desktop Setup Wizard",
            "folder": "windows",
        },
    },

    "Linux": {
        "prerequisites": {
            "filename": "linux_prerequisites_page.py",
            "module": "launcher.linux.linux_prerequisites_page",
            "description": "Linux Prerequisites Setup Wizard",
            "folder": "linux",
        },
        "docker": {
            "filename": "linux_docker_setup_page.py",
            "module": "launcher.linux.linux_docker_setup_page",
            "description": "Linux Docker Setup Wizard",
            "folder": "linux",
        },
    },

    "Darwin": {
        "prerequisites": {
            "filename": "macos_prerequisites_page.py",
            "module": "launcher.macos.macos_prerequisites_page",
            "description": "macOS Prerequisites Setup Wizard",
            "folder": "macos",
        },
        "docker": {
            "filename": "macos_docker_setup_page.py",
            "module": "launcher.macos.macos_docker_setup_page",
            "description": "macOS Docker Setup Wizard",
            "folder": "macos",
        },
    },
}

COMMON_PAGES = {
    "launcher": {
        "filename": "student_launcher.py",
        "module": "launcher.student_launcher",
        "description": "Automation Platform Student Launcher",
        "folder": None,
    },
}


# ============================================================
# OPERATING SYSTEM DETECTION
# ============================================================

def detect_operating_system():
    system = platform.system()
    machine = platform.machine()

    if system == "Windows":
        name = "Windows"
        version = platform.version()

    elif system == "Darwin":
        name = "macOS"
        version = platform.mac_ver()[0] or platform.release()

    elif system == "Linux":
        name = "Linux"
        version = platform.release()

        try:
            distribution = platform.freedesktop_os_release()

            name = distribution.get(
                "PRETTY_NAME",
                "Linux",
            )

        except (AttributeError, OSError):
            pass

    else:
        name = system or "Unknown"
        version = platform.release()

    return {
        "system": system,
        "name": name,
        "version": version,
        "architecture": machine,
    }


def is_frozen():
    return bool(getattr(sys, "frozen", False))


# ============================================================
# RESOLVE PAGE FOR CURRENT OPERATING SYSTEM
# ============================================================

def resolve_page(page_name, system=None):
    if system is None:
        system = platform.system()

    if page_name == "wsl":
        # Preserve the original Windows page alias.
        if system != "Windows":
            return None

        page_name = "prerequisites"

    if page_name in COMMON_PAGES:
        return COMMON_PAGES[page_name]

    system_pages = OS_PAGES.get(system)

    if system_pages is None:
        return None

    return system_pages.get(page_name)


def page_script_path(page):
    folder = page.get("folder")

    if folder:
        return (
                LAUNCHER_DIR
                / folder
                / page["filename"]
        )

    return LAUNCHER_DIR / page["filename"]


# ============================================================
# RUN PAGE IN CURRENT PROCESS
# USED BY PYINSTALLER CHILD MODES
# ============================================================

def run_page(page_name):
    page = resolve_page(page_name)

    if page is None:
        raise RuntimeError(
            "This setup page is not available "
            "for the current operating system."
        )

    module = importlib.import_module(
        page["module"]
    )

    for function_name in ("main", "run", "launch"):
        function = getattr(
            module,
            function_name,
            None,
        )

        if callable(function):
            return function()

    raise RuntimeError(
        f"{page['module']} does not expose "
        "a main(), run() or launch() function."
    )


# ============================================================
# MAIN WINDOW
# ============================================================

class AutomationPlatformMain:

    def __init__(self, root):
        self.root = root

        self.root.title(
            "Automation Platform - Student Setup"
        )

        self.root.geometry("790x810")
        self.root.minsize(650, 720)
        self.root.configure(bg=BACKGROUND)

        self.os_info = detect_operating_system()
        self.system = self.os_info["system"]

        self.status_var = tk.StringVar(
            value="System detected. Ready to begin."
        )

        self.build_ui()

    # ========================================================
    # BUILD USER INTERFACE
    # ========================================================

    def build_ui(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        font_family = (
            "Segoe UI"
            if self.system == "Windows"
            else "Helvetica"
            if self.system == "Darwin"
            else "DejaVu Sans"
        )

        self.font_family = font_family

        style.configure(
            "Main.TButton",
            font=(font_family, 11, "bold"),
            padding=(14, 13),
        )

        container = tk.Frame(
            self.root,
            bg=BACKGROUND,
        )

        container.pack(
            fill="both",
            expand=True,
            padx=28,
            pady=24,
        )

        # APPLICATION TITLE

        tk.Label(
            container,
            text=APP_NAME,
            font=(font_family, 23, "bold"),
            bg=BACKGROUND,
            fg=PRIMARY,
        ).pack(anchor="w")

        tk.Label(
            container,
            text="Student Installation & Application Launcher",
            font=(font_family, 11),
            bg=BACKGROUND,
            fg=SECONDARY,
        ).pack(
            anchor="w",
            pady=(4, 16),
        )

        # OPERATING SYSTEM INFORMATION

        os_card = tk.Frame(
            container,
            bg="#E0F2FE",
            highlightbackground="#BAE6FD",
            highlightthickness=1,
        )

        os_card.pack(
            fill="x",
            pady=(0, 16),
        )

        os_body = tk.Frame(
            os_card,
            bg="#E0F2FE",
        )

        os_body.pack(
            fill="x",
            padx=16,
            pady=12,
        )

        tk.Label(
            os_body,
            text="DETECTED OPERATING SYSTEM",
            font=(font_family, 9, "bold"),
            bg="#E0F2FE",
            fg=PRIMARY,
        ).pack(anchor="w")

        os_description = (
            f"{self.os_info['name']} "
            f"{self.os_info['version']} "
            f"({self.os_info['architecture']})"
        )

        tk.Label(
            os_body,
            text=os_description,
            font=(font_family, 12, "bold"),
            bg="#E0F2FE",
            fg=TEXT,
            wraplength=680,
            justify="left",
        ).pack(
            anchor="w",
            pady=(5, 0),
        )

        # OPERATING SYSTEM SPECIFIC STEPS

        if self.system == "Windows":
            self.build_windows_steps(container)

        elif self.system == "Linux":
            self.build_linux_steps(container)

        elif self.system == "Darwin":
            self.build_macos_steps(container)

        else:
            self.build_unsupported_steps(container)

        # STATUS

        tk.Label(
            container,
            textvariable=self.status_var,
            bg=BACKGROUND,
            fg=ACCENT,
            font=(font_family, 10),
            wraplength=700,
            justify="left",
        ).pack(
            anchor="w",
            pady=(12, 0),
        )

        # FOOTER

        footer_text = (
            "Administrator permission is requested "
            "only when required by an installer."
        )

        tk.Label(
            container,
            text=footer_text,
            bg=BACKGROUND,
            fg=SECONDARY,
            font=(font_family, 9),
            wraplength=700,
            justify="left",
        ).pack(
            anchor="w",
            pady=(8, 0),
        )

    # ========================================================
    # WINDOWS STEPS
    # ========================================================

    def build_windows_steps(self, container):
        self.add_step(
            container,
            "STEP 1",
            "WSL 2 & Ubuntu",
            "Check or install WSL 2 and Ubuntu.",
            "Open WSL Setup Wizard",
            self.open_prerequisites,
        )

        self.add_step(
            container,
            "STEP 2",
            "Docker Desktop",
            "Install and verify Docker Engine and Compose.",
            "Open Docker Setup Wizard",
            self.open_docker,
        )

        self.add_launcher_step(container)

    # ========================================================
    # LINUX STEPS
    # ========================================================

    def build_linux_steps(self, container):
        self.add_step(
            container,
            "STEP 1",
            "Linux Prerequisites",
            "Check Linux system and Docker prerequisites.",
            "Open Linux Prerequisites Wizard",
            self.open_prerequisites,
        )

        self.add_step(
            container,
            "STEP 2",
            "Docker Engine & Compose",
            "Install and verify Docker Engine and Compose.",
            "Open Linux Docker Setup Wizard",
            self.open_docker,
        )

        self.add_launcher_step(container)

    # ========================================================
    # MACOS STEPS
    # ========================================================

    def build_macos_steps(self, container):
        self.add_step(
            container,
            "STEP 1",
            "macOS Prerequisites",
            "Check macOS and Docker prerequisites.",
            "Open macOS Prerequisites Wizard",
            self.open_prerequisites,
        )

        self.add_step(
            container,
            "STEP 2",
            "Docker Desktop for Mac",
            "Install and verify Docker Desktop and Compose.",
            "Open macOS Docker Setup Wizard",
            self.open_docker,
        )

        self.add_launcher_step(container)

    # ========================================================
    # UNSUPPORTED OS
    # ========================================================

    def build_unsupported_steps(self, container):
        self.add_step(
            container,
            "STEP 1",
            "Unsupported Operating System",
            "Automatic setup is not available.",
            "View System Information",
            self.show_unsupported_system,
        )

    # ========================================================
    # COMMON STEP 3
    # ========================================================

    def add_launcher_step(self, container):
        self.add_step(
            container,
            "STEP 3",
            "Automation Platform",
            "Start, stop and manage the application.",
            "Open Student Launcher",
            self.open_launcher,
        )

    # ========================================================
    # REUSABLE STEP CARD
    # ========================================================

    def add_step(
            self,
            parent,
            number,
            title,
            description,
            button_text,
            command,
    ):
        card = tk.Frame(
            parent,
            bg="white",
            highlightbackground="#DBE4F0",
            highlightthickness=1,
        )

        card.pack(
            fill="x",
            pady=(0, 12),
        )

        body = tk.Frame(
            card,
            bg="white",
        )

        body.pack(
            fill="x",
            padx=17,
            pady=14,
        )

        tk.Label(
            body,
            text=f"{number} - {title}",
            font=(self.font_family, 12, "bold"),
            bg="white",
            fg=TEXT,
        ).pack(anchor="w")

        tk.Label(
            body,
            text=description,
            font=(self.font_family, 10),
            bg="white",
            fg=SECONDARY,
            wraplength=670,
            justify="left",
        ).pack(
            anchor="w",
            pady=(4, 10),
        )

        ttk.Button(
            body,
            text=button_text,
            command=command,
            style="Main.TButton",
        ).pack(fill="x")

    # ========================================================
    # LAUNCH PAGE AS CHILD PROCESS
    # ========================================================

    def launch_page(self, page_name):
        page = resolve_page(
            page_name,
            self.system,
        )

        if page is None:
            messagebox.showwarning(
                "Unsupported Setup Page",
                "This page is not supported "
                "on the detected operating system.",
                parent=self.root,
            )
            return

        try:
            environment = os.environ.copy()

            working_directory = (
                Path(sys.executable).resolve().parent
                if is_frozen()
                else PROJECT_DIR
            )

            kwargs = {
                "cwd": str(working_directory),
                "env": environment,
            }

            if self.system == "Windows":
                kwargs["creationflags"] = getattr(
                    subprocess,
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                )

            if is_frozen():
                # The frozen executable dispatches the
                # current OS-specific page by argument.
                command = [
                    sys.executable,
                    f"--{page_name}",
                ]

            else:
                script_path = page_script_path(page)

                if not script_path.is_file():
                    raise FileNotFoundError(
                        f"Missing file:\n{script_path}"
                    )

                # Package execution preserves imports:
                #
                # from launcher.linux...
                # from launcher.macos...
                # from launcher.windows...
                command = [
                    sys.executable,
                    "-m",
                    page["module"],
                ]

            subprocess.Popen(
                command,
                **kwargs,
            )

            self.status_var.set(
                f"Opened: {page['description']}"
            )

        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Launch Failed",
                str(error),
                parent=self.root,
            )

            self.status_var.set(
                f"Error opening {page['description']}"
            )

    # ========================================================
    # PAGE ACTIONS
    # ========================================================

    def open_prerequisites(self):
        self.launch_page("prerequisites")

    def open_wsl(self):
        # Preserve original method if used externally.
        self.launch_page("wsl")

    def open_docker(self):
        self.launch_page("docker")

    def open_launcher(self):
        self.launch_page("launcher")

    # ========================================================
    # UNSUPPORTED SYSTEM
    # ========================================================

    def show_unsupported_system(self):
        messagebox.showwarning(
            "Unsupported Operating System",
            "Detected operating system:\n\n"
            f"{self.os_info['name']}\n\n"
            "Automatic setup is supported only for "
            "Windows, Linux and macOS.",
            parent=self.root,
        )


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

def main():
    # ========================================================
    # WINDOWS ELEVATED WSL HELPER
    # KEEP EXISTING WINDOWS INSTALLATION WORKING
    # ========================================================

    if (
            len(sys.argv) == 4
            and sys.argv[1] == "--wsl-elevated-helper"
    ):
        if platform.system() != "Windows":
            raise RuntimeError(
                "WSL elevated helper is available "
                "only on Windows."
            )

        from launcher.windows.windows_wsl_setup_page import (
            elevated_helper_main,
        )

        return elevated_helper_main(
            sys.argv[2],
            sys.argv[3],
        )

    # ========================================================
    # FROZEN EXECUTABLE PAGE MODES
    # ========================================================

    page_arguments = {
        "--prerequisites": "prerequisites",
        "--wsl": "wsl",
        "--docker": "docker",
        "--launcher": "launcher",
    }

    if len(sys.argv) > 1:
        argument = sys.argv[1].lower()

        if argument in page_arguments:
            page_name = page_arguments[argument]

            result = run_page(page_name)

            return result if isinstance(result, int) else 0

    # ========================================================
    # MAIN MENU
    # ========================================================

    root = tk.Tk()

    AutomationPlatformMain(root)

    root.mainloop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
