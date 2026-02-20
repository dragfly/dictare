/// Voxtype native launcher for macOS .app bundle.
///
/// This compiled binary is the CFBundleExecutable of Voxtype.app.
/// It handles:
/// 1. Microphone permission (shows "Voxtype" in dialog, not "Python")
/// 2. Global hotkey via CGEventTap (requires Accessibility + Input Monitoring)
/// 3. Spawns the Python engine as a child process
/// 4. Sends SIGUSR1 to Python on hotkey tap to toggle listening
///
/// Usage:
///   Voxtype                    — Normal mode: permissions, hotkey, engine
///   Voxtype --check-permissions — Print JSON with permission status, then exit
///
/// Build: swiftc -O -o Voxtype launcher.swift

import ApplicationServices
import AVFoundation
import Cocoa
import Foundation

// ---------------------------------------------------------------------------
// Permission check mode (called by Python engine for diagnostics)
// ---------------------------------------------------------------------------
if CommandLine.arguments.contains("--check-permissions") {
    let accessibility = AXIsProcessTrusted()

    let micStatus = AVCaptureDevice.authorizationStatus(for: .audio)
    let microphone = (micStatus == .authorized)

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

    func applicationDidFinishLaunching(_ notification: Notification) {
        requestMicrophonePermission()
        spawnPythonEngine()
        setupEventTap()
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
        process.arguments = ["-m", "voxtype", "serve"]
        process.environment = ProcessInfo.processInfo.environment

        // When child exits, terminate the launcher too
        process.terminationHandler = { proc in
            // Small delay to let cleanup happen
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                exit(proc.terminationStatus)
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

        // Forward SIGTERM/SIGINT to child
        signal(SIGTERM) { _ in
            // Can't capture self in C signal handler, so use the global reference
            LauncherDelegate.forwardSignal(SIGTERM)
        }
        signal(SIGINT) { _ in
            LauncherDelegate.forwardSignal(SIGINT)
        }
    }

    // Static reference for signal forwarding (C signal handlers can't capture self)
    static weak var shared: LauncherDelegate?

    static func forwardSignal(_ sig: Int32) {
        if let pid = shared?.childProcess?.processIdentifier, pid > 0 {
            kill(pid, sig)
        }
        exit(0)
    }

    // --- CGEventTap (global hotkey) ---
    func setupEventTap() {
        let eventMask: CGEventMask = (1 << CGEventType.flagsChanged.rawValue)

        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: eventMask,
            callback: { proxy, type, event, refcon -> Unmanaged<CGEvent>? in
                guard let refcon = refcon else {
                    return Unmanaged.passRetained(event)
                }
                let delegate = Unmanaged<LauncherDelegate>.fromOpaque(refcon)
                    .takeUnretainedValue()
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

        let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        fputs("Hotkey listener active (Right Cmd)\n", stderr)
        writeHotkeyStatus("active")
    }

    func writeHotkeyStatus(_ status: String) {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".voxtype")
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
        } else if let downTime = keyDownTime {
            // Key released — check if it was a tap (short press)
            let duration = Date().timeIntervalSince(downTime)
            keyDownTime = nil

            if duration < tapThreshold {
                sendToggleSignal()
            }
        }
    }

    func sendToggleSignal() {
        guard let process = childProcess, process.isRunning else { return }
        kill(process.processIdentifier, SIGUSR1)
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
let app = NSApplication.shared
app.setActivationPolicy(.accessory)  // No Dock icon (like LSUIElement)

let delegate = LauncherDelegate()
LauncherDelegate.shared = delegate
app.delegate = delegate

app.run()
