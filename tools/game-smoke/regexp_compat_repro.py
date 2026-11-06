#!/usr/bin/env python3
"""Check legacy wide-hex regex compatibility through the real script runtime.

All patterns and strings are synthetic. Exercise all four compilation entry
points, retain existing Oniguruma syntax, and reject malformed expressions.
Linux without DISPLAY uses xvfb-run. --prepare-only writes a device fixture.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile


CASES = [
    ("constructor-ascii", r'''
var r = new RegExp("^[\\x0041-\\x005A]+$");
regexResult = r.test("AZ") && !r.test("az");'''),
    ("compile-bmp", r'''
var r = new RegExp(); r.compile("^\\x03A9+$");
regexResult = r.test("ΩΩ") && !r.test("A");'''),
    ("internal-cjk-range", r'''
var r = new RegExp(); r._compile("///^[\\x4E00-\\x9FFF]+$");
regexResult = r.test("中文") && !r.test("abc");'''),
    ("literal-hiragana", r'''
var r = /^\x3042+$/;
regexResult = r.test("ああ") && !r.test("い");'''),
    ("three-digit-hex", r'''
var r = new RegExp("^\\x100$"); regexResult = r.test("Ā");'''),
    ("leading-zero-hex", r'''
var r = new RegExp("^\\x00004E2D$"); regexResult = r.test("中");'''),
    ("legacy-supplementary", r'''
var r = new RegExp("^\\x1F642$"); regexResult = r.test("🙂") && !r.test("中");'''),
    ("captures", r'''
var r = new RegExp("^(\\x0041+)-(\\x4E2D+)$");
var m = r.exec("AA-中中");
regexResult = m.count == 3 && m[0] == "AA-中中" && m[1] == "AA" && m[2] == "中中";'''),
    ("ignore-case-flag", r'''
var r = new RegExp("^\\x0041+$", "i");
regexResult = r.test("aAa") && !r.test("B");'''),
    ("global-flag", r'''
var r = new RegExp("[\\x0041-\\x0042]", "g");
var first = r.exec("BA"); var second = r.exec("BA"); var third = r.exec("BA");
regexResult = first.count == 1 && first[0] == "B" && second.count == 1 && second[0] == "A" && third.count == 0;'''),
    ("internal-flags", r'''
var r = new RegExp(); r._compile("//ig/\\x0041");
regexResult = r.replace("a-A", "x") == "x-x";'''),
    ("native-brace-bmp", r'''
var r = new RegExp("^\\x{0041}\\x{4E2D}$"); regexResult = r.test("A中");'''),
    ("native-brace-supplementary", r'''
var r = new RegExp("^\\x{1F642}$"); regexResult = r.test("🙂");'''),
    ("native-utf16-byte-pair", r'''
var r = new RegExp("^\\x41\\x00$"); regexResult = r.test("A") && !r.test("B");'''),
    ("byte-pair-with-legacy", r'''
var r = new RegExp("^\\x41\\x00-\\x4E2D$"); regexResult = r.test("A-中");'''),
    ("escaped-backslash-native", r'''
var r = new RegExp("^\\\\x0041$"); regexResult = r.test("\\x0041") && !r.test("A");'''),
    ("escaped-backslash-with-legacy", r'''
var r = new RegExp("^\\\\x0041-\\x4E2D$"); regexResult = r.test("\\x0041-中");'''),
    ("native-quoted-region", r'''
var r = new RegExp("^\\Q.+[x]\\E$"); regexResult = r.test(".+[x]");'''),
    ("quoted-region-with-legacy", r'''
var r = new RegExp("^\\Q\\x0041\\E-\\x4E2D$"); regexResult = r.test("\\x0041-中");'''),
    ("native-quote-in-class", r'''
var r = new RegExp("^[\\Q]$"); regexResult = r.test("Q");'''),
    ("quote-in-class-with-legacy", r'''
var r = new RegExp("^[\\Q\\x4E2D]$"); regexResult = r.test("Q") && r.test("中");'''),
    ("comment-does-not-change-escape-state", r'''
var r = new RegExp("^(?#\\Q\\x0041[)\\x4E2D$");
regexResult = r.test("中") && !r.test("A");'''),
    ("initial-bracket-in-class", r'''
var r = new RegExp("^[]\\Q\\x4E2D]$");
regexResult = r.test("]") && r.test("Q") && r.test("中") && !r.test("A");'''),
    ("initial-bracket-in-negated-class", r'''
var r = new RegExp("^[^]\\Q\\x4E2D]$");
regexResult = r.test("文") && !r.test("]") && !r.test("Q") && !r.test("中");'''),
    ("native-inline-extended-mode", r'''
var r = new RegExp("(?x)^# [\n\\Q\\x0041\\E-\\x{4E2D}$");
regexResult = r.test("\\x0041-中");'''),
    ("legacy-inline-extended-rejected", r'''
var caught = false;
try { new RegExp("(?x)^# [\n\\Q\\x0041\\E-\\x4E2D$"); } catch (e) { caught = e.message != ""; }
regexResult = caught && (new RegExp("^ok$")).test("ok");'''),
    ("malformed-constructor", r'''
var caught = false; try { new RegExp("("); } catch (e) { caught = e.message != ""; }
regexResult = caught && (new RegExp("^ok$")).test("ok");'''),
    ("malformed-legacy-and-recovery", r'''
var r = new RegExp("^before$"); var caught = false;
try { r.compile("(\\x0041"); } catch (e) { caught = e.message != ""; }
r.compile("^after$"); regexResult = caught && r.test("after");'''),
    ("malformed-internal-and-recovery", r'''
var r = new RegExp(); var caught = false;
try { r._compile("///[\\x0041"); } catch (e) { caught = e.message != ""; }
r._compile("///^ok$"); regexResult = caught && r.test("ok");'''),
    ("out-of-range-hex-rejected", r'''
var caught = false; try { new RegExp("^\\x110000$"); } catch (e) { caught = e.message != ""; }
regexResult = caught && (new RegExp("^ok$")).test("ok");'''),
]

EXPECTED = ["REGEXP_COMPAT|BEGIN"] + ["REGEXP_COMPAT|PASS|" + name for name, _ in CASES] + ["REGEXP_COMPAT|END|0"]


def prepare(directory):
    fixture = directory / "fixture"
    fixture.mkdir(parents=True, exist_ok=False)
    script = [
        'var regexFailures = 0; var regexResult = false;',
        'function regexCheck(value, name) {',
        ' if (value) Debug.message("REGEXP_COMPAT|PASS|" + name);',
        ' else { regexFailures++; Debug.message("REGEXP_COMPAT|FAIL|" + name); }',
        '}',
        'Debug.message("REGEXP_COMPAT|BEGIN");',
    ]
    for name, body in CASES:
        script.extend([
            'try { regexResult = false;', body,
            ' regexCheck(regexResult, ' + json.dumps(name) + ');',
            '} catch (e) { regexCheck(false, ' + json.dumps(name) + ');',
            ' Debug.message("REGEXP_COMPAT|ERROR|" + (typeof e == "String" ? e : e.message)); }',
        ])
    script.extend([
        'Debug.message("REGEXP_COMPAT|END|" + regexFailures);',
        'System.exit(regexFailures ? 1 : 0);',
    ])
    startup = b"\xff\xfe" + ("\n".join(script) + "\n").encode("utf-16le")
    (fixture / "startup.tjs").write_bytes(startup)
    (directory / "regexp-fixture.json").write_text(json.dumps({
        "checks": [name for name, _ in CASES],
        "startup_sha256": hashlib.sha256(startup).hexdigest(),
    }, indent=2) + "\n")
    return fixture


def validate(output, exit_code, forced_stop):
    failures = []
    if exit_code != 0 or forced_stop:
        failures.append(f"Runtime exited with {exit_code}; forced_stop={forced_stop}")
    if "REGEXP_COMPAT|FAIL|" in output:
        failures.append("The synthetic script reported a failed assertion")
    for marker in EXPECTED:
        if output.count(marker) != 1:
            failures.append("Expected exactly one marker: " + marker)
    return failures


def run(engine, directory, timeout):
    fixture = prepare(directory)
    command = [str(engine), fixture.as_posix() + "/"]
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        xvfb = shutil.which("xvfb-run")
        if not xvfb:
            raise RuntimeError("Set DISPLAY or install xvfb-run for the real runtime")
        command = [xvfb, "-a", "-s", "-screen 0 1280x720x24", *command]
    env = os.environ.copy()
    env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    env.setdefault("ALSOFT_DRIVERS", "null")
    digest = hashlib.sha256()
    with engine.open("rb") as binary:
        for block in iter(lambda: binary.read(1024 * 1024), b""):
            digest.update(block)
    report = {"engine": str(engine), "engine_sha256": digest.hexdigest(),
              "command": command, "timeout_seconds": timeout, "forced_stop": False,
              "checks": len(CASES)}
    log_path = directory / "regexp-compat-runtime.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=engine.parent, env=env,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=(os.name == "posix"))
        try:
            report["exit_code"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            report["forced_stop"] = True
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait(timeout=5)
            report["exit_code"] = process.returncode
    output = log_path.read_text(encoding="utf-8", errors="replace")
    report["failures"] = validate(output, report["exit_code"], report["forced_stop"])
    report["passed"] = not report["failures"]
    (directory / "regexp-compat-report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["failures"]:
        print(output[-14000:], file=sys.stderr)
        for failure in report["failures"]:
            print(failure, file=sys.stderr)
        return 1
    print(f"{len(CASES)} runtime regular-expression compatibility checks passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.prepare_only:
        if args.output_dir is None:
            parser.error("--prepare-only requires --output-dir")
        print(prepare(args.output_dir.resolve()))
        return 0
    if args.engine is None:
        parser.error("--engine is required")
    engine = args.engine.resolve(strict=True)
    if args.output_dir is not None:
        parent = args.output_dir.resolve()
        parent.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="regexp-compat-", dir=parent))
        print(f"RegExp compatibility evidence: {directory}", flush=True)
        return run(engine, directory, args.timeout)
    with tempfile.TemporaryDirectory(prefix="krkr2-regexp-compat-") as temporary:
        return run(engine, Path(temporary), args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
