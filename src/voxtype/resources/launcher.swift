/// Voxtype native launcher for macOS .app bundle.
///
/// This compiled binary is the CFBundleExecutable of Voxtype.app.
/// It requests Microphone permission (showing "Voxtype" in dialogs, not
/// "Python"), then spawns the Python engine as a child process.
///
/// Note: Accessibility (CGEventTap) is NOT requested here because it does not
/// work from launchd-spawned processes on macOS Sequoia.  AXIsProcessTrusted()
/// always returns false in that context regardless of TCC entries.  The global
/// hotkey only works when `voxtype serve` runs in a foreground Terminal session.
///
/// Usage:
///   Voxtype                    — Normal mode: request permissions, launch engine
///   Voxtype --check-permissions — Print JSON with permission status, then exit
///
/// Build: swiftc -O -o Voxtype launcher.swift

import ApplicationServices
import AVFoundation
import Foundation

// --- Permission check mode ---
// Called by the Python engine to check permissions on behalf of the .app bundle.
// This binary IS the trusted process, so AXIsProcessTrusted() returns the real answer.
if CommandLine.arguments.contains("--check-permissions") {
    let accessibility = AXIsProcessTrusted()

    let micStatus = AVCaptureDevice.authorizationStatus(for: .audio)
    let microphone = (micStatus == .authorized)

    let json = "{\"accessibility\": \(accessibility), \"microphone\": \(microphone)}"
    print(json)
    exit(0)
}

// --- Request Microphone permission ---
// This makes macOS show "Voxtype" in the Microphone dialog and list.
// Without this + NSMicrophoneUsageDescription in Info.plist, the mic
// silently returns zeros.
let micSemaphore = DispatchSemaphore(value: 0)
AVCaptureDevice.requestAccess(for: .audio) { granted in
    if !granted {
        fputs("Warning: Microphone access not granted\n", stderr)
    }
    micSemaphore.signal()
}
micSemaphore.wait()

// --- Resolve Python path ---
// Read from companion file "python_path" next to this binary.
let binDir = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent()
let configFile = binDir.appendingPathComponent("python_path")

guard let pythonPath = try? String(contentsOf: configFile, encoding: .utf8)
    .trimmingCharacters(in: .whitespacesAndNewlines) else {
    fputs("Error: cannot read \(configFile.path)\n", stderr)
    exit(1)
}

// --- Spawn Python engine as child process ---
let process = Process()
process.executableURL = URL(fileURLWithPath: pythonPath)
process.arguments = ["-m", "voxtype", "serve"]
process.environment = ProcessInfo.processInfo.environment

// Forward SIGTERM/SIGINT to child
signal(SIGTERM) { _ in kill(process.processIdentifier, SIGTERM) }
signal(SIGINT) { _ in kill(process.processIdentifier, SIGINT) }

do {
    try process.run()
    process.waitUntilExit()
    exit(process.terminationStatus)
} catch {
    fputs("Error: \(error)\n", stderr)
    exit(1)
}
