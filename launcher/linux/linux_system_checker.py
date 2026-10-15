
"""
AUTOMATION PLATFORM - LINUX SYSTEM CHECKER

READ ONLY - NEVER INSTALLS OR DELETES ANYTHING.

Linux equivalent of the Windows WslChecker.

States:
    NOT_APPLICABLE
    UNSUPPORTED_DISTRIBUTION
    UNSUPPORTED_ARCHITECTURE
    DOCKER_MISSING
    DAEMON_STOPPED
    PERMISSION_DENIED
    SESSION_REFRESH_REQUIRED
    COMPOSE_MISSING
    NEEDS_ATTENTION
    READY

READY means:
    - Running on Linux
    - Supported architecture
    - Ubuntu or Debian distribution
    - Docker CLI installed
    - Docker Engine accessible by the current user
    - Docker Compose v2 installed
    - No sudo required for Docker commands

The checker does not install packages, start services,
change group memberships, or request administrator rights.
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

SUPPORTED_DISTRIBUTIONS = frozenset({
    "ubuntu",
    "debian",
})

SUPPORTED_ARCHITECTURES = frozenset({
    "x86_64",
    "amd64",
    "aarch64",
    "arm64",
})

APP_DIR = (
        Path.home()
        / ".local"
        / "state"
        / "automation-platform-student"
)

# Reserved for future setup workflow integration.
# The checker does not create this file.
SESSION_MARKER = APP_DIR / "docker_session_pending.json"


# ============================================================
# STATUS DATA
# ============================================================

@dataclass(frozen=True)
class LinuxStatus:
    state: str
    message: str
    details: str

    distribution: str = ""
    distribution_id: str = ""
    distribution_version: str = ""
    architecture: str = ""

    docker_version: Optional[str] = None
    docker_server_version: Optional[str] = None
    compose_version: Optional[str] = None

    docker_installed: bool = False
    daemon_accessible: bool = False
    compose_installed: bool = False
    docker_permission_granted: bool = False


# ============================================================
# SYSTEM CHECKER
# ============================================================

class LinuxSystemChecker:

    # --------------------------------------------------------
    # SAFE READ-ONLY PROCESS EXECUTION
    # --------------------------------------------------------

    @staticmethod
    def run_process(command, timeout=15):
        """
        Execute a read-only command without a shell.

        Returns:
            (exit_code, stdout, stderr)

        Exit codes:
            127 = command not found
            124 = timeout
        """
        try:
            completed = subprocess.run(
                command,
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
            return 127, "", "Command not found."

        except subprocess.TimeoutExpired as error:
            def decode_partial(value):
                if value is None:
                    return ""
                if isinstance(value, bytes):
                    return value.decode(
                        "utf-8",
                        errors="replace"
                    ).strip()
                return str(value).strip()

            return (
                124,
                decode_partial(error.stdout),
                decode_partial(error.stderr)
                or "Command timed out.",
            )

        except OSError as error:
            return 1, "", str(error)

    @classmethod
    def run_command(cls, *arguments, timeout=15):
        return cls.run_process(
            list(arguments),
            timeout=timeout,
        )

    # --------------------------------------------------------
    # LINUX DISTRIBUTION DETECTION
    # --------------------------------------------------------

    @staticmethod
    def get_distribution():
        """
        Read /etc/os-release.

        No external commands or root privileges required.
        """
        info = {}

        for filename in (
                "/etc/os-release",
                "/usr/lib/os-release",
        ):
            path = Path(filename)

            if not path.is_file():
                continue

            try:
                content = path.read_text(
                    encoding="utf-8",
                )

                for line in content.splitlines():
                    line = line.strip()

                    if not line or line.startswith("#"):
                        continue

                    if "=" not in line:
                        continue

                    key, value = line.split("=", 1)

                    value = value.strip()

                    if (
                            len(value) >= 2
                            and value[0] == value[-1]
                            and value[0] in ("'", '"')
                    ):
                        value = value[1:-1]

                    info[key] = value

                break

            except (OSError, UnicodeError):
                continue

        return {
            "id": info.get(
                "ID",
                "unknown"
            ).lower(),
            "name": info.get(
                "PRETTY_NAME",
                "Unknown Linux"
            ),
            "version": info.get(
                "VERSION_ID",
                ""
            ),
            "id_like": info.get(
                "ID_LIKE",
                ""
            ).lower(),
        }

    @classmethod
    def check_distribution_support(cls):
        distribution = cls.get_distribution()

        distro_id = distribution["id"]

        supported = (
                distro_id in SUPPORTED_DISTRIBUTIONS
        )

        return {
            **distribution,
            "supported": supported,
            "reason": (
                "Supported Linux distribution."
                if supported
                else (
                    "This distribution is detected, "
                    "but automated setup is currently "
                    "supported only on Ubuntu and Debian."
                )
            ),
        }

    # --------------------------------------------------------
    # SYSTEM INFORMATION
    # --------------------------------------------------------

    @classmethod
    def get_system_info(cls):
        return {
            "os": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "distribution": cls.get_distribution(),
        }

    @staticmethod
    def check_architecture():
        architecture = platform.machine().lower()

        return {
            "architecture": architecture,
            "supported": (
                    architecture
                    in SUPPORTED_ARCHITECTURES
            ),
        }

    # --------------------------------------------------------
    # DOCKER CLI
    # --------------------------------------------------------

    @classmethod
    def check_docker_installed(cls):
        docker_path = shutil.which("docker")

        if docker_path is None:
            return {
                "installed": False,
                "path": None,
                "version": None,
                "error": "Docker CLI was not found.",
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
    # DOCKER SERVICE
    # --------------------------------------------------------

    @classmethod
    def check_docker_service(cls):
        """
        Informational service check.

        Docker may also use rootless mode or another
        Docker context. Therefore systemctl status
        alone does not determine overall readiness.
        """
        if shutil.which("systemctl") is None:
            return {
                "available": False,
                "active": None,
                "status": "systemctl unavailable",
            }

        code, output, error = cls.run_command(
            "systemctl",
            "is-active",
            "docker",
            timeout=10,
        )

        status = (
                output or error or "unknown"
        ).strip()

        return {
            "available": True,
            "active": (
                True
                if code == 0 and status == "active"
                else False
            ),
            "status": status,
        }

    # --------------------------------------------------------
    # DOCKER ENGINE / DAEMON
    # --------------------------------------------------------

    @classmethod
    def check_docker_daemon(cls):
        """
        Check Docker Engine access as the current user.

        A failed docker info does not automatically mean
        that the daemon is stopped: permissions, contexts,
        and connection errors can produce the same result.
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

        permission_phrases = (
            "permission denied",
            "access denied",
            "operation not permitted",
        )

        connection_phrases = (
            "cannot connect",
            "connection refused",
            "is the docker daemon running",
            "no such file or directory",
            "connection reset",
        )

        if any(
                phrase in lowered
                for phrase in permission_phrases
        ):
            error_type = "PERMISSION_DENIED"

        elif any(
                phrase in lowered
                for phrase in connection_phrases
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

        version = (
            output if code == 0 else None
        )

        # Detect Compose v2, not an unrelated command.
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
                version if valid_compose_v2 else None
            ),
            "error": (
                None
                if valid_compose_v2
                else error
                     or output
                     or "Docker Compose v2 not available."
            ),
        }

    # --------------------------------------------------------
    # DOCKER GROUP / SESSION PERMISSIONS
    # --------------------------------------------------------

    @staticmethod
    def check_docker_group():
        """
        Compare persistent docker-group membership with
        groups active in the current process.

        A newly-added group may require logging out and
        logging back in before Docker access works.
        """
        result = {
            "group_exists": False,
            "configured_member": False,
            "active_member": False,
            "session_refresh_needed": False,
            "error": None,
        }

        if platform.system() != "Linux":
            return result

        try:
            import grp
            import pwd

            user = pwd.getpwuid(
                os.getuid()
            ).pw_name

            primary_gid = os.getgid()

            docker_group = grp.getgrnam(
                "docker"
            )

            result["group_exists"] = True

            configured_member = (
                    user in docker_group.gr_mem
                    or primary_gid == docker_group.gr_gid
            )

            active_member = (
                    docker_group.gr_gid
                    in os.getgroups()
                    or primary_gid == docker_group.gr_gid
            )

            result["configured_member"] = (
                configured_member
            )

            result["active_member"] = (
                active_member
            )

            result["session_refresh_needed"] = (
                    configured_member
                    and not active_member
            )

        except KeyError:
            # Docker group is absent, or the current
            # user cannot be resolved.
            pass

        except (ImportError, OSError) as error:
            result["error"] = str(error)

        return result

    @classmethod
    def check_docker_permissions(cls):
        group = cls.check_docker_group()

        daemon = cls.check_docker_daemon()

        return {
            "docker_group_member": (
                group["active_member"]
            ),
            "configured_group_member": (
                group["configured_member"]
            ),
            "session_refresh_needed": (
                group["session_refresh_needed"]
            ),
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
        """
        Structured diagnostics.

        Also preserves the interface used by the
        initial LinuxPrerequisitesPage implementation.
        """
        system = cls.get_system_info()

        distribution_support = (
            cls.check_distribution_support()
        )

        architecture = cls.check_architecture()

        docker = cls.check_docker_installed()

        daemon = cls.check_docker_daemon()

        compose = cls.check_docker_compose()

        group = cls.check_docker_group()

        permissions = {
            "docker_group_member": group["active_member"],
            "configured_group_member": (
                group["configured_member"]
            ),
            "session_refresh_needed": (
                group["session_refresh_needed"]
            ),
            "can_use_docker_without_sudo": (
                daemon["accessible"]
            ),
            "error": daemon["error"],
            "error_type": daemon["error_type"],
        }

        service = cls.check_docker_service()

        return {
            "system": system,
            "distribution_support": (
                distribution_support
            ),
            "architecture": architecture,
            "docker": docker,
            "docker_service": service,
            "docker_daemon": daemon,
            "docker_compose": compose,
            "docker_group": group,
            "docker_permissions": permissions,
        }

    # --------------------------------------------------------
    # MAIN CHECK - SAME PHILOSOPHY AS WSL CHECKER
    # --------------------------------------------------------

    def check(self):

        if platform.system() != "Linux":
            return LinuxStatus(
                state="NOT_APPLICABLE",
                message=(
                    "Linux prerequisites are not "
                    "applicable on this operating system."
                ),
                details=(
                    f"Operating system: {platform.system()}"
                ),
            )

        report = self.check_all()

        system = report["system"]
        distribution = system["distribution"]

        distro_support = report[
            "distribution_support"
        ]

        architecture = report["architecture"]

        docker = report["docker"]
        service = report["docker_service"]
        daemon = report["docker_daemon"]
        compose = report["docker_compose"]
        group = report["docker_group"]
        permissions = report["docker_permissions"]

        # ----------------------------------------------------
        # DETAILED DIAGNOSTIC OUTPUT
        # ----------------------------------------------------

        details = (
            "LINUX SYSTEM:\n"
            f"Distribution: {distribution['name']}\n"
            f"Distribution ID: {distribution['id']}\n"
            f"Version: {distribution['version']}\n"
            f"ID_LIKE: {distribution['id_like']}\n"
            f"Kernel: {system['release']}\n"
            f"Architecture: {system['architecture']}\n"
            "\nDISTRIBUTION SUPPORT:\n"
            f"Supported: {distro_support['supported']}\n"
            f"Reason: {distro_support['reason']}\n"
            "\nDOCKER CLI:\n"
            f"Installed: {docker['installed']}\n"
            f"Path: {docker['path']}\n"
            f"Version: {docker['version']}\n"
            f"Error: {docker['error']}\n"
            "\nDOCKER SERVICE:\n"
            f"systemctl available: {service['available']}\n"
            f"Active: {service['active']}\n"
            f"Status: {service['status']}\n"
            "\nDOCKER ENGINE:\n"
            f"Accessible: {daemon['accessible']}\n"
            f"Server version: {daemon['server_version']}\n"
            f"Error type: {daemon['error_type']}\n"
            f"Error: {daemon['error']}\n"
            "\nDOCKER COMPOSE:\n"
            f"Installed: {compose['installed']}\n"
            f"Version: {compose['version']}\n"
            f"Error: {compose['error']}\n"
            "\nDOCKER GROUP:\n"
            f"Group exists: {group['group_exists']}\n"
            f"Configured member: {group['configured_member']}\n"
            f"Active member: {group['active_member']}\n"
            f"Session refresh needed: "
            f"{group['session_refresh_needed']}\n"
            "\nDOCKER PERMISSIONS:\n"
            f"Accessible without sudo: "
            f"{permissions['can_use_docker_without_sudo']}"
        )

        def make_result(state, message):
            return LinuxStatus(
                state=state,
                message=message,
                details=details,
                distribution=distribution["name"],
                distribution_id=distribution["id"],
                distribution_version=distribution["version"],
                architecture=system["architecture"],
                docker_version=docker["version"],
                docker_server_version=(
                    daemon["server_version"]
                ),
                compose_version=compose["version"],
                docker_installed=docker["installed"],
                daemon_accessible=daemon["accessible"],
                compose_installed=compose["installed"],
                docker_permission_granted=(
                    permissions[
                        "can_use_docker_without_sudo"
                    ]
                ),
            )

        # ----------------------------------------------------
        # DISTRIBUTION AND ARCHITECTURE
        # ----------------------------------------------------

        if distribution["id"] == "unknown":
            return make_result(
                "NEEDS_ATTENTION",
                "Could not identify the Linux distribution.",
            )

        if not architecture["supported"]:
            return make_result(
                "UNSUPPORTED_ARCHITECTURE",
                (
                    "The current CPU architecture is not "
                    "supported by this setup flow."
                ),
            )

        if not distro_support["supported"]:
            return make_result(
                "UNSUPPORTED_DISTRIBUTION",
                (
                    f"{distribution['name']} was detected, "
                    "but automated setup currently supports "
                    "Ubuntu and Debian."
                ),
            )

        # ----------------------------------------------------
        # DOCKER MISSING
        # ----------------------------------------------------

        if not docker["installed"]:
            return make_result(
                "DOCKER_MISSING",
                (
                    "Docker Engine or its command-line "
                    "client is not installed correctly."
                ),
            )

        # ----------------------------------------------------
        # DAEMON / PERMISSION DIAGNOSTICS
        # ----------------------------------------------------

        if not daemon["accessible"]:

            if (
                    daemon["error_type"] == "PERMISSION_DENIED"
                    and group["session_refresh_needed"]
            ):
                return make_result(
                    "SESSION_REFRESH_REQUIRED",
                    (
                        "Docker group membership was "
                        "configured, but is not active "
                        "in this session. Log out and "
                        "log back in."
                    ),
                )

            if daemon["error_type"] == "PERMISSION_DENIED":
                return make_result(
                    "PERMISSION_DENIED",
                    (
                        "The current user does not have "
                        "permission to access the configured "
                        "Docker daemon."
                    ),
                )

            if (
                    daemon["error_type"] == "CONNECTION_FAILED"
                    and service["active"] is False
                    and service["status"] in (
                    "inactive",
                    "failed",
                    "deactivating",
            )
            ):
                return make_result(
                    "DAEMON_STOPPED",
                    (
                        "The Docker service is stopped "
                        "or has failed to start."
                    ),
                )

            return make_result(
                "NEEDS_ATTENTION",
                (
                    "Docker Engine could not be reached. "
                    "Check the service, Docker context "
                    "and diagnostic details."
                ),
            )

        # ----------------------------------------------------
        # DOCKER COMPOSE V2 MISSING
        # ----------------------------------------------------

        if not compose["installed"]:
            return make_result(
                "COMPOSE_MISSING",
                (
                    "Docker Engine is accessible, "
                    "but Docker Compose v2 is missing "
                    "or cannot be verified."
                ),
            )

        # ----------------------------------------------------
        # READY
        # ----------------------------------------------------

        return make_result(
            "READY",
            (
                "Linux, Docker Engine and Docker "
                "Compose v2 are ready. Docker is "
                "accessible without sudo."
            ),
        )


# ============================================================
# STANDALONE TEST
# ============================================================

def main():
    status = LinuxSystemChecker().check()

    print(f"STATE: {status.state}")
    print(f"MESSAGE: {status.message}")

    print("\nSYSTEM:")
    print(f"Distribution: {status.distribution}")
    print(f"Architecture: {status.architecture}")

    print("\nDOCKER:")
    print(f"Installed: {status.docker_installed}")
    print(f"Version: {status.docker_version}")
    print(f"Server: {status.docker_server_version}")
    print(f"Compose: {status.compose_version}")
    print(f"Daemon accessible: {status.daemon_accessible}")

    print("\nDETAILS:")
    print(status.details)


if __name__ == "__main__":
    main()
