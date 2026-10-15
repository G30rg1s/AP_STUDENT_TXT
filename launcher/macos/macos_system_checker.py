
"""
AUTOMATION PLATFORM - macOS SYSTEM CHECKER

READ ONLY - NEVER INSTALLS OR DELETES ANYTHING.

macOS equivalent of Windows WslChecker and
LinuxSystemChecker.

States:
    NOT_APPLICABLE
    UNSUPPORTED_ARCHITECTURE
    MACOS_VERSION_NEEDS_ATTENTION
    DOCKER_MISSING
    DOCKER_CLI_MISSING
    DOCKER_DESKTOP_STOPPED
    PERMISSION_DENIED
    REMOTE_DOCKER_CONTEXT
    COMPOSE_MISSING
    NEEDS_ATTENTION
    READY

READY means:
    - Running on macOS
    - Supported Intel or Apple Silicon architecture
    - macOS version passes the configured baseline
    - Docker Desktop application detected
    - Docker CLI available
    - Docker Engine reachable using a local connection
    - Docker Compose v2 available

The checker never:
    - Installs Docker
    - Starts Docker Desktop
    - Changes permissions
    - Modifies Docker contexts
    - Requests administrator privileges
"""

import json
import os
import platform
import re
import shutil
import subprocess

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

SUPPORTED_ARCHITECTURES = frozenset({
    "x86_64",
    "arm64",
    "aarch64",
})

# Project policy, not a guarantee of compatibility with
# every Docker Desktop release. Current Docker Desktop
# requirements must be checked during installation.
MINIMUM_MACOS_MAJOR = 13

APP_DIR = (
        Path.home()
        / "Library"
        / "Application Support"
        / "AutomationPlatformStudent"
)

# Reserved for future setup workflow integration.
# Read-only checker does not write this marker.
RESTART_MARKER = APP_DIR / "restart_pending.json"


# ============================================================
# STATUS DATA
# ============================================================

@dataclass(frozen=True)
class MacOSStatus:
    state: str
    message: str
    details: str

    macos_version: str = ""
    architecture: str = ""

    docker_desktop_path: Optional[str] = None
    docker_version: Optional[str] = None
    docker_server_version: Optional[str] = None
    compose_version: Optional[str] = None

    docker_desktop_installed: bool = False
    docker_installed: bool = False
    daemon_accessible: bool = False
    compose_installed: bool = False
    docker_permission_granted: bool = False

    docker_context: Optional[str] = None
    docker_endpoint: Optional[str] = None


# ============================================================
# macOS SYSTEM CHECKER
# ============================================================

