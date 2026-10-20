import AppKit
import Foundation

final class AppDelegate: NSObject, NSApplicationDelegate {
    let root: URL = {
        if let path = ProcessInfo.processInfo.environment["ANTISLOP_DATA_DIR"] {
            return URL(fileURLWithPath: path)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Antislop")
    }()
    var item: NSStatusItem!
    var status = NSMenuItem()
    var toggle = NSMenuItem()
    var controller: Process?
    var enabled = true
    var terminating = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = NSImage(systemSymbolName: "wand.and.stars", accessibilityDescription: "Antislop")
        let menu = NSMenu()
        let title = NSMenuItem(title: "Antislop", action: nil, keyEquivalent: "")
        title.isEnabled = false
        menu.addItem(title)
        status = NSMenuItem(title: "Starting…", action: nil, keyEquivalent: "")
        status.isEnabled = false
        menu.addItem(status)
        toggle = NSMenuItem(title: "Enabled", action: #selector(toggleService), keyEquivalent: "")
        toggle.target = self
        menu.addItem(toggle)
        menu.addItem(.separator())
        let logs = NSMenuItem(title: "Open Logs…", action: #selector(openLogs), keyEquivalent: "")
        logs.target = self
        menu.addItem(logs)
        let quit = NSMenuItem(title: "Quit Antislop", action: #selector(quit), keyEquivalent: "q")
        quit.target = self
        menu.addItem(quit)
        item.menu = menu
        startController()
        Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func startController() {
        DispatchQueue.global(qos: .utility).async { [self] in
            do {
                let configURL = root.appendingPathComponent("config.json")
                let config = try JSONSerialization.jsonObject(with: Data(contentsOf: configURL)) as! [String: Any]
                let python = config["python"] as! String
                let process = Process()
                process.executableURL = URL(fileURLWithPath: python)
                // `resourceURL` is not reliable for this minimal hand-built
                // bundle, so address the Resources directory explicitly.
                let pythonRoot = Bundle.main.bundleURL
                    .appendingPathComponent("Resources/python").path
                process.arguments = ["-c",
                    "import sys; sys.path.insert(0, sys.argv.pop(1)); from antislop_mcp.controller import main; main()",
                    pythonRoot, "--data-dir", root.path,
                    "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
                process.currentDirectoryURL = root
                var environment = ProcessInfo.processInfo.environment
                environment["PYTHONPATH"] = Bundle.main.resourceURL!.appendingPathComponent("python").path
                environment["PYTHONUNBUFFERED"] = "1"
                process.environment = environment
                let logURL = root.appendingPathComponent("controller.log")
                FileManager.default.createFile(atPath: logURL.path, contents: nil)
                let log = try FileHandle(forWritingTo: logURL)
                try log.seekToEnd()
                process.standardOutput = log
                process.standardError = log
                process.standardInput = FileHandle.nullDevice
                try process.run()
                DispatchQueue.main.async { self.controller = process }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { self.refresh() }
            } catch {
                DispatchQueue.main.async { self.status.title = "Could not start — check controller.log" }
            }
        }
    }

    func send(_ body: [String: Any], completion: @escaping ([String: Any]?) -> Void) {
        let socket = root.appendingPathComponent("control.sock").path
        DispatchQueue.global(qos: .utility).async {
            let python: String
            if let data = try? Data(contentsOf: self.root.appendingPathComponent("config.json")),
               let config = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
               let configured = config["python"] as? String {
                python = configured
            } else {
                python = "/usr/bin/python3"
            }
            let task = Process()
            task.executableURL = URL(fileURLWithPath: python)
            task.arguments = ["-c", "import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.sendall(sys.argv[2].encode()+b'\\n'); print(s.makefile().readline())", socket, String(data: try! JSONSerialization.data(withJSONObject: body), encoding: .utf8)!]
            let pipe = Pipe()
            task.standardOutput = pipe
            try? task.run()
            task.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            completion((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])
        }
    }

    func refresh() {
        send(["action": "status"]) { [weak self] value in
            DispatchQueue.main.async {
                guard let value else { return }
                self?.enabled = value["enabled"] as? Bool ?? true
                self?.toggle.state = self?.enabled == true ? .on : .off
                self?.status.title = value["message"] as? String ?? "Unavailable"
            }
        }
    }

    @objc func toggleService() {
        let desired = !enabled
        send(["action": "enable", "enabled": desired]) { [weak self] _ in
            DispatchQueue.main.async { self?.refresh() }
        }
    }

    @objc func openLogs() { NSWorkspace.shared.open(root) }
    @objc func quit() { NSApp.terminate(nil) }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !terminating else { return .terminateLater }
        terminating = true
        send(["action": "enable", "enabled": false]) { _ in
            DispatchQueue.main.async {
                if self.controller?.isRunning == true { self.controller?.terminate() }
                sender.reply(toApplicationShouldTerminate: true)
            }
        }
        return .terminateLater
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
