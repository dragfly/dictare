/// Voxtype native launcher for macOS .app bundle.
///
/// This compiled binary is the CFBundleExecutable of Voxtype.app.
/// It requests Accessibility permission (showing "Voxtype" in the dialog,
/// not "Python"), then spawns the Python engine as a child process.
///
/// Build: swiftc -O -o Voxtype launcher.swift

import ApplicationServices
import Foundation

// --- Request Accessibility permission ---
// This makes macOS show "Voxtype" in the Accessibility dialog and list.
let key = kAXTrustedCheckOptionPrompt.takeRetainedValue() as String
let options = [key: true] as CFDictionary
AXIsProcessTrustedWithOptions(options)

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
process.arguments = ["-m", "voxtype", "engine", "start", "-d"]
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
