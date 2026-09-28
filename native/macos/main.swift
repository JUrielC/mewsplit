// mewsplit — ventana nativa de macOS.
//
// Es a la vez lanzador y ventana: arranca el servidor de mewsplit (el comando
// que instala uv), muestra la interfaz en un WKWebView y detiene el servidor
// al cerrarse. Da a mewsplit su propio icono en el Dock y en Cmd+Tab, en vez
// de ser una ventana más del navegador del usuario.
//
// Por qué no la bloquea Gatekeeper sin firma de Apple: llega dentro del
// paquete de Python que baja uv, y lo que baja uv no lleva la marca de
// cuarentena. El enlazador le pone la firma ad-hoc que exige Apple Silicon.
//
// Dos modos:
//   sin argumentos   lanzador: la ruta del comando `mewsplit` sale de la clave
//                    MewsplitCommand del Info.plist (la escribe install.sh).
//   con una URL      solo ventana: el servidor ya lo lleva otro proceso (así
//                    la abre el comando `mewsplit` desde la terminal).

import Cocoa
import UniformTypeIdentifiers
import WebKit

/// Contrato con backend/mewsplit/app.py: con MEWSPLIT_NATIVE=1 imprime
/// `MEWSPLIT_APP_READY url=<url> owner=<new|existing>` cuando está listo.
private let readyPrefix = "MEWSPLIT_APP_READY "