class MacOSSystemChecker:

    # --------------------------------------------------------
    # SAFE READ-ONLY PROCESS EXECUTION
    # --------------------------------------------------------

    @staticmethod
    def run_process(command, timeout=15):
        """
        Execute a command without a shell.

        Returns:
            (exit_code, stdout, stderr)

        Exit codes:
            127 = command not found
            124 = command timeout
        """
        try:
            completed = subprocess.run(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )

            return (
                completed.returncode,
                completed.stdout.strip(),
                completed.stderr.strip(),
            )

        except FileNotFoundError:
            return (
                127,
                "",
                "Command not found.",
            )

        except subprocess.TimeoutExpired as error:

            def decode_partial(value):
                if value is None:
                    return ""

                if isinstance(value, bytes):
                    return value.decode(
                        "utf-8",
                        errors="replace",
                    ).strip()

                return str(value).strip()

            return (
                124,
                decode_partial(error.stdout),
                decode_partial(error.stderr)
                or "Command timed out.",
            )

        except OSError as error:
            return (
                1,
                "",
                str(error),
            )

    @classmethod
    def run_command(cls, *arguments, timeout=15):
        return cls.run_process(
            arguments,
            timeout=timeout,
        )

    # --------------------------------------------------------
    # macOS VERSION
    # --------------------------------------------------------

    @staticmethod
    def check_macos_version():
        version = platform.mac_ver()[0]

        try:
            major = int(version.split(".")[0])

        except (ValueError, IndexError):
            return {
                "version": version,
                "major": None,
                "supported": None,
                "error": "Cannot determine macOS version.",
            }

        return {
            "version": version,
            "major": major,
            "supported": (
                    major >= MINIMUM_MACOS_MAJOR
            ),
            "error": None,
        }

    # --------------------------------------------------------
    # CPU ARCHITECTURE
    # --------------------------------------------------------

    @staticmethod
    def check_architecture():
        architecture = (
            platform.machine().lower()
        )

        return {
            "architecture": architecture,
            "supported": (
                    architecture
                    in SUPPORTED_ARCHITECTURES
            ),
            "apple_silicon": (
                    architecture in (
                "arm64",
                "aarch64",
            )
            ),
            "intel": architecture == "x86_64",
        }

    # --------------------------------------------------------
    # SYSTEM INFORMATION
    # --------------------------------------------------------

    @classmethod
    def get_system_info(cls):
        return {
            "os": platform.system(),
            "release": platform.release(),
            "macos_version": (
                cls.check_macos_version()
            ),
            "architecture": (
                cls.check_architecture()
            ),
        }

    # --------------------------------------------------------
    # DOCKER DESKTOP INSTALLATION
    # --------------------------------------------------------

    @staticmethod
    def check_docker_desktop_installed():
        """
        Detect Docker Desktop in standard locations.

        Custom installation locations may require
        additional detection in the setup wizard.
        """
        candidates = (
            Path("/Applications/Docker.app"),
            (
                    Path.home()
                    / "Applications"
                    / "Docker.app"
            ),
        )

        for path in candidates:
            if (
                    path.is_dir()
                    and (
                    path
                    / "Contents"
                    / "Info.plist"
            ).is_file()
            ):
                return {
                    "installed": True,
                    "path": str(path),
                    "error": None,
                }

        return {
            "installed": False,
            "path": None,
            "error": (
                "Docker Desktop was not found "
                "in the standard Applications locations."
            ),
        }

    # --------------------------------------------------------
    # DOCKER CLI
    # --------------------------------------------------------

    @classmethod
    def check_docker_installed(cls):
        docker_path = shutil.which("docker")

        if not docker_path:
            return {
                "installed": False,
                "path": None,
                "version": None,
                "error": "Docker CLI was not found in PATH.",
            }

        code, output, error = cls.run_command(
            "docker",
            "--version",
            timeout=10,
        )

        return {
            "installed": code == 0,
            "path": docker_path,
            "version": (
                output if code == 0 else None
            ),
            "error": (
                None
                if code == 0
                else error or output
            ),
        }

    # --------------------------------------------------------
    # DOCKER CONTEXT
    # --------------------------------------------------------

    @classmethod
    def check_docker_context(cls):
        """
        Detect the effective Docker connection.

        DOCKER_CONTEXT overrides DOCKER_HOST.
        DOCKER_HOST may override the default context.

        Docker may be configured to access a remote
        engine. A remote engine must not be mistaken
        for a ready local Docker Desktop installation.
        """
        result = {
            "name": None,
            "endpoint": None,
            "remote": False,
            "verified": False,
            "error": None,
        }

        if shutil.which("docker") is None:
            result["error"] = "Docker CLI not found."
            return result

        env_context = os.environ.get(
            "DOCKER_CONTEXT",
            "",
        ).strip()

        env_host = os.environ.get(
            "DOCKER_HOST",
            "",
        ).strip()

        code, name, error = cls.run_command(
            "docker",
            "context",
            "show",
            timeout=10,
        )

        if code != 0:
            result["error"] = (
                    error or name
                    or "Could not determine Docker context."
            )
            return result

        result["name"] = name

        code, output, error = cls.run_command(
            "docker",
            "context",
            "inspect",
            name,
            timeout=10,
        )

        endpoint = None

        if code == 0:
            try:
                parsed = json.loads(output)

                if (
                        isinstance(parsed, list)
                        and parsed
                        and isinstance(parsed[0], dict)
                ):
                    endpoints = parsed[0].get(
                        "Endpoints",
                        {},
                    )

                    docker_endpoint = (
                        endpoints.get("docker", {})
                    )

                    endpoint = docker_endpoint.get(
                        "Host"
                    )

            except (ValueError, TypeError, AttributeError):
                pass

        if env_context:
            # Explicit Docker context wins over DOCKER_HOST.
            result["name"] = env_context

        elif env_host:
            # Docker host overrides the selected default
            # context in the absence of DOCKER_CONTEXT.
            endpoint = env_host

        result["endpoint"] = endpoint

        if endpoint:
            endpoint_lower = endpoint.lower()

            if endpoint_lower.startswith((
                    "ssh://",
                    "tcp://",
                    "http://",
                    "https://",
            )):
                result["remote"] = True
                result["verified"] = True

            elif endpoint_lower.startswith(
                    "unix://"
            ):
                result["remote"] = False
                result["verified"] = True

            else:
                result["error"] = (
                    "Unrecognized Docker endpoint."
                )

        else:
            result["error"] = (
                    error
                    or "Docker endpoint could not be verified."
            )

        return result

    # --------------------------------------------------------
    # DOCKER ENGINE ACCESS
    # --------------------------------------------------------

    @classmethod
    def check_docker_daemon(cls):
        """
        Read-only Docker Engine connection check.
        """
        if shutil.which("docker") is None:
            return {
                "running": False,
                "accessible": False,
                "server_version": None,
                "error": "Docker CLI is not installed.",
                "error_type": "DOCKER_MISSING",
            }

        code, output, error = cls.run_command(
            "docker",
            "info",
            "--format",
            "{{.ServerVersion}}",
            timeout=15,
        )

        if code == 0:
            return {
                "running": True,
                "accessible": True,
                "server_version": output,
                "error": None,
                "error_type": None,
            }

        combined = (
                error + "\n" + output
        ).strip()

        lowered = combined.casefold()

        if (
                "permission denied" in lowered
                or "operation not permitted" in lowered
                or "access denied" in lowered
        ):
            error_type = "PERMISSION_DENIED"

        elif any(
                phrase in lowered
                for phrase in (
                        "cannot connect",
                        "connection refused",
                        "is the docker daemon running",
                        "no such file or directory",
                        "connection reset",
                )
        ):
            error_type = "CONNECTION_FAILED"

        elif code == 124:
            error_type = "TIMEOUT"

        else:
            error_type = "UNKNOWN"

        return {
            "running": False,
            "accessible": False,
            "server_version": None,
            "error": combined or f"Exit code: {code}",
            "error_type": error_type,
        }

    # --------------------------------------------------------
    # DOCKER COMPOSE V2
    # --------------------------------------------------------

    @classmethod
    def check_docker_compose(cls):
        if shutil.which("docker") is None:
            return {
                "installed": False,
                "version": None,
                "error": "Docker CLI is not installed.",
            }

        code, output, error = cls.run_command(
            "docker",
            "compose",
            "version",
            timeout=10,
        )

        valid_compose_v2 = (
                code == 0
                and bool(
            re.search(
                r"\bv2\.\d+",
                output,
                flags=re.IGNORECASE,
            )
        )
        )

        return {
            "installed": valid_compose_v2,
            "version": (
                output if valid_compose_v2 else None
            ),
            "error": (
                None
                if valid_compose_v2
                else error or output
                     or "Docker Compose v2 not available."
            ),
        }

    # --------------------------------------------------------
    # DOCKER PERMISSIONS
    # --------------------------------------------------------

    @classmethod
    def check_docker_permissions(cls):
        """
        Unlike Linux, macOS Docker Desktop does not
        normally require membership of a docker group.

        Verify real access instead of Unix group membership.
        """
        daemon = cls.check_docker_daemon()

        return {
            "docker_group_member": False,
            "can_use_docker_without_sudo": (
                daemon["accessible"]
            ),
            "error": daemon["error"],
            "error_type": daemon["error_type"],
        }

    # --------------------------------------------------------
    # COMPLETE DIAGNOSTICS
    # --------------------------------------------------------

    @classmethod
    def check_all(cls):
        system = cls.get_system_info()

        desktop = (
            cls.check_docker_desktop_installed()
        )

        docker = cls.check_docker_installed()

        context = cls.check_docker_context()

        daemon = cls.check_docker_daemon()

        compose = cls.check_docker_compose()

        permissions = {
            "docker_group_member": False,
            "can_use_docker_without_sudo": (
                daemon["accessible"]
            ),
            "error": daemon["error"],
            "error_type": daemon["error_type"],
        }

        return {
            "system": system,
            "docker_desktop": desktop,
            "docker": docker,
            "docker_context": context,
            "docker_daemon": daemon,
            "docker_compose": compose,
            "docker_permissions": permissions,
        }

    # --------------------------------------------------------
    # MAIN CHECK
    # --------------------------------------------------------

    def check(self):

        if platform.system() != "Darwin":
            return MacOSStatus(
                state="NOT_APPLICABLE",
                message=(
                    "macOS prerequisites are not applicable "
                    "on this operating system."
                ),
                details=(
                    f"Operating system: {platform.system()}"
                ),
            )

        report = self.check_all()

        system = report["system"]
        version = system["macos_version"]
        architecture = system["architecture"]

        desktop = report["docker_desktop"]
        docker = report["docker"]
        context = report["docker_context"]
        daemon = report["docker_daemon"]
        compose = report["docker_compose"]
        permissions = report["docker_permissions"]

        details = (
            "macOS SYSTEM:\n"
            f"Version: {version['version']}\n"
            f"Architecture: {architecture['architecture']}\n"
            f"Apple Silicon: {architecture['apple_silicon']}\n"
            f"Intel: {architecture['intel']}\n"
            "\nDOCKER DESKTOP:\n"
            f"Installed: {desktop['installed']}\n"
            f"Path: {desktop['path']}\n"
            f"Error: {desktop['error']}\n"
            "\nDOCKER CLI:\n"
            f"Installed: {docker['installed']}\n"
            f"Path: {docker['path']}\n"
            f"Version: {docker['version']}\n"
            f"Error: {docker['error']}\n"
            "\nDOCKER CONTEXT:\n"
            f"Name: {context['name']}\n"
            f"Endpoint: {context['endpoint']}\n"
            f"Remote: {context['remote']}\n"
            f"Verified: {context['verified']}\n"
            f"Error: {context['error']}\n"
            "\nDOCKER ENGINE:\n"
            f"Accessible: {daemon['accessible']}\n"
            f"Server version: {daemon['server_version']}\n"
            f"Error type: {daemon['error_type']}\n"
            f"Error: {daemon['error']}\n"
            "\nDOCKER COMPOSE:\n"
            f"Installed: {compose['installed']}\n"
            f"Version: {compose['version']}\n"
            f"Error: {compose['error']}\n"
            "\nDOCKER PERMISSIONS:\n"
            f"Accessible without sudo: "
            f"{permissions['can_use_docker_without_sudo']}"
        )

        def make_result(state, message):
            return MacOSStatus(
                state=state,
                message=message,
                details=details,
                macos_version=version["version"],
                architecture=architecture["architecture"],
                docker_desktop_path=desktop["path"],
                docker_version=docker["version"],
                docker_server_version=daemon[
                    "server_version"
                ],
                compose_version=compose["version"],
                docker_desktop_installed=desktop[
                    "installed"
                ],
                docker_installed=docker["installed"],
                daemon_accessible=daemon["accessible"],
                compose_installed=compose["installed"],
                docker_permission_granted=permissions[
                    "can_use_docker_without_sudo"
                ],
                docker_context=context["name"],
                docker_endpoint=context["endpoint"],
            )

        # ----------------------------------------------------
        # SYSTEM REQUIREMENTS
        # ----------------------------------------------------

        if not architecture["supported"]:
            return make_result(
                "UNSUPPORTED_ARCHITECTURE",
                (
                    "The Mac architecture is not supported "
                    "by this setup flow."
                ),
            )

        if version["supported"] is not True:
            return make_result(
                "MACOS_VERSION_NEEDS_ATTENTION",
                (
                    "The macOS version needs verification "
                    "against Docker Desktop requirements."
                ),
            )

        # ----------------------------------------------------
        # DOCKER DESKTOP INSTALLATION
        # ----------------------------------------------------

        if not desktop["installed"]:
            return make_result(
                "DOCKER_MISSING",
                (
                    "Docker Desktop was not found "
                    "in the standard macOS application "
                    "locations."
                ),
            )

        # ----------------------------------------------------
        # DOCKER CLI
        # ----------------------------------------------------

        if not docker["installed"]:
            return make_result(
                "DOCKER_CLI_MISSING",
                (
                    "Docker Desktop is installed, "
                    "but the Docker CLI is missing "
                    "or cannot be executed."
                ),
            )

        # ----------------------------------------------------
        # LOCAL DOCKER CONTEXT
        # ----------------------------------------------------

        if context["remote"]:
            return make_result(
                "REMOTE_DOCKER_CONTEXT",
                (
                    "Docker is configured to use a remote "
                    "engine. Switch to the local Docker "
                    "Desktop context."
                ),
            )

        if not context["verified"]:
            return make_result(
                "NEEDS_ATTENTION",
                (
                    "The current Docker connection "
                    "could not be verified as local."
                ),
            )

        # ----------------------------------------------------
        # ENGINE ACCESS
        # ----------------------------------------------------

        if not daemon["accessible"]:

            if daemon["error_type"] == "PERMISSION_DENIED":
                return make_result(
                    "PERMISSION_DENIED",
                    (
                        "The current user cannot access "
                        "the configured Docker Engine."
                    ),
                )

            if daemon["error_type"] == "CONNECTION_FAILED":
                return make_result(
                    "DOCKER_DESKTOP_STOPPED",
                    (
                        "Docker Desktop is installed, "
                        "but its local Docker Engine "
                        "is not reachable. Docker Desktop "
                        "may still be starting."
                    ),
                )

            return make_result(
                "NEEDS_ATTENTION",
                (
                    "Docker Engine could not be verified. "
                    "Review the diagnostic details."
                ),
            )

        # ----------------------------------------------------
        # COMPOSE V2
        # ----------------------------------------------------

        if not compose["installed"]:
            return make_result(
                "COMPOSE_MISSING",
                (
                    "Docker Engine is accessible, "
                    "but Docker Compose v2 is missing "
                    "or could not be verified."
                ),
            )

        # ----------------------------------------------------
        # READY
        # ----------------------------------------------------

        return make_result(
            "READY",
            (
                "macOS, Docker Desktop, Docker Engine "
                "and Docker Compose v2 are ready."
            ),
        )


# ============================================================
# STANDALONE TEST
# ============================================================

def main():
    status = MacOSSystemChecker().check()

    print(f"STATE: {status.state}")
    print(f"MESSAGE: {status.message}")

    print("\nSYSTEM:")
    print(f"macOS: {status.macos_version}")
    print(f"Architecture: {status.architecture}")

    print("\nDOCKER:")
    print(
        "Desktop installed:",
        status.docker_desktop_installed,
    )
    print("Docker version:", status.docker_version)
    print("Engine version:", status.docker_server_version)
    print("Compose:", status.compose_version)
    print("Context:", status.docker_context)
    print("Endpoint:", status.docker_endpoint)

    print("\nDETAILS:")
    print(status.details)


if __name__ == "__main__":
    main()
