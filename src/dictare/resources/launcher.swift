/// Dictare native launcher for macOS .app bundle.
///
/// This compiled binary is the CFBundleExecutable of Dictare.app.
/// It handles:
/// 1. Microphone permission (shows "Dictare" in dialog, not "Python")
/// 2. Global hotkey via CGEventTap (requires Accessibility + Input Monitoring)
/// 3. Spawns the Python engine as a child process
/// 4. Sends key.down / key.up events to Python via IPC (with SIGUSR1 fallback)
///
/// The launcher is a pure forwarder: it reads the configured hotkey keycode,
/// intercepts the matching modifier key events, and forwards raw key.down /
/// key.up to Python.  Python's TapDetector handles all gesture logic
/// (single tap, double tap, long press).
///
/// Usage:
///   Dictare                    — Normal mode: permissions, hotkey, engine
///   Dictare --check-permissions — Print JSON with permission status, then exit
///
/// Build: swiftc -O -o Dictare launcher.swift

import ApplicationServices
import AVFoundation
import Cocoa
import Darwin
import Foundation

// ---------------------------------------------------------------------------
// Request Input Monitoring (called during `dictare service install`)
// ---------------------------------------------------------------------------
if CommandLine.arguments.contains("--request-input-monitoring") {
    let granted = CGRequestListenEventAccess()
    if granted {
        fputs("Input Monitoring: granted\n", stderr)
    } else {
        fputs("Input Monitoring: not granted — enable Dictare in System Settings\n", stderr)
    }
    exit(granted ? 0 : 1)
}

// ---------------------------------------------------------------------------
// Permission check mode (called by Python engine for diagnostics)
// ---------------------------------------------------------------------------
if CommandLine.arguments.contains("--check-permissions") {
    let accessibility = AXIsProcessTrusted()

    let micStatus = AVCaptureDevice.authorizationStatus(for: .audio)
    let microphone = (micStatus == .authorized)

    // NOTE: CGPreflightListenEventAccess() is unreliable from launchd on Sequoia
    // (always returns false even when granted).  Input Monitoring status is reported
    // via ~/.dictare/hotkey_status written by setupEventTap() at runtime.
    let json = "{\"accessibility\": \(accessibility), \"microphone\": \(microphone)}"
    print(json)
    exit(0)
}

// ---------------------------------------------------------------------------
// Config reader — read hotkey.key from ~/.config/dictare/config.toml
// ---------------------------------------------------------------------------

/// Read a string value from a TOML file given section and key.
/// Only handles simple `key = "value"` lines (no inline tables, arrays, etc.).
func readTomlString(path: String, section: String, key: String) -> String? {
    guard let content = try? String(contentsOfFile: path, encoding: .utf8) else {
        return nil
    }
    var inSection = false
    for line in content.components(separatedBy: "\n") {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix("[") {
            // Section header — check if this is the one we want
            inSection = trimmed == "[\(section)]"
            continue
        }
        guard inSection else { continue }
        // Parse: key = "value"
        let parts = trimmed.components(separatedBy: "=")
        guard parts.count >= 2 else { continue }
        let lineKey = parts[0].trimmingCharacters(in: .whitespaces)
        guard lineKey == key else { continue }
        var value = parts[1...].joined(separator: "=").trimmingCharacters(in: .whitespaces)
        // Strip surrounding quotes
        if value.hasPrefix("\"") && value.hasSuffix("\"") && value.count >= 2 {
            value = String(value.dropFirst().dropLast())
        }
        return value
    }
    return nil
}

/// Map an evdev key name to a macOS CGKeyCode.
/// Returns nil for unknown names.
func evdevToKeyCode(_ name: String) -> Int64? {
    switch name {
    case "KEY_RIGHTMETA":  return 54  // Right Command
    case "KEY_LEFTMETA":   return 55  // Left Command
    case "KEY_LEFTSHIFT":  return 56  // Left Shift
    case "KEY_LEFTALT":    return 58  // Left Option
    case "KEY_LEFTCTRL":   return 59  // Left Control
    case "KEY_RIGHTSHIFT": return 60  // Right Shift
    case "KEY_RIGHTALT":   return 61  // Right Option
    case "KEY_RIGHTCTRL":  return 62  // Right Control
    case "KEY_FN":         return 63  // Fn
    default:               return nil
    }
}

