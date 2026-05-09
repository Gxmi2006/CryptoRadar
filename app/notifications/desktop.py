from __future__ import annotations


class DesktopNotifier:
    def send(self, title: str, message: str) -> bool:
        try:
            from plyer import notification

            notification.notify(title=title, message=message, timeout=8)
            return True
        except Exception:
            return False
