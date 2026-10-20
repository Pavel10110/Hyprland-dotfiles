# Dictation GPU acceleration

The desktop toggle script uses whisper-cli with the small model, automatic language detection, and an explicit CPU thread count. GPU acceleration is automatically selected by whisper-cli when the ggml Vulkan backend is installed.

## Restore

Install whisper-cpp and ggml-vulkan from the package manifests. Ensure the machine has a working Vulkan driver (on this NVIDIA desktop: nvidia-utils matching the loaded kernel driver). Model binaries remain outside Git at ~/.local/share/vexa/models/ggml-small.bin.

## Diagnose

Dictation logs are at /tmp/vexa-dictation-$UID/log.txt. A successful GPU-enabled invocation should report both the Vulkan backend and the detected GPU. CPU-backend loading alongside Vulkan is normal; loading only CPU indicates GPU acceleration is absent or failed.

The first Vulkan invocation after a driver/backend update can take substantially longer while shaders/pipelines are cached. Repeat the same recording to distinguish cold initialization from recurring latency. Preserve the small model and automatic language selection unless the user requests a quality/language change.

## Verification

Benchmark an existing clean.wav directly with whisper-cli, without invoking the desktop toggle or pasting into the active window. Compare normal GPU mode with -ng (CPU-only). Time total process execution, not just model inference, and compare output files. Do not record new microphone audio remotely for a benchmark.
