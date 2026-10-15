
import ctypes
import json
import locale
import os
import platform
import re
import subprocess
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ============================================================
# AUTOMATION PLATFORM - WSL CHECKER
# ============================================================
#
# READ ONLY - NEVER INSTALLS OR DELETES ANYTHING.
#
# States:
#   MISSING
#   DEFAULT_WSL1
#   DISTRO_MISSING
#   DISTRO_WSL1
#   RESTART_REQUIRED
#   NEEDS_ATTENTION
#   READY
#   NOT_APPLICABLE
#
# For this project's setup flow, READY means:
#   - VirtualMachinePlatform enabled
#   - WSL installed
#   - Default WSL version 2
#   - Ubuntu installed as WSL 2
#   - No restart pending from our installer
#
# ============================================================


APP_DIR = (
        Path(os.environ.get("LOCALAPPDATA") or Path.home())
        / "AutomationPlatformStudent"
)

RESTART_MARKER = APP_DIR / "wsl_restart_pending.json"


# ============================================================
# RESTART TRACKING
# ============================================================

def windows_boot_timestamp():
    if platform.system() != "Windows":
        return None

    try:
        kernel = ctypes.windll.kernel32

        kernel.GetTickCount64.restype = ctypes.c_ulonglong

        uptime_ms = kernel.GetTickCount64()

        return time.time() - uptime_ms / 1000.0

    except (AttributeError, OSError):
        return None


def restart_is_pending():
    """
    Return True if our installer requested a restart
    and Windows has not rebooted since then.
    """

    if not RESTART_MARKER.is_file():
        return False

    try:
        data = json.loads(
            RESTART_MARKER.read_text(encoding="utf-8")
        )

        marked_at = float(data["timestamp"])
        boot_time = windows_boot_timestamp()

        if boot_time is None:
            return True

        return marked_at > boot_time + 2

    except (OSError, ValueError, KeyError, TypeError):
        return True


# ============================================================
# STATUS DATA
# ============================================================

@dataclass(frozen=True)
class WslStatus:
    state: str
    message: str
    details: str
    default_version: Optional[int] = None
    distributions: tuple = ()


# ============================================================
# WSL CHECKER
# ============================================================

