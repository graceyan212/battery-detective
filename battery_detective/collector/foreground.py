"""App identity only. No window titles, document paths, or input capture."""


def read_applications():
    try:
        from AppKit import NSWorkspace
        import objc

        def identity(app):
            return {"pid": int(app.processIdentifier()), "name": str(app.localizedName() or "Unknown"),
                    "bundle_id": str(app.bundleIdentifier()) if app.bundleIdentifier() else None}

        with objc.autorelease_pool():
            workspace = NSWorkspace.sharedWorkspace()
            front = workspace.frontmostApplication()
            applications = {int(app.processIdentifier()): identity(app) for app in workspace.runningApplications()}
            return identity(front) if front else {}, applications, [] if front else ["foreground_unavailable"]
    except (ImportError, RuntimeError, AttributeError):
        return {}, {}, ["foreground_unavailable"]