/// Return the CGEventFlags mask bit that corresponds to a modifier keycode.
func flagMaskForKeyCode(_ keyCode: Int64) -> CGEventFlags {
    switch keyCode {
    case 54, 55: return .maskCommand      // Right Cmd, Left Cmd
    case 56, 60: return .maskShift        // Left Shift, Right Shift
    case 58, 61: return .maskAlternate    // Left Option, Right Option
    case 59, 62: return .maskControl      // Left Control, Right Control
    case 63:     return .maskSecondaryFn  // Fn
    default:     return .maskCommand      // Fallback
    }
}

/// Resolve the configured hotkey keycode from config.toml.
/// Falls back to 54 (Right Cmd) if the file is missing or the key is unknown.
func resolveHotkeyKeyCode() -> Int64 {
    let configPath = NSHomeDirectory() + "/.config/dictare/config.toml"
    if let keyName = readTomlString(path: configPath, section: "hotkey", key: "key"),
       let code = evdevToKeyCode(keyName) {
        fputs("Hotkey: configured key=\(keyName) keyCode=\(code)\n", stderr)
        return code
    }
    fputs("Hotkey: using default Right Cmd (keyCode=54)\n", stderr)
    return 54
}

/// Resolve the mode_switch_modifier flag mask from config.toml.
/// Returns nil if the feature is disabled (key missing or empty).
func resolveModeSwitchModifier() -> CGEventFlags? {
    let configPath = NSHomeDirectory() + "/.config/dictare/config.toml"
    guard let keyName = readTomlString(path: configPath, section: "hotkey", key: "mode_switch_modifier"),
          !keyName.isEmpty,
          let code = evdevToKeyCode(keyName) else {
        return nil
    }
    let mask = flagMaskForKeyCode(code)
    fputs("Hotkey: mode_switch_modifier=\(keyName) keyCode=\(code)\n", stderr)
    return mask
}

// ---------------------------------------------------------------------------
// App Delegate — manages CGEventTap and child process
// ---------------------------------------------------------------------------
class LauncherDelegate: NSObject, NSApplicationDelegate {
    var childProcess: Process?
    var sigTermSource: DispatchSourceSignal?
    var sigIntSource: DispatchSourceSignal?
    var eventTap: CFMachPort?  // Stored for recreation after system disable
    var tapEventReceived = false  // True once first real event arrives from CGEventTap
    var tapRecreating = false     // Guard against concurrent recreation
    var hotkeySeq: UInt64 = 0

    // Configured hotkey keycode (read from config.toml at startup)
    var hotkeyKeyCode: Int64 = 54
    var hotkeyFlagMask: CGEventFlags = .maskCommand

    // Optional secondary modifier for mode switching (nil = disabled)
    var modeSwitchFlagMask: CGEventFlags? = nil

