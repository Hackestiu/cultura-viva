"""
Wrapper around `optimum-cli export onnx` for environments pinned to
torch<=2.3.1.

optimum.exporters.onnx.model_patcher references torch.rms_norm at import
time (unconditionally, for patching compatibility across model types) --
that op was only added in torch 2.4, so plain `optimum-cli export onnx`
crashes on import with older torch, before export logic even runs.

VITS models don't use RMSNorm anywhere in their architecture, so stubbing
torch.rms_norm as a no-op before optimum imports is safe here: the stub is
never actually called during a VITS export, it just needs to exist so the
PatchingSpec(...) line at import time doesn't raise AttributeError.

Usage:
    python export_onnx.py --model facebook/mms-tts-eng onnx_models/mms-tts-eng
    python export_onnx.py --model kakao-enterprise/vits-ljs onnx_models/vits-ljs
    python export_onnx.py --model kakao-enterprise/vits-vctk onnx_models/vits-vctk-low
"""

import sys

import torch

if not hasattr(torch, "rms_norm"):
    def _rms_norm_stub(*args, **kwargs):
        raise NotImplementedError(
            "torch.rms_norm stub was actually called -- this model needs a "
            "real RMSNorm op, which isn't available on torch<=2.3.1. "
            "This shim is only safe for architectures (like VITS) that "
            "don't use RMSNorm."
        )
    torch.rms_norm = _rms_norm_stub
    print("[shim] stubbed torch.rms_norm for optimum import compatibility", file=sys.stderr)

from optimum.commands.optimum_cli import main

if __name__ == "__main__":
    # optimum-cli's own arg parser expects sys.argv[0] to be the program name
    # and the rest to start with the subcommand -- prepend "export"/"onnx"
    # so this behaves like `optimum-cli export onnx ...` when called as
    # `python export_onnx.py --model ... out_dir`.
    sys.argv = [sys.argv[0], "export", "onnx"] + sys.argv[1:]
    main()