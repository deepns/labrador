"""Keep the index fresh: re-index files a couple of seconds after they stop changing."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from .extractors import file_type


def watch(ix, debounce: float = 2.0):
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    pending: dict[str, float] = {}
    lock = threading.Lock()

    class H(FileSystemEventHandler):
        def on_any_event(self, ev):
            if ev.is_directory:
                return
            for path in {getattr(ev, "src_path", None), getattr(ev, "dest_path", None)} - {None, ""}:
                if file_type(Path(path)) and "/." not in path:
                    with lock:
                        pending[path] = time.time()

    obs = Observer()
    obs.schedule(H(), str(ix.root), recursive=True)
    obs.start()
    print(f"Watching {ix.root}  (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(0.5)
            now = time.time()
            with lock:
                ready = [p for p, t in pending.items() if now - t >= debounce]
                for p in ready:
                    pending.pop(p)
            for p in ready:
                path = Path(p)
                if path.exists():
                    n, err = ix.index_file(path)
                    print(f"  indexed {path.name}: {n} units" + (f" ({err})" if err else ""))
                else:
                    ix.store.remove_file(p)
                    print(f"  removed {path.name}")
    except KeyboardInterrupt:
        pass
    finally:
        obs.stop()
        obs.join()