    // Track whether key.down was sent via IPC so we send key.up the same way
    var keyDownSentViaIPC = false
    // Track whether the hotkey modifier is currently held down (for combo detection)
    var hotkeyIsDown = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        hotkeyKeyCode = resolveHotkeyKeyCode()
        hotkeyFlagMask = flagMaskForKeyCode(hotkeyKeyCode)
        modeSwitchFlagMask = resolveModeSwitchModifier()
        requestMicrophonePermission()
        writeAccessibilityStatus()
        spawnPythonEngine()
        ensureTrayRunning()
        setupSignalHandling()
        setupEventTap()
    }

    // --- Signal handling ---
    // DispatchSource for reliable signal handling inside NSApplication run loop.
    // C signal() handlers don't fire reliably when NSApplication.run() owns the
    // main thread.  DispatchSource integrates with GCD and always fires.
    func setupSignalHandling() {
        // Ignore default C handlers — DispatchSource takes over
        signal(SIGTERM, SIG_IGN)
        signal(SIGINT, SIG_IGN)

        let termSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
        termSource.setEventHandler {
            fputs("SIGTERM received — shutting down\n", stderr)
            NSApplication.shared.terminate(nil)
        }
        termSource.resume()
        sigTermSource = termSource

        let intSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
        intSource.setEventHandler {
            fputs("SIGINT received — shutting down\n", stderr)
            NSApplication.shared.terminate(nil)
        }
        intSource.resume()
        sigIntSource = intSource
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        terminateChild()
        return .terminateNow
    }

    func terminateChild() {
        guard let process = childProcess, process.isRunning else { return }
        kill(process.processIdentifier, SIGTERM)
        // Give child 2 seconds to clean up, then force kill
        let deadline = Date().addingTimeInterval(2.0)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
        }
        if process.isRunning {
            kill(process.processIdentifier, SIGKILL)
        }
    }

    // --- Microphone ---
    func requestMicrophonePermission() {
        let semaphore = DispatchSemaphore(value: 0)
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            if !granted {
                fputs("Warning: Microphone access not granted\n", stderr)
            }
            semaphore.signal()
        }
        semaphore.wait()
    }

    // --- Tray app ---
    // Uses launchctl start which is idempotent: no-op if the service is already running.
    func ensureTrayRunning() {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        task.arguments = ["start", "dev.dragfly.dictare.tray"]
        try? task.run()
        fputs("Tray: launchctl start dev.dragfly.dictare.tray\n", stderr)
    }

    // --- Python engine ---
    func spawnPythonEngine() {
        let binDir = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent()
        let configFile = binDir.appendingPathComponent("python_path")

        guard let pythonPath = try? String(contentsOf: configFile, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines) else {
            fputs("Error: cannot read \(configFile.path)\n", stderr)
            NSApplication.shared.terminate(nil)
            return
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = ["-m", "dictare", "serve"]
        process.environment = ProcessInfo.processInfo.environment

        // When child exits unexpectedly, terminate the launcher too
        process.terminationHandler = { proc in
            let status = proc.terminationStatus
            let reason = proc.terminationReason
            fputs("Engine exited: status=\(status) reason=\(reason.rawValue)\n", stderr)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                NSApplication.shared.terminate(nil)
            }
        }

        do {
            try process.run()
            self.childProcess = process
            fputs("Engine started (PID \(process.processIdentifier))\n", stderr)
        } catch {
            fputs("Error starting engine: \(error)\n", stderr)
            NSApplication.shared.terminate(nil)
        }
    }

    // --- CGEventTap (global hotkey) ---

    /// Prime TCC authorization before creating a tap.
    ///
    /// CGEvent.tapCreate() can return non-nil while silently dropping events
    /// when the process hasn't yet "activated" its Input Monitoring grant in
    /// the current run-loop context.  CGRequestListenEventAccess() forces TCC
    /// to evaluate the permission synchronously; if already granted it is a
    /// no-op (no dialog shown).  Calling it before every tapCreate() closes
    /// the race between binary-hash registration and tap creation.
    func primeTCCAuthorization() {
        let granted = CGRequestListenEventAccess()
        if !granted {
            fputs("Warning: CGRequestListenEventAccess returned false\n", stderr)
        }
    }

    func teardownEventTap() {
        if let tap = eventTap {
            CGEvent.tapEnable(tap: tap, enable: false)
            CFMachPortInvalidate(tap)
            eventTap = nil
        }
        tapEventReceived = false
    }

    func recreateEventTap() {
        guard !tapRecreating else { return }
        tapRecreating = true
        teardownEventTap()
        setupEventTap()
        tapRecreating = false
    }

    func setupEventTap() {
        // Prime TCC before creating the tap — ensures the permission grant
        // is active in this process context (no-op if already granted).
        primeTCCAuthorization()

        // NOTE: Do NOT use CGPreflightListenEventAccess() here — it returns false
        // from launchd on Sequoia even when Input Monitoring IS granted (same bug
        // as AXIsProcessTrusted()).  CGEvent.tapCreate() itself is reliable: returns
        // nil when permission is missing, non-nil when granted.
        let eventMask: CGEventMask = (1 << CGEventType.flagsChanged.rawValue)
                                   | (1 << CGEventType.keyDown.rawValue)

        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: eventMask,
            callback: { proxy, type, event, refcon -> Unmanaged<CGEvent>? in
                // macOS may disable the tap after a timeout or system event.
                // We MUST re-enable it or the hotkey stops working permanently.
                if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
                    if let refcon = refcon {
                        let delegate = Unmanaged<LauncherDelegate>.fromOpaque(refcon)
                            .takeUnretainedValue()
                        let reason = type == .tapDisabledByTimeout ? "timeout" : "user input"
                        fputs("CGEventTap disabled by \(reason) — recreating tap\n", stderr)
                        // Re-enabling the existing tap is unreliable on Sequoia:
                        // the tap appears active but silently delivers no events.
                        // Destroy and recreate the tap from scratch instead.
                        DispatchQueue.main.async {
                            delegate.recreateEventTap()
                        }
                    }
                    return Unmanaged.passUnretained(event)
                }

                guard let refcon = refcon else {
                    return Unmanaged.passUnretained(event)
                }
                let delegate = Unmanaged<LauncherDelegate>.fromOpaque(refcon)
                    .takeUnretainedValue()
                // First real event confirms the tap is actually delivering events.
                // On Sequoia, CGEvent.tapCreate() can succeed (non-nil) while the
                // tap silently receives nothing — write "confirmed" only when we
                // actually see an event arrive.
                if !delegate.tapEventReceived {
                    delegate.tapEventReceived = true
                    delegate.writeHotkeyStatus("confirmed")
                    fputs("CGEventTap confirmed: first event received\n", stderr)
                }
                if type == .keyDown {
                    delegate.handleKeyDown(event: event)
                } else {
                    delegate.handleFlagsChanged(event: event)
                }
                return Unmanaged.passUnretained(event)
            },
            userInfo: Unmanaged.passUnretained(self).toOpaque()
        ) else {
            fputs("Warning: CGEventTap creation failed — hotkey disabled\n", stderr)
            fputs("Grant Input Monitoring in System Settings\n", stderr)
            writeHotkeyStatus("failed")
            return
        }

        self.eventTap = tap
        let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        fputs("Hotkey listener active (keyCode=\(hotkeyKeyCode))\n", stderr)
        writeHotkeyStatus("active")
    }

    func writeHotkeyStatus(_ status: String) {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".dictare")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("hotkey_status")
        try? status.write(to: file, atomically: true, encoding: .utf8)
    }

    func writeAccessibilityStatus() {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".dictare")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("accessibility_status")
        let status = AXIsProcessTrusted() ? "granted" : "missing"
        try? status.write(to: file, atomically: true, encoding: .utf8)
    }

    /// Handle a flagsChanged CGEvent — forward raw key.down / key.up to Python.
    ///
    /// The launcher is a pure forwarder: it does NOT filter by duration or decide
    /// what a "tap" is.  Python's TapDetector receives raw key.down / key.up events
    /// and handles all gesture logic (single tap, double tap, long press).
    func handleFlagsChanged(event: CGEvent) {
        let keyCode = event.getIntegerValueField(.keyboardEventKeycode)
        guard keyCode == hotkeyKeyCode else { return }

        let flags = event.flags
        let keyIsDown = flags.contains(hotkeyFlagMask)

        if keyIsDown {
            hotkeyIsDown = true
            // Check if the mode-switch modifier is held simultaneously
            if let modMask = modeSwitchFlagMask, flags.contains(modMask) {
                fputs("Hotkey: combo DOWN (keyCode=\(keyCode) + modifier)\n", stderr)
                sendCombo()
            } else {
                fputs("Hotkey: key DOWN (keyCode=\(keyCode))\n", stderr)
                sendKeyDown()
            }
        } else {
            hotkeyIsDown = false
            fputs("Hotkey: key UP (keyCode=\(keyCode))\n", stderr)
            sendKeyUp()
        }
    }

    /// Handle a keyDown CGEvent — if the hotkey modifier is held, this is a combo
    /// (e.g., Command+I).  Notify Python's TapDetector so it cancels the tap.
    func handleKeyDown(event: CGEvent) {
        guard hotkeyIsDown else { return }
        sendOtherKey()
    }

    func hotkeyTransportMode() -> String {
        let env = ProcessInfo.processInfo.environment["DICTARE_HOTKEY_TRANSPORT"] ?? "auto"
        return env.lowercased()
    }

    /// Send key.down to Python via IPC.  Falls back to SIGUSR1 (hotkey.tap) if IPC fails.
    func sendKeyDown() {
        hotkeySeq += 1
        let seq = hotkeySeq
        let mode = hotkeyTransportMode()

        if mode != "signal" {
            if sendIPCMessage(type: "key.down", seq: seq) {
                fputs("Hotkey: IPC key.down delivered (seq \(seq))\n", stderr)
                keyDownSentViaIPC = true
                return
            }
            fputs("Hotkey: IPC key.down failed (seq \(seq)) — falling back to SIGUSR1\n", stderr)
        }
        // SIGUSR1 fallback: simulate a complete tap (Python on_hotkey_tap does down+up)
        keyDownSentViaIPC = false
        sendToggleSignal()
    }

    /// Send key.up to Python via IPC (only if key.down was sent via IPC).
    func sendKeyUp() {
        guard keyDownSentViaIPC else {
            // key.down was sent as SIGUSR1; key.up is a no-op (tap already simulated)
            return
        }
        keyDownSentViaIPC = false
        hotkeySeq += 1
        let seq = hotkeySeq
        let mode = hotkeyTransportMode()

        if mode != "signal" {
            if sendIPCMessage(type: "key.up", seq: seq) {
                fputs("Hotkey: IPC key.up delivered (seq \(seq))\n", stderr)
                return
            }
            fputs("Hotkey: IPC key.up failed (seq \(seq))\n", stderr)
            // key.up lost — TapDetector long-press timer will fire at 0.8s and reset.
            // Not ideal but acceptable: the worst case is an unintended submit action.
        }
    }

    /// Send other_key to Python via IPC (combo detection).
    func sendOtherKey() {
        guard keyDownSentViaIPC else {
            // key.down was sent as SIGUSR1; combo detection not possible
            return
        }
        hotkeySeq += 1
        let seq = hotkeySeq
        if sendIPCMessage(type: "other_key", seq: seq) {
            fputs("Hotkey: IPC other_key delivered (seq \(seq))\n", stderr)
        }
        // If IPC fails, no fallback needed — worst case is a false tap
    }

    /// Send key.combo to Python via IPC (mode-switch: modifier + hotkey tap).
    /// Does not send key.down/key.up — the combo is treated as an atomic event.
    func sendCombo() {
        hotkeySeq += 1
        let seq = hotkeySeq
        keyDownSentViaIPC = false  // Skip key.up — combo is atomic
        if sendIPCMessage(type: "key.combo", seq: seq) {
            fputs("Hotkey: IPC key.combo delivered (seq \(seq))\n", stderr)
        } else {
            fputs("Hotkey: IPC key.combo failed (seq \(seq)) — no fallback\n", stderr)
        }
    }

    /// Send a single IPC message to the Python engine and wait for ACK.
    func sendIPCMessage(type msgType: String, seq: UInt64) -> Bool {
        let socketPath = NSHomeDirectory() + "/.dictare/hotkey.sock"
        let maxPathLen = MemoryLayout.size(ofValue: sockaddr_un().sun_path)
        if socketPath.utf8.count >= maxPathLen {
            return false
        }

        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        if fd < 0 {
            return false
        }
        defer { _ = close(fd) }

        var timeout = timeval(tv_sec: 0, tv_usec: 250_000)
        withUnsafePointer(to: &timeout) { ptr in
            _ = setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, ptr, socklen_t(MemoryLayout<timeval>.size))
            _ = setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, ptr, socklen_t(MemoryLayout<timeval>.size))
        }

        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        socketPath.withCString { cs in
            withUnsafeMutablePointer(to: &addr.sun_path) { sp in
                sp.withMemoryRebound(to: CChar.self, capacity: maxPathLen) { cp in
                    strncpy(cp, cs, maxPathLen - 1)
                    cp[maxPathLen - 1] = 0
                }
            }
        }

        let connected = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sap in
                connect(fd, sap, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        if connected != 0 {
            return false
        }

        let payload = "{\"type\":\"\(msgType)\",\"seq\":\(seq),\"ts\":\(Date().timeIntervalSince1970)}\n"
        let sendResult = payload.withCString { cs in
            send(fd, cs, strlen(cs), 0)
        }
        if sendResult <= 0 {
            return false
        }

        var buf = [UInt8](repeating: 0, count: 512)
        let n = recv(fd, &buf, buf.count, 0)
        if n <= 0 {
            return false
        }

        let raw = String(decoding: buf[0..<n], as: UTF8.self)
        guard let line = raw.split(separator: "\n").first else { return false }
        guard let data = line.data(using: .utf8) else { return false }
        guard
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let ackType = obj["type"] as? String,
            let ackSeq = obj["seq"] as? NSNumber
        else {
            return false
        }
        return ackType == "ack" && ackSeq.uint64Value == seq
    }

    func sendToggleSignal() {
        guard let process = childProcess, process.isRunning else {
            fputs("Hotkey: sendToggleSignal — no child process running\n", stderr)
            return
        }
        kill(process.processIdentifier, SIGUSR1)
        fputs("Hotkey: SIGUSR1 sent to PID \(process.processIdentifier)\n", stderr)
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
let app = NSApplication.shared
app.setActivationPolicy(.accessory)  // No Dock icon (like LSUIElement)

let delegate = LauncherDelegate()
app.delegate = delegate

app.run()
