"""Process exit codes shared by the engine and native supervisors."""

from __future__ import annotations

# A normal, intentional shutdown. Supervisors must not restart the engine.
EXIT_OK = 0

# A controlled restart requested by settings or another protocol client.
# 75 is EX_TEMPFAIL on BSD/macOS and communicates that retrying is intentional.
EXIT_RESTART_REQUESTED = 75

# PortAudio timed out inside native code. The current process is unsafe to reuse.
EXIT_AUDIO_POISONED = 70
