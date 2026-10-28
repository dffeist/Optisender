"""Checks OptiReader reports connection status changes only, not every retry (no pad needed).

Run:  python test_opti_reader.py
"""
import contextlib
import io
import sys
import types


class FakeDevice:
    """Stands in for hid.device(); open() fails until FakeHid.pad_present is set."""

    def open(self, vid, pid):
        if not FakeHid.pad_present:
            raise OSError("open failed")

    def set_nonblocking(self, flag): pass
    def write(self, report): return len(report)
    def get_product_string(self): return "OptiShot 2"
    def close(self): pass


class FakeHid(types.ModuleType):
    pad_present = False
    device = FakeDevice


sys.modules["hid"] = FakeHid("hid")   # the real library is only needed with the hardware attached

import opti_reader  # noqa: E402


def output_of(call):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = call()
    return result, buf.getvalue()


def main():
    reader = opti_reader.OptiReader()

    # first failure at startup is reported once
    ok, out = output_of(reader.connect)
    assert not ok and out.strip() == "HID Connection Error: open failed", out

    # repeated retries with no change print nothing and keep failing
    for _ in range(5):
        ok, out = output_of(reader.reconnect)
        assert not ok and out == "", out
        assert reader.is_connected is False

    # the pad appears: the change is reported
    FakeHid.pad_present = True
    ok, out = output_of(reader.reconnect)
    assert ok and reader.is_connected and "OptiShot connected" in out, out

    # a plain connect() still reports failures (startup behaviour unchanged)
    FakeHid.pad_present = False
    fresh = opti_reader.OptiReader()
    ok, out = output_of(fresh.connect)
    assert not ok and "HID Connection Error" in out

    print("All OptiReader status checks passed.")


if __name__ == "__main__":
    main()
