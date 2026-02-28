/// Dictare native launcher for macOS .app bundle.
///
/// This compiled binary is the CFBundleExecutable of Dictare.app.
/// It handles:
/// 1. Microphone permission (shows "Dictare" in dialog, not "Python")
/// 2. Global hotkey via CGEventTap (requires Accessibility + Input Monitoring)
/// 3. Spawns the Python engine as a child process
/// 4. Sends SIGUSR1 to Python on hotkey tap to toggle listening
///
/// Usage:
///   Dictare                    — Normal mode: permissions, hotkey, engine
///   Dictare --check-permissions — Print JSON with permission status, then exit
///
/// Build: swiftc -O -o Dictare launcher.swift

import ApplicationServices
import AVFoundation
import Cocoa
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
// App Delegate — manages CGEventTap and child process
// ---------------------------------------------------------------------------
class LauncherDelegate: NSObject, NSApplicationDelegate {
    var childProcess: Process?
    var keyDownTime: Date?
    let tapThreshold: TimeInterval = 0.5  // Max press duration for a "tap"
    var sigTermSource: DispatchSourceSignal?
    var sigIntSource: DispatchSourceSignal?
    var eventTap: CFMachPort?  // Stored for recreation after system disable
    var tapEventReceived = false  // True once first real event arrives from CGEventTap
    var tapRecreating = false     // Guard against concurrent recreation

    func applicationDidFinishLaunching(_ notification: Notification) {
        requestMicrophonePermission()
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
        task.arguments = ["start", "com.dragfly.dictare.tray"]
        try? task.run()
        fputs("Tray: launchctl start com.dragfly.dictare.tray\n", stderr)
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
                    return Unmanaged.passRetained(event)
                }

                guard let refcon = refcon else {
                    return Unmanaged.passRetained(event)
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
                delegate.handleFlagsChanged(event: event)
                return Unmanaged.passRetained(event)
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
        fputs("Hotkey listener active (Right Cmd)\n", stderr)
        writeHotkeyStatus("active")
    }

    func writeHotkeyStatus(_ status: String) {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".dictare")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("hotkey_status")
        try? status.write(to: file, atomically: true, encoding: .utf8)
    }

    func handleFlagsChanged(event: CGEvent) {
        let keyCode = event.getIntegerValueField(.keyboardEventKeycode)

        // Right Cmd = keycode 54
        guard keyCode == 54 else { return }

        let flags = event.flags
        let rightCmdDown = flags.contains(.maskCommand)

        if rightCmdDown {
            // Key pressed — record timestamp
            keyDownTime = Date()
            fputs("Hotkey: Right Cmd DOWN\n", stderr)
        } else if let downTime = keyDownTime {
            // Key released — check if it was a tap (short press)
            let duration = Date().timeIntervalSince(downTime)
            keyDownTime = nil
            fputs(String(format: "Hotkey: Right Cmd UP (duration=%.3fs)\n", duration), stderr)

            if duration < tapThreshold {
                fputs("Hotkey: tap accepted — sending SIGUSR1\n", stderr)
                sendToggleSignal()
            } else {
                fputs(String(format: "Hotkey: tap rejected (too long, threshold=%.1fs)\n", tapThreshold), stderr)
            }
        }
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
