"""`compile`: render plain d2 class diagrams in StarUML style.

Diagrams live in diagrams/; renders go to out/ (same sub-folders).

    uv run compile                            # every diagrams/**/*.d2 -> out/**/*.svg
    uv run compile class_diagram              # just diagrams/class_diagram.d2
    uv run compile --png                      # PNGs instead (needs rsvg-convert)
    uv run compile class_diagram -o x.svg     # explicit output path (one diagram)
    uv run compile class_diagram -w           # live preview in the browser
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .convert import convert
from .fonts import DEFAULT_FONT, FontError, available_fonts, find_font, fontconfig_env
from .postprocess import postprocess_file

DEFAULT_OUT_DIR = "out"
DEFAULT_DIAGRAMS_DIR = "diagrams"


class RenderError(Exception):
    """A diagram could not be rendered (the others still are)."""


def d2_command(args: argparse.Namespace) -> list[str]:
    """d2 with the font trick: d2 0.9 measures all text with the "bold" font, so
    the Regular font goes in the bold slot (exact measuring) and the Bold font in
    the italic slot (class names use italic to come out bold)."""
    font = args.font
    cmd = ["d2", "--pad", "20"]
    if args.layout:
        cmd += ["--layout", args.layout]
    cmd += [
        "--font-regular", str(font.regular),
        "--font-bold", str(font.regular),
        "--font-italic", str(font.bold),
    ]  # fmt: skip
    return cmd


def fail(message: str) -> None:
    print(f"compile: {message}", file=sys.stderr)
    sys.exit(1)


def write_converted(source: Path, target: Path) -> str:
    """Convert `source` into `target`; returns the converted text."""
    text, warnings = convert(source.read_text(encoding="utf-8"))
    for warning in warnings:
        print(f"compile: warning: {warning}", file=sys.stderr)
    target.write_text(text, encoding="utf-8")
    return text


def run_d2(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        errors = "\n".join(line for line in result.stderr.splitlines() if not line.startswith("info:"))
        raise RenderError(f"d2 failed:\n{errors}")


def styled_path(source: Path) -> Path:
    """The generated d2 sits next to the input so relative imports/icons still resolve."""
    return source.with_name(f".{source.stem}.staruml.d2")


def output_path(args: argparse.Namespace, source: Path) -> Path:
    if args.output:
        return Path(args.output)
    relative = source.resolve().relative_to(Path(args.diagrams_dir).resolve())
    return Path(args.out_dir) / relative.with_suffix(".png" if args.png else ".svg")


def validate(source: Path) -> None:
    """Check the user's own file first, so errors point at its lines (not the generated file's)."""
    result = subprocess.run(["d2", "validate", str(source)], capture_output=True, text=True)
    if result.returncode != 0:
        lines = [line for line in result.stderr.splitlines() if line.strip() and not line.startswith("info:")]
        message = "\n".join(re.sub(r"^err: (?:\S+validateCmd: )?", f"{source}:", line) for line in lines)
        raise RenderError(f"invalid d2:\n{message}")


def render(args: argparse.Namespace, source: Path) -> None:
    validate(source)
    output = output_path(args, source)
    output.parent.mkdir(parents=True, exist_ok=True)
    styled = styled_path(source)
    try:
        write_converted(source, styled)
        if output.suffix.lower() == ".png":
            render_png(args, styled, output)
        else:
            run_d2(d2_command(args) + [str(styled), str(output)])
            postprocess_file(output)
        if args.emit_d2:
            shutil.copyfile(styled, args.emit_d2)
    finally:
        styled.unlink(missing_ok=True)
    print(f"wrote {output}", flush=True)


def render_png(args: argparse.Namespace, styled: Path, output: Path) -> None:
    if not shutil.which("rsvg-convert"):
        raise RenderError("PNG output needs rsvg-convert (brew install librsvg)")
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "out.svg"
        run_d2(d2_command(args) + [str(styled), str(svg)])
        postprocess_file(svg, png_fonts=True)
        env = fontconfig_env(args.font, Path(tmp))
        subprocess.run(["rsvg-convert", "--zoom", "2", str(svg), "-o", str(output)], check=True, env=env)


def watch(args: argparse.Namespace, source: Path) -> None:
    """Re-convert on every save; `d2 -w` re-renders and reloads the browser.
    (The preview skips the SVG touch-ups: filled arrowheads, blue shadow.)"""
    def stop(*_: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)  # clean up the temp file when killed, too
    styled = styled_path(source)
    last = write_converted(source, styled)
    mtime = source.stat().st_mtime
    preview_dir = tempfile.TemporaryDirectory()  # d2 -w writes an SVG; keep it out of the way
    preview = Path(preview_dir.name) / "preview.svg"
    d2 = subprocess.Popen(d2_command(args) + ["--watch", str(styled), str(preview)])
    try:
        while d2.poll() is None:
            time.sleep(0.4)
            current = source.stat().st_mtime
            if current == mtime:
                continue
            mtime = current
            try:
                text, warnings = convert(source.read_text(encoding="utf-8"))
            except Exception as exc:  # keep watching while the file is half-edited
                print(f"compile: could not convert: {exc}", file=sys.stderr)
                continue
            for warning in warnings:
                print(f"compile: warning: {warning}", file=sys.stderr)
            if text != last:
                styled.write_text(text, encoding="utf-8")
                last = text
    except KeyboardInterrupt:
        pass
    finally:
        if d2.poll() is None:
            d2.terminate()
            d2.wait()
        preview_dir.cleanup()
        styled.unlink(missing_ok=True)


def find_diagrams(diagrams_dir: Path, names: list[str]) -> list[Path]:
    """All diagrams in `diagrams_dir`, or the named ones (name, name.d2 or a path)."""
    if not diagrams_dir.is_dir():
        fail(f"no {diagrams_dir}/ folder here: run compile from the project folder (or use --diagrams-dir)")
    if not names:
        found = sorted(
            p for p in diagrams_dir.rglob("*.d2")
            if not any(part.startswith(".") for part in p.relative_to(diagrams_dir).parts)
        )
        if not found:
            fail(f"no .d2 files in {diagrams_dir}/")
        return found

    root = diagrams_dir.resolve()
    sources = []
    for name in names:
        candidates = [Path(name), diagrams_dir / name, diagrams_dir / f"{name}.d2"]
        source = next((c for c in candidates if c.is_file()), None)
        if source is None:
            fail(f"no diagram {name!r} (looked in {diagrams_dir}/)")
        if not source.resolve().is_relative_to(root):
            fail(f"{source} is outside {diagrams_dir}/: all diagrams have to be in there")
        sources.append(source)
    return sources


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="compile",
        description="Render plain d2 class diagrams in StarUML style. "
        "Without arguments, renders every diagram in diagrams/ to out/.",
    )
    parser.add_argument(
        "diagrams",
        nargs="*",
        metavar="DIAGRAM",
        help="diagrams to render: a name (class_diagram), file name or path inside diagrams/ (default: all)",
    )
    parser.add_argument("-o", "--output", help="output .svg or .png path (one diagram only)")
    parser.add_argument(
        "--diagrams-dir",
        default=os.environ.get("STARUML_DIAGRAMS_DIR", DEFAULT_DIAGRAMS_DIR),
        help=f"folder with the diagrams (default: {DEFAULT_DIAGRAMS_DIR}/)",
    )
    parser.add_argument(
        "--out-dir",
        default=os.environ.get("STARUML_OUT_DIR", DEFAULT_OUT_DIR),
        help=f"folder for the renders, mirroring the diagrams folder (default: {DEFAULT_OUT_DIR}/)",
    )
    parser.add_argument("--png", action="store_true", help="write PNGs instead of SVGs")
    parser.add_argument("--layout", choices=["dagre", "elk"], help="override the layout engine")
    parser.add_argument("--emit-d2", metavar="FILE", help="also save the generated d2 here (one diagram only)")
    parser.add_argument("-w", "--watch", action="store_true", help="live preview in the browser (one diagram only)")
    parser.add_argument(
        "--font",
        default=os.environ.get("STARUML_FONT", DEFAULT_FONT),
        help=f"a font from fonts/ ({', '.join(available_fonts()) or 'none found'}), "
        f"or a folder with Name-Regular.ttf and Name-Bold.ttf (default: {DEFAULT_FONT})",
    )
    args = parser.parse_args(argv)

    if not shutil.which("d2"):
        fail("d2 not found (brew install d2)")
    try:
        args.font = find_font(args.font)
    except FontError as exc:
        fail(str(exc))

    sources = find_diagrams(Path(args.diagrams_dir), args.diagrams)
    if len(sources) > 1:
        for option, used in (("-o", args.output), ("--emit-d2", args.emit_d2), ("-w", args.watch)):
            if used:
                fail(f"{option} works with one diagram; name it, e.g. compile {sources[0].stem} {option}")

    if args.watch:
        watch(args, sources[0])
        return

    failed = []
    for source in sources:
        try:
            render(args, source)
        except RenderError as exc:
            print(f"compile: {source}: {exc}", file=sys.stderr)
            failed.append(source)
    if failed:
        fail(f"{len(failed)} of {len(sources)} diagram(s) failed")


if __name__ == "__main__":
    main()
