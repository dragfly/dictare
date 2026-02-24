# Terminal Compatibility Guide

This guide helps troubleshoot terminal display issues and escape sequence problems across different terminal emulators.

## Common Issues

### Escape Sequences Appearing as Text

If you see characters like `[27;2;13~` or `^[[` appearing in your terminal, these are escape sequences that aren't being properly interpreted.

**Example:**
```
[27;2;13~Hello[27;2;13~World
```

**Causes:**
1. Terminal sending modifier key sequences (Shift+Function keys, Alt+keys, etc.)
2. Incorrect `TERM` environment variable
3. Terminal emulator compatibility issues

**Solutions:**

#### 1. Check Your TERM Variable
```bash
echo $TERM
```

For most modern terminals, this should be:
- `xterm-256color` (most common)
- `screen-256color` (if using tmux/screen)
- Terminal-specific values (e.g., `ghostty`, `alacritty`, `wezterm`)

To fix temporarily:
```bash
export TERM=xterm-256color
```

To fix permanently, add to your shell config (`~/.zshrc`, `~/.bashrc`, etc.):
```bash
export TERM=xterm-256color
```

#### 2. Ghostty-Specific Configuration

If you're using Ghostty terminal, create or edit `~/.config/ghostty/config`:

```toml
# REQUIRED for dictare keyboard mode with auto_enter=false
# Fix Shift+Enter to send newline instead of escape sequence [27;2;13~
keybind = shift+enter=text:\n

# Optional: Set terminal type
term = xterm-256color
```

**Why is this needed?**

Ghostty implements the "modifyOtherKeys" terminal standard which sends detailed escape sequences for modified keys. When you press Shift+Enter, Ghostty sends `[27;2;13~` instead of a simple newline character.

This affects:
- dictare with `auto_enter=false` (accumulate mode)
- Claude Code multi-line input
- Any app expecting Shift+Enter = newline

The `keybind = shift+enter=text:\n` remaps Shift+Enter to send `\n`, matching the behavior of iTerm2 and Terminal.app. This is safe because Shift+Enter has no special meaning in terminals by default.

#### 3. Terminal Compatibility Mode

Some terminals have compatibility modes. For Ghostty:
- Check if you have any custom keybindings that might be sending escape sequences
- Try disabling any special key modifiers in your terminal settings

#### 4. Shell Configuration

Check if your shell is outputting these sequences. Test in a clean shell:
```bash
bash --norc
# or
zsh -f
```

If the issue disappears, it's likely a shell configuration problem.

### Box Drawing Characters Not Displaying

If dictare's status panel shows broken box characters, your terminal might not support UTF-8 box drawing.

**Solution:**
Ensure your terminal and locale support UTF-8:
```bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

## Virtualized macOS (UTM, Parallels, VMware)

### MLX/Metal Acceleration Issues

If you see errors like:
```
Error: Unable to load kernel steel_gemm_fused...
error: unsupported deferred-static-alloca-size function body
```

This is because MLX's Metal GPU acceleration doesn't work in virtualized environments.

**Solution:**

dictare v2.15.3+ automatically detects virtualized macOS and disables hardware acceleration.

For older versions or manual override:
```bash
dictare listen --no-hw-accel
```

Or set in config (`~/.config/dictare/config.toml`):
```toml
[stt]
hw_accel = false
```

## Testing Terminal Compatibility

Test your terminal's capabilities:

```bash
# Test box drawing
echo "┌─────┐"
echo "│ Hi! │"
echo "└─────┘"

# Test colors
echo -e "\033[31mRed\033[0m \033[32mGreen\033[0m \033[33mYellow\033[0m"

# Test your TERM supports 256 colors
tput colors
```

Expected output:
- Box characters should be connected lines (not broken)
- Colors should display correctly
- `tput colors` should output `256`

## Recommended Terminal Emulators

Fully tested and compatible:
- **iTerm2** (macOS) - Excellent compatibility
- **Alacritty** - Fast, cross-platform
- **WezTerm** - Feature-rich, cross-platform
- **Ghostty** (with proper config) - Modern, fast

Known issues:
- **Terminal.app** (macOS) - Limited color support, slower
- **Windows Terminal** - Works but requires WSL or proper setup

## Getting Help

If you're still experiencing issues:

1. Capture debug output:
   ```bash
   dictare listen --verbose 2>&1 | tee dictare_debug.log
   ```

2. Include in your report:
   - Terminal emulator and version
   - Output of `echo $TERM`
   - Output of `tput colors`
   - Operating system and version
   - Whether running in VM
   - The debug log

3. Report at: https://github.com/anthropics/dictare/issues (or your repo URL)
