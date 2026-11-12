"""Hardware-free unit tests for the paired measurement protocol."""

import unittest

from benchmark import measure_once, run_blocks, validate_pair


class FakeInterpreter:
    def __init__(self, *, shape=(1, 2), dtype="uint8", quant=(0.1, 128),
                 output_shape=(1, 1)):
        self.in_detail = {"index": 0, "shape": shape, "dtype": dtype,
                          "quantization": quant}
        self.out_detail = {"index": 1, "shape": output_shape, "dtype": dtype}
        self.invocations = 0
        self.seen = []

    def get_input_details(self):
        return [self.in_detail]

    def get_output_details(self):
        return [self.out_detail]

    def set_tensor(self, index, tensor):
        assert index == 0
        self.seen.append(tensor)

    def invoke(self):
        self.invocations += 1

    def get_tensor(self, index):
        assert index == 1
        return b"result"


class SequenceClock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 10
        return self.value


class BenchmarkTests(unittest.TestCase):
    def test_measure_once_includes_exactly_set_invoke_get(self):
        interpreter = FakeInterpreter()
        stages, outputs = measure_once(interpreter, b"input", clock=SequenceClock())
        self.assertEqual((stages.set_ns, stages.invoke_ns, stages.get_ns, stages.total_ns),
                         (10, 10, 10, 30))
        self.assertEqual(outputs, [b"result"])
        self.assertEqual(interpreter.invocations, 1)

    def test_different_models_are_not_silently_compared(self):
        baseline = FakeInterpreter()
        for other in [FakeInterpreter(shape=(1, 3)), FakeInterpreter(dtype="int8"),
                      FakeInterpreter(quant=(0.2, 128)), FakeInterpreter(output_shape=(1, 2))]:
            with self.subTest(other=other.in_detail, output=other.out_detail):
                with self.assertRaises(ValueError):
                    validate_pair(baseline, other)
        changed_output_quant = FakeInterpreter()
        changed_output_quant.out_detail["quantization"] = (0.2, 0)
        baseline.out_detail["quantization"] = (0.1, 0)
        with self.assertRaises(ValueError):
            validate_pair(baseline, changed_output_quant)

    def test_order_warmup_and_identical_inputs(self):
        cpu, tpu = FakeInterpreter(), FakeInterpreter()
        clock = SequenceClock()
        rows = list(run_blocks(cpu, tpu, [b"a", b"b"], sessions=2, blocks=2,
                               warmups=3, clock=clock, telemetry=lambda: {"temp": 47000}))
        self.assertEqual(len(rows), 32)
        self.assertEqual(cpu.invocations, 22)  # 16 measured + 6 warmup
        self.assertEqual(tpu.invocations, 22)
        self.assertEqual(cpu.seen.count(b"a"), tpu.seen.count(b"a"))
        self.assertEqual(cpu.seen.count(b"b"), tpu.seen.count(b"b"))
        orders = []
        for session in range(2):
            for block in range(2):
                orders.append([r["mode"] for r in rows if r["session"] == session
                               and r["block"] == block and r["input_id"] == 0])
        self.assertEqual(orders, [["cpu", "tpu", "tpu", "cpu"],
                                  ["tpu", "cpu", "cpu", "tpu"],
                                  ["tpu", "cpu", "cpu", "tpu"],
                                  ["cpu", "tpu", "tpu", "cpu"]])
        self.assertTrue(all(row["total_ns"] == row["set_ns"] + row["invoke_ns"]
                            + row["get_ns"] == 30 for row in rows))
        self.assertTrue(all(row["temp"] == 47000 for row in rows))

    def test_rejects_invalid_design(self):
        cpu, tpu = FakeInterpreter(), FakeInterpreter()
        with self.assertRaises(ValueError):
            list(run_blocks(cpu, tpu, [], sessions=1, blocks=1, warmups=0))
        with self.assertRaises(ValueError):
            list(run_blocks(cpu, tpu, [b"a"], sessions=1, blocks=0, warmups=0))


if __name__ == "__main__":
    unittest.main()