class WslChecker:

    # --------------------------------------------------------
    # WINDOWS OUTPUT DECODING
    # --------------------------------------------------------

    @staticmethod
    def decode_output(data):
        if not data:
            return ""

        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return data.decode(
                "utf-16",
                errors="replace"
            ).strip()

        if b"\x00" in data:
            return data.decode(
                "utf-16-le",
                errors="replace"
            ).strip()

        try:
            return data.decode("utf-8").strip()

        except UnicodeError:
            encoding = locale.getpreferredencoding(False)

            return data.decode(
                encoding,
                errors="replace"
            ).strip()

    # --------------------------------------------------------
    # SAFE READ-ONLY PROCESS EXECUTION
    # --------------------------------------------------------

    @classmethod
    def run_process(cls, command, timeout=15):
        flags = getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0
        )

        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                creationflags=flags
            )

            return (
                completed.returncode,
                cls.decode_output(completed.stdout),
                cls.decode_output(completed.stderr)
            )

        except FileNotFoundError:
            return 127, "", "Command not found."

        except subprocess.TimeoutExpired as error:
            partial_stdout = cls.decode_output(error.stdout)
            partial_stderr = cls.decode_output(error.stderr)

            return (
                124,
                partial_stdout,
                partial_stderr or "Command timed out."
            )

        except OSError as error:
            return 1, "", str(error)

    @classmethod
    def run_command(cls, *arguments, timeout=15):
        return cls.run_process(
            ["wsl.exe", *arguments],
            timeout=timeout
        )

    # --------------------------------------------------------
    # WINDOWS OPTIONAL FEATURE
    # --------------------------------------------------------

    @classmethod
    def check_windows_feature(cls, feature_name):
        safe_name = feature_name.replace("'", "''")

        script = (
            "$ErrorActionPreference='Stop';"
            "$feature=Get-CimInstance "
            "-ClassName Win32_OptionalFeature "
            f"-Filter \"Name='{safe_name}'\";"
            "if($null -eq $feature){"
            "'NOT_FOUND'"
            "}else{"
            "switch([int]$feature.InstallState){"
            "1{'ENABLED'}"
            "2{'DISABLED'}"
            "3{'ABSENT'}"
            "default{'UNKNOWN'}"
            "}"
            "}"
        )

        code, output, error = cls.run_process(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script
            ],
            timeout=20
        )

        if code != 0:
            return "UNKNOWN", error or output

        state = output.strip().upper()

        if state in (
                "ENABLED",
                "DISABLED",
                "ABSENT",
                "NOT_FOUND"
        ):
            return state, output

        return "UNKNOWN", output

    # --------------------------------------------------------
    # DETECT MISSING WSL PACKAGE
    # --------------------------------------------------------

    @staticmethod
    def wsl_not_installed(output):
        text = output.casefold()

        phrases = (
            "windows subsystem for linux is not installed",
            "windows subsystem for linux has not been installed",
            "the windows subsystem for linux is not installed",
            "υποσύστημα των windows για linux δεν είναι εγκατεστημένο",
            "υποσυστημα των windows για linux δεν ειναι εγκατεστημενο",
            "wsl is not installed"
        )

        return any(phrase in text for phrase in phrases)

    # --------------------------------------------------------
    # DETECT NO INSTALLED DISTRIBUTIONS
    # --------------------------------------------------------

    @staticmethod
    def no_distributions_installed(output):
        text = output.casefold()

        phrases = (
            "no installed distributions",
            "there are no installed distributions",
            "has no installed distributions",
            "δεν υπάρχουν εγκατεστημένες διανομές",
            "δεν υπαρχουν εγκατεστημενες διανομες"
        )

        return any(phrase in text for phrase in phrases)

    # --------------------------------------------------------
    # PARSE INSTALLED DISTRIBUTIONS
    # --------------------------------------------------------

    @staticmethod
    def parse_distributions(output):
        distributions = []

        for raw_line in output.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if (
                    "NAME" in line.upper()
                    and "VERSION" in line.upper()
            ):
                continue

            # Typical output:
            #
            # NAME        STATE      VERSION
            # Ubuntu      Stopped    2
            #
            # Allow localized state names.

            match = re.match(
                r"^\*?\s*(.+?)\s{2,}(.+?)\s+([12])\s*$",
                line
            )

            if not match:
                continue

            distributions.append({
                "name": match.group(1).strip(),
                "state": match.group(2).strip(),
                "version": int(match.group(3))
            })

        return tuple(distributions)

    # --------------------------------------------------------
    # MAIN WSL CHECK
    # --------------------------------------------------------

    def check(self):

        # WSL is Windows-only.

        if platform.system() != "Windows":
            return WslStatus(
                state="NOT_APPLICABLE",
                message=(
                    "WSL is not required on "
                    "this operating system."
                ),
                details=(
                    f"Operating system: {platform.system()}"
                )
            )

        # ----------------------------------------------------
        # CHECK WINDOWS FEATURES
        # ----------------------------------------------------

        vmp, vmp_diagnostics = self.check_windows_feature(
            "VirtualMachinePlatform"
        )

        legacy, legacy_diagnostics = (
            self.check_windows_feature(
                "Microsoft-Windows-Subsystem-Linux"
            )
        )

        details = (
            "WINDOWS OPTIONAL FEATURES:\n"
            f"VirtualMachinePlatform: {vmp}\n"
            "Microsoft-Windows-Subsystem-Linux: "
            f"{legacy}"
        )

        if vmp == "UNKNOWN":
            details += (
                    "\n\nVMP DIAGNOSTIC:\n"
                    + str(vmp_diagnostics)
            )

        if legacy == "UNKNOWN":
            details += (
                    "\n\nLEGACY FEATURE DIAGNOSTIC:\n"
                    + str(legacy_diagnostics)
            )

        # Helper to preserve our existing WslStatus API.

        def make_result(
                state,
                message,
                default_version=None,
                distributions=()
        ):
            return WslStatus(
                state=state,
                message=message,
                details=details,
                default_version=default_version,
                distributions=distributions
            )

        # ----------------------------------------------------
        # VIRTUAL MACHINE PLATFORM MISSING
        # ----------------------------------------------------

        if vmp in ("DISABLED", "ABSENT", "NOT_FOUND"):
            return make_result(
                "MISSING",
                (
                    "Virtual Machine Platform is disabled "
                    "or unavailable. WSL 2 is not ready."
                )
            )

        if vmp != "ENABLED":
            return make_result(
                "NEEDS_ATTENTION",
                "Could not verify Virtual Machine Platform."
            )

        # ----------------------------------------------------
        # CHECK WSL STATUS FIRST
        # ----------------------------------------------------

        status_code, status_out, status_err = (
            self.run_command("--status", timeout=12)
        )

        status_text = (
                status_out + "\n" + status_err
        ).strip()

        details += (
                "\n\nWSL STATUS:\n"
                + (
                        status_text
                        or f"Exit code: {status_code}"
                )
        )

        # Critical: WSL executable can exist even when
        # the actual WSL package has been uninstalled.
        #
        # Do not run --version or --list if --status
        # explicitly reports WSL is missing.

        if (
                status_code == 127
                or self.wsl_not_installed(status_text)
        ):
            return make_result(
                "MISSING",
                (
                    "Windows Subsystem for Linux "
                    "is not installed."
                )
            )

        if status_code == 124:
            return make_result(
                "NEEDS_ATTENTION",
                "WSL status command timed out."
            )

        # ----------------------------------------------------
        # RESTART TRACKING
        # ----------------------------------------------------

        if restart_is_pending():
            return make_result(
                "RESTART_REQUIRED",
                (
                    "Restart Windows before continuing "
                    "the WSL setup."
                )
            )

        if status_code != 0:
            return make_result(
                "NEEDS_ATTENTION",
                "WSL status could not be verified."
            )

        # ----------------------------------------------------
        # DEFAULT VERSION
        # ----------------------------------------------------

        match = re.search(
            r"Default Version:\s*([12])",
            status_out,
            flags=re.IGNORECASE
        )

        default_version = (
            int(match.group(1))
            if match
            else None
        )

        if default_version == 1:
            return make_result(
                "DEFAULT_WSL1",
                (
                    "WSL 1 is the default version. "
                    "Configure WSL 2."
                ),
                default_version=1
            )

        if default_version != 2:
            return make_result(
                "NEEDS_ATTENTION",
                (
                    "Could not confirm the default "
                    "WSL version."
                )
            )

        # ----------------------------------------------------
        # VERIFY WSL PACKAGE
        # ----------------------------------------------------

        version_code, version_out, version_err = (
            self.run_command("--version", timeout=15)
        )

        details += (
                "\n\nWSL VERSION:\n"
                + (
                        version_out
                        or version_err
                        or f"Exit code: {version_code}"
                )
        )

        if version_code != 0:
            return make_result(
                "NEEDS_ATTENTION",
                "Could not verify WSL package version.",
                default_version=2
            )

        # ----------------------------------------------------
        # VERIFY DISTRIBUTIONS
        # ----------------------------------------------------

        list_code, list_out, list_err = (
            self.run_command(
                "--list",
                "--verbose",
                timeout=15
            )
        )

        combined_list_output = (
                list_out + "\n" + list_err
        )

        details += (
                "\n\nWSL DISTRIBUTIONS:\n"
                + (
                        combined_list_output.strip()
                        or f"Exit code: {list_code}"
                )
        )

        # ====================================================
        # FIX: NO DISTRIBUTIONS
        #
        # Some versions of WSL return a nonzero exit code
        # when no distributions are installed.
        #
        # This is DISTRO_MISSING, not NEEDS_ATTENTION.
        # ====================================================

        if self.no_distributions_installed(
                combined_list_output
        ):
            return make_result(
                "DISTRO_MISSING",
                (
                    "WSL 2 is installed, but Ubuntu "
                    "is missing. Install Ubuntu."
                ),
                default_version=2
            )

        if list_code != 0:
            return make_result(
                "NEEDS_ATTENTION",
                (
                    "Could not list installed "
                    "WSL distributions."
                ),
                default_version=2
            )

        distributions = self.parse_distributions(
            list_out
        )

        # ----------------------------------------------------
        # CHECK UBUNTU
        # ----------------------------------------------------

        ubuntu = next(
            (
                distro
                for distro in distributions
                if distro["name"].casefold() == "ubuntu"
            ),
            None
        )

        if ubuntu is None:
            return make_result(
                "DISTRO_MISSING",
                (
                    "WSL 2 is installed, but Ubuntu "
                    "is missing. Install Ubuntu."
                ),
                default_version=2,
                distributions=distributions
            )

        if ubuntu["version"] == 1:
            return make_result(
                "DISTRO_WSL1",
                (
                    "Ubuntu is using WSL 1. "
                    "Convert Ubuntu to WSL 2."
                ),
                default_version=2,
                distributions=distributions
            )

        # ----------------------------------------------------
        # READY
        # ----------------------------------------------------

        return make_result(
            "READY",
            (
                "WSL 2 and Ubuntu are installed "
                "and configured."
            ),
            default_version=2,
            distributions=distributions
        )


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    status = WslChecker().check()

    print(f"STATE: {status.state}")
    print(f"MESSAGE: {status.message}")
    print(f"DEFAULT VERSION: {status.default_version}")

    print("\nDISTRIBUTIONS:")

    if status.distributions:
        for distro in status.distributions:
            print(
                f"  {distro['name']} - "
                f"{distro['state']} - "
                f"WSL {distro['version']}"
            )
    else:
        print("  None detected")

    print("\nDETAILS:")
    print(status.details)
