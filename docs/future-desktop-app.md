# Future plan: self-contained desktop app

## Goal

Distribute ScribbleFactory as an installable desktop application for Windows, macOS, and Linux. A user should be able to install it and use the dashboard, rendering pipeline, offline Whisper timing, and local library without separately installing Python, Node, npm, Chromium, FFmpeg, or other project dependencies.

The application remains local-first and offline at runtime. The user's video library and generated files remain on disk and should be movable or backed up independently of the application installation.

## Proposed architecture

- Package the existing Vue frontend inside a desktop shell.
- Start the bundled FastAPI backend automatically on an internal localhost port.
- Bundle the Python runtime and the FastAPI/pipeline dependencies.
- Bundle the Node renderer, Playwright Chromium, and Three.js assets.
- Bundle FFmpeg and FFprobe with platform-specific binaries.
- Include the faster-whisper model and project fonts/assets.
- Keep the current file-based `library/` format as the data model.
- Store default user data in an OS-appropriate writable application-data directory, while allowing the library location to be selected or overridden.

Electron is the most straightforward first shell because the project already uses Node and Chromium. Tauri is a possible later alternative if reducing installer size becomes important.

## Platform deliverables

- Windows: signed installer and portable build if practical.
- macOS: signed and notarized `.app` distributed in a `.dmg`; test Apple Silicon and Intel targets as needed.
- Linux: AppImage as the first target, with `.deb` considered later.

## Planned phases

1. **Dependency audit**
   - Identify every runtime file, executable, model, browser asset, and generated resource required by a clean installation.
   - Confirm licenses and redistribution terms for Chromium, FFmpeg, Whisper model, fonts, and npm/Python dependencies.

2. **Desktop launcher prototype**
   - Add a development-only shell that starts the API, waits for its health endpoint, opens the frontend, and shuts down all child processes cleanly.
   - Make paths independent of the current working directory.

3. **Runtime bundling**
   - Package Python and the application code.
   - Bundle Node and the renderer dependencies.
   - Bundle Playwright Chromium, FFmpeg/FFprobe, the Whisper model, fonts, and static assets.
   - Replace PATH-only assumptions with resolved bundled executable paths while retaining developer-mode overrides.

4. **Library and settings handling**
   - Add a first-run library-directory choice.
   - Separate read-only packaged resources from writable user data.
   - Provide diagnostics for disk space, missing resources, renderer status, and FFmpeg availability.

5. **Installers and release automation**
   - Build Windows, macOS, and Linux artifacts on their native or compatible build environments.
   - Add application icons, version metadata, update notes, and crash/log collection suitable for a local-only app.
   - Configure code signing and macOS notarization before public distribution.

6. **Cross-platform validation**
   - Test a clean machine with no preinstalled Python, Node, npm, FFmpeg, or Playwright.
   - Exercise story editing, voice import, timing, still rendering, final rendering, cancellation, restart recovery, and large libraries.
   - Test GPU rendering and SwiftShader fallback on representative hardware.

## Main risks

- Installer size will be substantial because of Chromium, FFmpeg, and the Whisper model.
- WebGL and Chromium behavior may differ across GPU drivers and operating systems.
- Process-tree cleanup and file locking need separate Windows, macOS, and Linux testing.
- macOS signing/notarization and Windows code signing require certificates and release infrastructure.
- Linux support will have more variation between distributions than Windows or macOS.
- The current shell setup scripts are not a substitute for native packaging and should remain developer tooling.

## Definition of done

A clean machine on each supported platform can install ScribbleFactory, launch it from the desktop, select or create a library, render a complete sample project, close and reopen the app without orphaned services, and uninstall the application without deleting the user's library unless explicitly requested.