private let logURL = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Logs/mewsplit.log")

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    /// Solo se detiene al salir un servidor que arrancamos nosotros: si ya
    /// había uno (abierto desde la terminal), es de otro y sigue vivo.
    private var ownsServer = false
    private var baseURL: URL?
    private var stdoutBuffer = Data()
    private var keepAliveTimer: Timer?
    /// Al salir detenemos el servidor nosotros: que su final no parezca un fallo.
    private var terminating = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        buildWindow()

        if let arg = CommandLine.arguments.dropFirst().first(where: { $0.hasPrefix("http") }),
           let url = URL(string: arg) {
            open(url)
        } else {
            showStatus("arrancando mewsplit…")
            startServer()
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        terminating = true
        keepAliveTimer?.invalidate()
        guard ownsServer, let server, server.isRunning else { return }

        // El cierre ordenado de uvicorn espera a que acabe el análisis en
        // curso: cerrar la app a mitad de una separación dejaría el servidor
        // trabajando a escondidas unos segundos más. Se le da un segundo y
        // luego se termina a la fuerza; los trabajos viven en memoria y se
        // perderían igual.
        server.terminate()
        let deadline = Date().addingTimeInterval(1)
        while server.isRunning && Date() < deadline {
            usleep(50_000)
        }
        if server.isRunning {
            kill(server.processIdentifier, SIGKILL)
        }
    }

    // MARK: - Servidor

    private func startServer() {
        guard let command = Bundle.main.object(forInfoDictionaryKey: "MewsplitCommand") as? String,
              FileManager.default.isExecutableFile(atPath: command) else {
            showStatus("no se encontró mewsplit. vuelve a ejecutar el comando de instalación.", isError: true)
            return
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: command)
        var environment = ProcessInfo.processInfo.environment
        environment["MEWSPLIT_NATIVE"] = "1"
        process.environment = environment

        let log = openLog()
        let output = Pipe()
        process.standardOutput = output
        process.standardError = log ?? FileHandle.nullDevice
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            log?.write(data)
            DispatchQueue.main.async { self?.consume(data) }
        }
        process.terminationHandler = { [weak self] process in
            DispatchQueue.main.async { self?.serverExited(process) }
        }

        do {
            try process.run()
            server = process
        } catch {
            showStatus("no se pudo arrancar mewsplit: \(error.localizedDescription)", isError: true)
        }
    }

    private func consume(_ data: Data) {
        stdoutBuffer.append(data)
        while let newline = stdoutBuffer.firstIndex(of: 0x0A) {
            let line = String(decoding: stdoutBuffer[..<newline], as: UTF8.self)
            stdoutBuffer.removeSubrange(...newline)
            guard line.hasPrefix(readyPrefix) else { continue }

            var fields: [String: String] = [:]
            for pair in line.dropFirst(readyPrefix.count).split(separator: " ") {
                let parts = pair.split(separator: "=", maxSplits: 1)
                if parts.count == 2 { fields[String(parts[0])] = String(parts[1]) }
            }
            if let raw = fields["url"], let url = URL(string: raw) {
                ownsServer = fields["owner"] == "new"
                open(url)
            }
        }
    }

    private func serverExited(_ process: Process) {
        if terminating { return }
        // Si ya había otra instancia, el proceso avisa dónde está y termina:
        // es lo esperado, la ventana sigue usando ese servidor.
        if baseURL != nil && !ownsServer { return }
        keepAliveTimer?.invalidate()
        showStatus("mewsplit se detuvo inesperadamente. revisa ~/Library/Logs/mewsplit.log", isError: true)
    }

    private func openLog() -> FileHandle? {
        let manager = FileManager.default
        try? manager.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !manager.fileExists(atPath: logURL.path) {
            manager.createFile(atPath: logURL.path, contents: nil)
        }
        let handle = try? FileHandle(forWritingTo: logURL)
        handle?.seekToEndOfFile()
        return handle
    }

    // MARK: - Ventana

    private func open(_ url: URL) {
        baseURL = url
        webView.load(URLRequest(url: url))
        startKeepAlive(url)
    }

    /// La página avisa cada minuto que sigue abierta (keepAlive en lib/api.ts),
    /// pero WebKit pausa los temporizadores de una ventana minimizada: sin este
    /// aviso nativo el servidor se apagaría solo con la app abierta.
    private func startKeepAlive(_ url: URL) {
        keepAliveTimer?.invalidate()
        let health = url.appendingPathComponent("health")
        keepAliveTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { _ in
            URLSession.shared.dataTask(with: health).resume()
        }
    }

    private func buildWindow() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        // La reproducción siempre la inicia un clic del usuario en el transporte.
        configuration.mediaTypesRequiringUserActionForPlayback = []

        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        // Sin esto se ve un destello blanco antes de que cargue el fondo oscuro.
        webView.setValue(false, forKey: "drawsBackground")

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 800),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        window.title = "mewsplit"
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = NSColor(red: 0x10 / 255, green: 0x11 / 255, blue: 0x14 / 255, alpha: 1)
        window.minSize = NSSize(width: 960, height: 600)
        window.contentView = webView
        window.center()
        window.setFrameAutosaveName("mewsplit")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func showStatus(_ message: String, isError: Bool = false) {
        let color = isError ? "#ff4d00" : "#a8acb6"
        let html = """
        <html><body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
        background:#101114;color:\(color);font:12px -apple-system,sans-serif;letter-spacing:.14em;
        text-transform:lowercase">\(message)</body></html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    // MARK: - Menú

    private func buildMenu() {
        let main = NSMenu()

        let app = NSMenu()
        app.addItem(withTitle: "Acerca de mewsplit",
                    action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(withTitle: "Ocultar mewsplit", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let others = app.addItem(withTitle: "Ocultar otras",
                                 action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        others.keyEquivalentModifierMask = [.command, .option]
        app.addItem(withTitle: "Mostrar todo",
                    action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(withTitle: "Salir de mewsplit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        let edit = NSMenu(title: "Edición")
        edit.addItem(withTitle: "Deshacer", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = edit.addItem(withTitle: "Rehacer", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cortar", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copiar", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Pegar", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Seleccionar todo", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        let view = NSMenu(title: "Ver")
        view.addItem(withTitle: "Recargar", action: #selector(reload), keyEquivalent: "r").target = self
        let fullScreen = view.addItem(withTitle: "Pantalla completa",
                                      action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        fullScreen.keyEquivalentModifierMask = [.command, .control]

        let windowMenu = NSMenu(title: "Ventana")
        windowMenu.addItem(withTitle: "Minimizar", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        windowMenu.addItem(withTitle: "Cerrar", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")

        for menu in [app, edit, view, windowMenu] {
            let item = NSMenuItem()
            item.submenu = menu
            main.addItem(item)
        }
        NSApp.mainMenu = main
        NSApp.windowsMenu = windowMenu
    }

    @objc private func reload() {
        if let baseURL { webView.load(URLRequest(url: baseURL)) } else { webView.reload() }
    }
}

// MARK: - Navegación y descargas

extension AppDelegate: WKNavigationDelegate, WKDownloadDelegate {
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.shouldPerformDownload {
            decisionHandler(.download)
            return
        }
        // Un enlace que sale de mewsplit se abre en el navegador del usuario.
        if action.navigationType == .linkActivated, let url = action.request.url,
           url.host != baseURL?.host, ["http", "https"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(response.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    /// "save mix" crea un <a download> con un blob: en un navegador se descarga
    /// solo; en una ventana nativa hay que preguntar dónde guardarlo.
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        #if MEWSPLIT_AUTOTEST
        if let dir = Autotest.directory {
            completionHandler(dir.appendingPathComponent(suggestedFilename))
            return
        }
        #endif
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.directoryURL = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
        panel.beginSheetModal(for: window) { result in
            guard result == .OK, let url = panel.url else { return completionHandler(nil) }
            // WKDownload no sobrescribe: si el usuario confirmó reemplazar, se borra antes.
            try? FileManager.default.removeItem(at: url)
            completionHandler(url)
        }
    }

    func downloadDidFinish(_ download: WKDownload) {
        #if MEWSPLIT_AUTOTEST
        Autotest.report("descarga-terminada")
        #endif
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let alert = NSAlert()
        alert.messageText = "No se pudo guardar el archivo"
        alert.informativeText = error.localizedDescription
        alert.beginSheetModal(for: window)
    }

    #if MEWSPLIT_AUTOTEST
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        Autotest.run(in: webView)
    }
    #endif
}

// MARK: - Abrir archivos

extension AppDelegate: WKUIDelegate {
    /// En un navegador el <input type="file"> abre su propio diálogo; en un
    /// WKWebView hay que abrirlo nosotros o el clic no hace nada.
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        #if MEWSPLIT_AUTOTEST
        if let dir = Autotest.directory {
            Autotest.report("abrir-archivo")
            completionHandler([dir.appendingPathComponent("entrada.wav")])
            return
        }
        #endif
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false
        // Los mismos formatos que acepta DropZone. .ogg no siempre cuelga de
        // public.audio, así que se añaden las extensiones explícitas.
        panel.allowedContentTypes = [.audio] + ["wav", "mp3", "flac", "aiff", "aif", "m4a", "ogg"]
            .compactMap { UTType(filenameExtension: $0) }
        panel.beginSheetModal(for: window) { result in
            completionHandler(result == .OK ? panel.urls : nil)
        }
    }
}

// MARK: - Pruebas automáticas

#if MEWSPLIT_AUTOTEST
/// Solo en el binario de pruebas (compilado con -D MEWSPLIT_AUTOTEST): con
/// MEWSPLIT_AUTOTEST_DIR, los diálogos se contestan solos con esa carpeta y,
/// al cargar la interfaz, se pulsa "elegir archivo" y se guarda un archivo de
/// prueba. Así se verifica el cableado de abrir y guardar sin tocar el ratón.
enum Autotest {
    static let directory = ProcessInfo.processInfo.environment["MEWSPLIT_AUTOTEST_DIR"].map {
        URL(fileURLWithPath: $0)
    }
    private static var done = false
    private static var pending: Set<String> = ["abrir-archivo", "descarga-terminada"]

    /// Cuando ya pasó por abrir y guardar, espera a que la subida llegue al
    /// servidor y cierra la app: así se prueba también que lo detiene al salir.
    static func report(_ event: String) {
        print("autotest:", event)
        fflush(stdout)
        pending.remove(event)
        if pending.isEmpty {
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { NSApp.terminate(nil) }
        }
    }

    static func run(in webView: WKWebView) {
        guard directory != nil, !done, webView.url?.scheme == "http" else { return }
        done = true
        let script = """
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob(['mewsplit'], {type: 'audio/wav'}));
        a.download = 'prueba.wav';
        document.body.appendChild(a); a.click();
        document.querySelector('input[type=file]').click();
        """
        webView.evaluateJavaScript(script) { _, error in
            report(error == nil ? "script-ok" : "script-error \(error!)")
        }
    }
}
#endif

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
