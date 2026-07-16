"""OpenSCAD executable, capability, and export helpers."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

from selflensbahtinov.models import OutputFormat


class OpenScadError(RuntimeError):
    pass


class UnsupportedFormatError(OpenScadError):
    pass


def command_for(openscad: str, scad_path: Path, output_path: Path) -> list[str]:
    return [openscad, "-o", str(output_path), str(scad_path)]


def output_path(base: Path, fmt: OutputFormat) -> Path:
    return base.with_suffix(".3mf" if fmt is OutputFormat.THREEMF else "." + fmt.value)


def _format_process_error(
    prefix: str, exc: subprocess.CalledProcessError
) -> OpenScadError:
    details = []
    if exc.stdout:
        details.append(f"stdout: {exc.stdout.strip()}")
    if exc.stderr:
        details.append(f"stderr: {exc.stderr.strip()}")
    suffix = " (" + "; ".join(details) + ")" if details else ""
    return OpenScadError(
        f"{prefix}: OpenSCAD exited with status {exc.returncode}{suffix}"
    )


def version_text(openscad: str) -> str:
    try:
        result = subprocess.run(
            [openscad, "--version"], check=True, capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise OpenScadError(
            f"Unable to run OpenSCAD '{openscad}': executable not found"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise _format_process_error(
            f"Unable to run OpenSCAD '{openscad}'", exc
        ) from exc
    return result.stdout.strip() or result.stderr.strip()


def supports_format(openscad: str, fmt: OutputFormat) -> bool:
    if fmt is OutputFormat.SCAD:
        return True
    txt = version_text(openscad)
    if fmt is OutputFormat.STL:
        return True
    m = re.search(r"(\d+)\.(\d+)", txt)
    return bool(m and (int(m.group(1)), int(m.group(2))) >= (2021, 1))


def export(openscad: str, scad: Path, out: Path, dry_run: bool = False) -> None:
    if dry_run:
        return
    try:
        subprocess.run(
            command_for(openscad, scad, out), check=True, capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise OpenScadError(
            f"Unable to export {out}: OpenSCAD executable '{openscad}' not found"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise _format_process_error(f"Unable to export {out}", exc) from exc
