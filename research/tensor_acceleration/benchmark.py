#!/usr/bin/env python3
"""Paired CPU/Edge-TPU TFLite microbenchmark; NOT a face-detection accuracy test.

Dependencies on the Raspberry Pi: numpy, tflite_runtime, pycoral and a working
Coral runtime/device. There is deliberately no CPU fallback for the TPU arm.
See PROTOCOL.md before interpreting numbers from this program.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence


@dataclass(frozen=True)
class Stages:
    set_ns: int
    invoke_ns: int
    get_ns: int
    total_ns: int


def _shape(detail: Mapping[str, Any]) -> tuple[int, ...]:
    return tuple(int(dim) for dim in detail["shape"])


def validate_pair(cpu: Any, tpu: Any) -> tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
    """Fail closed if CPU and TPU interpreters do not have matching tensor I/O."""
    cpu_inputs, tpu_inputs = cpu.get_input_details(), tpu.get_input_details()
    if len(cpu_inputs) != 1 or len(tpu_inputs) != 1:
        raise ValueError("Benchmark supports exactly one input tensor per model")
    c_input, t_input = cpu_inputs[0], tpu_inputs[0]
    for key, value in (("shape", _shape), ("dtype", lambda d: d["dtype"]),
                       ("quantization", lambda d: tuple(d.get("quantization", ())))):
        if value(c_input) != value(t_input):
            raise ValueError(f"CPU/TPU input {key} differs; do not compare these models")
    if any(dim <= 0 for dim in _shape(c_input)):
        raise ValueError("Dynamic/empty input shape is not supported")
    cpu_outputs, tpu_outputs = cpu.get_output_details(), tpu.get_output_details()
    if not cpu_outputs or len(cpu_outputs) != len(tpu_outputs):
        raise ValueError("CPU/TPU output count differs")
    for n, (c_out, t_out) in enumerate(zip(cpu_outputs, tpu_outputs)):
        if (_shape(c_out) != _shape(t_out) or c_out["dtype"] != t_out["dtype"]
                or tuple(c_out.get("quantization", ())) != tuple(t_out.get("quantization", ()))):
            raise ValueError(f"CPU/TPU output {n} shape/dtype/quantization differs; "
                             "provide an explicit mapping and document it")
    return c_input, cpu_outputs


def measure_once(interpreter: Any, tensor: Any, clock: Callable[[], int] = time.perf_counter_ns
                 ) -> tuple[Stages, list[Any]]:
    """Measures host-side set/invoke/get, never the isolated accelerator silicon."""
    t0 = clock()
    interpreter.set_tensor(interpreter.get_input_details()[0]["index"], tensor)
    t1 = clock()
    interpreter.invoke()
    t2 = clock()
    outputs = [interpreter.get_tensor(d["index"]) for d in interpreter.get_output_details()]
    t3 = clock()
    stages = Stages(t1 - t0, t2 - t1, t3 - t2, t3 - t0)
    if min(stages.set_ns, stages.invoke_ns, stages.get_ns) < 0:
        raise RuntimeError("Non-monotonic clock detected")
    return stages, outputs


def warmup(interpreter: Any, tensor: Any, count: int) -> None:
    for _ in range(count):
        interpreter.set_tensor(interpreter.get_input_details()[0]["index"], tensor)
        interpreter.invoke()
        for detail in interpreter.get_output_details():
            interpreter.get_tensor(detail["index"])


def run_blocks(cpu: Any, tpu: Any, tensors: Sequence[Any], *, sessions: int, blocks: int,
               warmups: int, telemetry: Callable[[], Mapping[str, Any]] = lambda: {},
               clock: Callable[[], int] = time.perf_counter_ns
               ) -> Iterator[dict[str, Any]]:
    """ABBA / BAAB blocks on identical prepared tensors; no file I/O in timed part."""
    if not tensors or sessions < 1 or blocks < 1 or warmups < 0:
        raise ValueError("Need inputs, sessions>=1, blocks>=1, warmups>=0")
    validate_pair(cpu, tpu)
    modes = {"cpu": cpu, "tpu": tpu}
    for session in range(sessions):
        for interpreter in (cpu, tpu):
            warmup(interpreter, tensors[0], warmups)
        for block in range(blocks):
            order = ("cpu", "tpu", "tpu", "cpu") if (session + block) % 2 == 0 else (
                "tpu", "cpu", "cpu", "tpu")
            for position, mode in enumerate(order):
                for input_id, tensor in enumerate(tensors):
                    stages, _ = measure_once(modes[mode], tensor, clock=clock)
                    yield {
                        "session": session,
                        "block": block,
                        "position": position,
                        "mode": mode,
                        "input_id": input_id,
                        "set_ns": stages.set_ns,
                        "invoke_ns": stages.invoke_ns,
                        "get_ns": stages.get_ns,
                        "total_ns": stages.total_ns,
                        **telemetry(),  # read AFTER timing, never from inside measure_once
                    }


def _read_integer(path: str) -> int | None:
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def pi_telemetry() -> dict[str, int | None]:
    return {
        "temperature_mC": _read_integer("/sys/class/thermal/thermal_zone0/temp"),
        "cpu_freq_kHz": _read_integer("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _git_sha() -> str | None:
    root = Path(__file__).resolve().parents[2]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _create_interpreters(cpu_model: Path, tpu_model: Path, threads: int) -> tuple[Any, Any, dict]:
    try:
        import tflite_runtime.interpreter as tflite
        from pycoral.utils import edgetpu
    except ImportError as exc:
        raise RuntimeError("Install compatible tflite_runtime and pycoral on the Pi first") from exc
    devices = edgetpu.list_edge_tpus()
    # The study is specifically about a single M.2 PCIe Edge TPU. No silent CPU fallback.
    if len(devices) != 1 or devices[0].get("type") != "pci":
        raise RuntimeError(f"Expected exactly one working PCIe Coral TPU; found: {devices}")
    t0 = time.perf_counter_ns()
    cpu = tflite.Interpreter(model_path=str(cpu_model), num_threads=threads)
    cpu.allocate_tensors()
    t1 = time.perf_counter_ns()
    tpu = edgetpu.make_interpreter(str(tpu_model))
    tpu.allocate_tensors()
    t2 = time.perf_counter_ns()
    return cpu, tpu, {"cpu_init_ns": t1-t0, "tpu_init_ns": t2-t1,
                      "devices": devices}


def _prepared_tensors(args: argparse.Namespace, input_detail: Mapping[str, Any]) -> Sequence[Any]:
    import numpy as np

    shape = _shape(input_detail)
    dtype = np.dtype(input_detail["dtype"])
    if dtype not in (np.dtype("uint8"), np.dtype("int8")):
        raise ValueError(f"Expected a quantized uint8/int8 model; got {dtype}")
    if shape[0] != 1:
        raise ValueError(f"Study uses batch size 1; got input shape {shape}")
    if args.synthetic:
        rng = np.random.default_rng(args.seed)
        bounds = np.iinfo(dtype)
        return [rng.integers(bounds.min, bounds.max + 1, size=shape, dtype=dtype)
                for _ in range(args.num_inputs)]
    data = np.load(args.inputs_npy, mmap_mode="r", allow_pickle=False)
    if data.dtype != dtype:
        raise ValueError(f"Input dtype {data.dtype} != model dtype {dtype}; prepare inputs first")
    if data.ndim == len(shape) + 1 and tuple(data.shape[1:]) == shape:
        samples = (data[i] for i in range(data.shape[0]))
    elif shape[0] == 1 and data.ndim == len(shape) and tuple(data.shape[1:]) == shape[1:]:
        # Common layout: (N, H, W, C) for an input of shape (1, H, W, C).
        samples = (data[i:i+1] for i in range(data.shape[0]))
    else:
        raise ValueError(f"Input shape {data.shape} incompatible with model shape {shape}")
    return [np.ascontiguousarray(sample) for sample in samples]


def _compare_outputs(cpu: Any, tpu: Any, tensor: Any) -> list[dict[str, Any]]:
    """Numerical diagnostics outside timed blocks; NOT a classification/detection metric."""
    import numpy as np

    _, cpu_out = measure_once(cpu, tensor)
    _, tpu_out = measure_once(tpu, tensor)
    diagnostics = []
    for c, t in zip(cpu_out, tpu_out):
        if c.shape != t.shape or c.dtype != t.dtype:
            raise ValueError("Output shapes or dtypes differ at runtime")
        diff = np.abs(c.astype("float64") - t.astype("float64"))
        if not np.all(np.isfinite(diff)):
            raise ValueError("Non-finite output values: cannot compare numerical results")
        diagnostics.append({"shape": list(c.shape), "dtype": str(c.dtype),
                            "max_abs_difference": float(diff.max()) if diff.size else 0.0,
                            "exact_equal": bool(np.array_equal(c, t))})
    return diagnostics


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-model", required=True, type=Path)
    parser.add_argument("--tpu-model", required=True, type=Path)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--inputs-npy", type=Path, help="prepared tensors (N,H,W,C) or (N,1,H,W,C)")
    inputs.add_argument("--synthetic", action="store_true", help="TEST ONLY: artificial inputs")
    parser.add_argument("--output-dir", required=True, type=Path, help="must be empty/nonexistent")
    parser.add_argument("--num-inputs", type=int, default=10, help="synthetic inputs only")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--threads", type=int, default=4, help="CPU TFLite threads; fixed per run")
    parser.add_argument("--sessions", type=int, default=3)
    parser.add_argument("--blocks", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=50)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.threads < 1 or args.num_inputs < 1 or args.sessions < 1 or args.blocks < 1 or args.warmup < 0:
        raise SystemExit("threads, inputs, sessions and blocks must be positive; warmup nonnegative")
    for path in (args.cpu_model, args.tpu_model):
        if not path.is_file():
            raise SystemExit(f"Model not found: {path}")
    if args.inputs_npy is not None and not args.inputs_npy.is_file():
        raise SystemExit(f"Prepared input file not found: {args.inputs_npy}")
    if args.output_dir.exists() and (not args.output_dir.is_dir() or any(args.output_dir.iterdir())):
        raise SystemExit(f"Refusing to overwrite a file or nonempty output directory: {args.output_dir}")

    cpu, tpu, initialization = _create_interpreters(args.cpu_model, args.tpu_model, args.threads)
    input_detail, output_details = validate_pair(cpu, tpu)
    tensors = _prepared_tensors(args, input_detail)
    if not tensors:
        raise SystemExit("Input file contains no tensors")
    diagnostics = _compare_outputs(cpu, tpu, tensors[0])
    manifest = {
        "purpose": "paired host-side TFLite microbenchmark; NOT end-to-end or accuracy",
        "synthetic": args.synthetic,
        "models": {"cpu": {"path": str(args.cpu_model), "sha256": _sha256(args.cpu_model)},
                   "tpu": {"path": str(args.tpu_model), "sha256": _sha256(args.tpu_model)}},
        "input": {"shape": list(_shape(input_detail)), "dtype": str(input_detail["dtype"]),
                  "quantization": [float(x) for x in input_detail.get("quantization", ())],
                  "count": len(tensors), "source": "synthetic" if args.synthetic else str(args.inputs_npy)},
        "outputs": [{"shape": list(_shape(d)), "dtype": str(d["dtype"])} for d in output_details],
        "design": {"sessions": args.sessions, "blocks": args.blocks, "warmup": args.warmup,
                   "cpu_threads": args.threads, "seed": args.seed,
                   "tpu_cpu_fallback_threads": "PyCoral interpreter default; verify in runtime"},
        "environment": {"host": platform.platform(), "python": sys.version,
                        "numpy": _version("numpy"), "pycoral": _version("pycoral"),
                        "tflite_runtime": _version("tflite-runtime"), "git_commit": _git_sha(),
                        **initialization},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.output_dir / "output_comparison.json").write_text(
        json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
    fields = ["session", "block", "position", "mode", "input_id", "set_ns", "invoke_ns",
              "get_ns", "total_ns", "temperature_mC", "cpu_freq_kHz"]
    # Keep CSV file I/O outside the measured experiment to avoid cache/scheduler noise.
    rows = list(run_blocks(cpu, tpu, tensors, sessions=args.sessions, blocks=args.blocks,
                           warmups=args.warmup, telemetry=pi_telemetry))
    with (args.output_dir / "runs.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {args.output_dir}; synthetic={args.synthetic}; no accuracy/end-to-end claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
