"""``ontoreview-ui``: a local web UI (NiceGUI) to configure and run builds, exports and checks.

    pip install "ontoreview[ui]"
    ontoreview-ui                     # opens http://127.0.0.1:8765 in your browser

Runs on this machine only (bound to 127.0.0.1 by default); paths are local paths.
"""

from __future__ import annotations

import argparse
import logging
import queue
import sys
import uuid
from pathlib import Path

from . import __version__
from .ui_core import (
    TASKS,
    Settings,
    browse,
    describe_source,
    existing_output,
    forget_run,
    load_history,
    open_in_file_manager,
    record_run,
    run_task,
)

HELP = {
    "robot": "ROBOT runs on this machine: a local `robot`, else Docker (image pulled on first use).",
    "oops": "OOPS! is a web service: the ontology is uploaded to oops.linkeddata.es. "
            "'auto' uses it only when ROBOT cannot run. Choose 'off' for private ontologies.",
}


class _QueueHandler(logging.Handler):
    """Collects log records from worker threads; the page drains the queue on a timer."""

    def __init__(self, q: queue.Queue) -> None:
        super().__init__(logging.INFO)
        self.q = q
        self.setFormatter(logging.Formatter("%(levelname)s  %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.q.put_nowait(self.format(record))
        except Exception:  # noqa: BLE001
            pass


def build_page() -> None:  # noqa: C901 - one page, laid out top to bottom
    from nicegui import app, run, ui

    s = Settings.load()
    logs: queue.Queue[str] = queue.Queue()
    handler = _QueueHandler(logs)
    logging.getLogger("ontoreview").addHandler(handler)
    logging.getLogger("ontoreview").setLevel(logging.INFO)
    ui.context.client.on_disconnect(lambda: logging.getLogger("ontoreview").removeHandler(handler))

    ui.page_title("OntoReview")
    ui.add_css("""
      .ob-card { width: 100%; }
      .ob-step { font-weight: 600; font-size: 1.05rem; }
      .ob-hint { color: #5d5950; font-size: .85rem; }
      body.body--dark .ob-hint { color: #a49e91; }
      .ob-cli { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .8rem; white-space: pre-wrap; word-break: break-all; }
      .ob-log { height: 16rem; font-size: .8rem; }
    """)
    dark = ui.dark_mode(None)
    prior_state: dict = {}
    ready: list[bool] = []  # existing output at the chosen location (see refresh)  # follow the operating system until toggled

    # ------------------------------------------------------------ header
    with ui.header().classes("items-center justify-between px-4"):
        with ui.row().classes("items-baseline gap-3"):
            ui.label("OntoReview").classes("text-xl font-semibold")
            ui.label("Ontology documentation and review").classes("text-sm opacity-80")
        with ui.row().classes("items-center gap-1"):
            ui.label(f"v{__version__}").classes("text-xs opacity-70")
            ui.button(icon="dark_mode", on_click=lambda: dark.set_value(not dark.value)) \
                .props('flat round color=white aria-label="Toggle dark mode"').tooltip("Dark mode")

    # ------------------------------------------------------------ file picker
    def pick(kind: str, on_pick, folders: bool, start: str = "") -> None:
        state = {"path": start or s.source or str(Path.cwd())}
        with ui.dialog() as dlg, ui.card().classes("w-[40rem] max-w-full"):
            ui.label("Choose a folder" if folders and kind == "ontology" else "Choose a file").classes("ob-step")
            path_label = ui.label().classes("ob-cli")
            box = ui.column().classes("w-full gap-0 max-h-[50vh] overflow-auto")

            def show(p: str) -> None:
                lst = browse(p, kind)  # type: ignore[arg-type]
                state["path"] = lst.path
                path_label.text = lst.path
                box.clear()
                with box:
                    if lst.parent:
                        ui.button("..", icon="arrow_upward", on_click=lambda: show(lst.parent)) \
                            .props("flat align=left no-caps").classes("w-full")
                    for d in lst.dirs:
                        ui.button(d, icon="folder", on_click=lambda d=d: show(str(Path(lst.path) / d))) \
                            .props("flat align=left no-caps").classes("w-full")
                    if not folders:
                        for f in lst.files:
                            ui.button(f, icon="description",
                                      on_click=lambda f=f: (on_pick(str(Path(lst.path) / f)), dlg.close())) \
                                .props("flat align=left no-caps").classes("w-full")
                    if not lst.dirs and (folders or not lst.files):
                        ui.label("Nothing here.").classes("ob-hint q-pa-sm")

            show(state["path"])
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                if folders:
                    ui.button("Use this folder", icon="check",
                              on_click=lambda: (on_pick(state["path"]), dlg.close()))
        dlg.open()

    def refresh(*_) -> None:
        if not ready:  # bindings fire while the page is still being built
            return
        source_info.text = describe_source(s.source)
        folder = s.is_folder
        output.props(f'placeholder="{s.default_output()}"')
        per_file_hint.set_visibility(folder)
        cq.set_enabled(not folder)
        prev.set_enabled(not folder)
        site_opts.set_visibility(s.task in ("site", "single"))
        check_opts.set_visibility(s.task == "check")
        eval_opts.set_visibility(s.task in ("site", "single", "check"))
        cli.text = s.cli()
        prior = existing_output(s.output_path())
        existing_row.set_visibility(prior is not None)
        if prior:
            import datetime as _dt
            when = _dt.datetime.fromtimestamp(prior["when"]).strftime("%Y-%m-%d %H:%M")
            what = f"{prior['count']} ontologies" if prior["kind"] == "folder" else "output"
            existing_info.text = f"Previous {what} here from {when}; running again updates it."
        prior_state.clear()
        prior_state.update(prior or {})

    # ------------------------------------------------------------ form
    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        with ui.row().classes("w-full gap-4 items-start no-wrap max-md:flex-wrap"):
            with ui.column().classes("gap-4 grow basis-1/2 min-w-0 w-full"):
                with ui.card().classes("ob-card"):
                    ui.label("1. What to document").classes("ob-step")
                    src = ui.input("Ontology file, URL or folder", on_change=refresh).bind_value(s, "source") \
                        .mark("source").classes("w-full").props('clearable aria-describedby="source-info"')
                    with ui.row().classes("gap-2"):
                        ui.button("File…", icon="description",
                                  on_click=lambda: pick("ontology", lambda p: src.set_value(p), False)).props("outline")
                        ui.button("Folder…", icon="folder",
                                  on_click=lambda: pick("ontology", lambda p: src.set_value(p), True)).props("outline")
                    source_info = ui.label().classes("ob-hint").props('id="source-info" aria-live="polite"')

                with ui.card().classes("ob-card"):
                    ui.label("2. What to produce").classes("ob-step")
                    ui.toggle(TASKS, on_change=refresh).bind_value(s, "task").props("no-caps spread") \
                        .classes("w-full flex-wrap")
                    ui.label("For a folder, every ontology gets its own sub-folder, plus an index page.") \
                        .classes("ob-hint")

                with ui.card().classes("ob-card"):
                    ui.label("3. Where").classes("ob-step")
                    output = ui.input("Output folder or file (leave empty for the default)", on_change=refresh) \
                        .bind_value(s, "output").mark("output").classes("w-full").props("clearable")
                    ui.button("Choose…", icon="folder_open",
                              on_click=lambda: pick("any", lambda p: output.set_value(p), True,
                                                    s.output or str(s.output_path().parent))).props("outline")
                    with ui.row().classes("w-full items-center gap-2") as existing_row:
                        existing_info = ui.label().classes("ob-hint grow").props('aria-live="polite"')
                        ui.button("Open", icon="open_in_new", on_click=lambda: prior_state.get("index") and
                                  ui.navigate.to(link_for(prior_state["index"]), new_tab=True)).props("flat dense no-caps")
                        ui.button("Open folder", icon="folder_open",
                                  on_click=lambda: reveal(str(s.output_path()))).props("flat dense no-caps")

                with ui.expansion("Options", icon="tune").classes("ob-card").props("header-class=ob-step"):
                    with ui.column().classes("w-full gap-3") as site_opts:
                        ui.toggle({"single": "One page", "multi": "One page per section"}, on_change=refresh) \
                            .bind_value(s, "layout").props("no-caps")
                        ui.input("Languages (comma-separated, first is default)", on_change=refresh) \
                            .bind_value(s, "languages").classes("w-full")
                        ui.input("Public URL (base_url)", on_change=refresh).bind_value(s, "base_url").classes("w-full")
                        with ui.row().classes("gap-4"):
                            ui.switch("Load owl:imports", on_change=refresh).bind_value(s, "load_imports")
                            ui.switch("Individuals", on_change=refresh).bind_value(s, "include_individuals")
                            ui.switch("Inferred superclasses (needs owlrl)", on_change=refresh).bind_value(s, "reason")
                    per_file_hint = ui.label("Competency questions and the previous version apply to a single "
                                             "ontology; for a folder, put them in an ontoreview.toml next to it.") \
                        .classes("ob-hint")
                    with ui.row().classes("w-full items-end no-wrap gap-2"):
                        cq = ui.input("Competency questions file(s)", on_change=refresh) \
                            .bind_value(s, "competency_questions").classes("grow")
                        ui.button(icon="attach_file", on_click=lambda: pick(
                            "cq", lambda p: cq.set_value(", ".join(x for x in (s.competency_questions, p) if x)), False)) \
                            .props('flat round aria-label="Choose competency questions file"')
                    with ui.row().classes("w-full items-end no-wrap gap-2"):
                        prev = ui.input("Previous version (for the changelog)", on_change=refresh) \
                            .bind_value(s, "previous_version").classes("grow")
                        ui.button(icon="attach_file", on_click=lambda: pick(
                            "ontology", lambda p: prev.set_value(p), False)) \
                            .props('flat round aria-label="Choose previous version"')
                    with ui.column().classes("w-full gap-1") as eval_opts:
                        with ui.row().classes("gap-4 items-center"):
                            ui.select({"auto": "auto", "on": "on", "off": "off"}, label="ROBOT", on_change=refresh) \
                                .bind_value(s, "robot").classes("w-28")
                            ui.select({"auto": "auto (fallback)", "on": "always", "off": "never"},
                                      label="OOPS! web service", on_change=refresh).bind_value(s, "oops").classes("w-44")
                        ui.label(HELP["robot"]).classes("ob-hint")
                        ui.label(HELP["oops"]).classes("ob-hint")
                    with ui.row() as check_opts:
                        ui.select({"error": "errors", "warning": "warnings", "info": "suggestions", "never": "never"},
                                  label="Fail on", on_change=refresh).bind_value(s, "fail_on").classes("w-40")

                with ui.row().classes("gap-2"):
                    run_btn = ui.button("Run", icon="play_arrow", on_click=lambda: start()).mark("run")
                    ui.button("Save as ontoreview.toml", icon="save", on_click=lambda: save_toml()).props("outline")
                    ui.button("Load ontoreview.toml", icon="upload_file",
                              on_click=lambda: pick("toml", load_toml, False)).props("outline")

            # -------------------------------------------------------- results
            with ui.column().classes("gap-4 grow basis-1/2 min-w-0 w-full"):
                with ui.card().classes("ob-card"):
                    ui.label("Results").classes("ob-step")
                    progress = ui.linear_progress(show_value=False).props("indeterminate")
                    progress.set_visibility(False)
                    status = ui.label("Nothing run yet.").classes("ob-hint").props('aria-live="polite"')
                    results = ui.column().classes("w-full gap-1")
                with ui.card().classes("ob-card"):
                    ui.label("Log").classes("ob-step")
                    log_view = ui.log(max_lines=500).classes("w-full ob-log")
                with ui.card().classes("ob-card"):
                    ui.label("Same thing on the command line").classes("ob-step")
                    cli = ui.label().classes("ob-cli")

        # ---------------------------------------------------------- history
        with ui.card().classes("ob-card"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Previous runs").classes("ob-step")
                hist_count = ui.label().classes("ob-hint").props('aria-live="polite"')
            with ui.row().classes("w-full items-center gap-3"):
                hist_text = ui.input("Filter by source or output", on_change=lambda: history.refresh()) \
                    .props("clearable dense").classes("grow min-w-[14rem]")
                hist_task = ui.select({"all": "All tasks", **TASKS}, value="all", label="Task",
                                      on_change=lambda: history.refresh()).props("dense").classes("w-44")
                hist_exist = ui.switch("Only runs whose output still exists", value=True,
                                       on_change=lambda: history.refresh())
            history_box = ui.column().classes("w-full gap-0")

    def drain() -> None:
        while True:
            try:
                log_view.push(logs.get_nowait())
            except queue.Empty:
                return

    ui.timer(0.3, drain)

    def link_for(path: str) -> str | None:
        """Serve the output folder so results open in a new browser tab."""
        if not path:
            return None
        p = Path(path)
        root = s.output_path() if s.output_path().is_dir() else p.parent
        try:
            rel = p.resolve().relative_to(root.resolve())
        except ValueError:
            root, rel = p.parent, Path(p.name)
        mount = f"/out/{uuid.uuid4().hex[:10]}"
        app.add_static_files(mount, root)
        return f"{mount}/{rel.as_posix()}"

    def show_results(res) -> None:
        results.clear()
        with results:
            if res.index:
                url = link_for(res.index)
                with ui.row().classes("items-center gap-2"):
                    ui.button("Open", icon="open_in_new", on_click=lambda u=url: ui.navigate.to(u, new_tab=True))
                    ui.button("Open folder", icon="folder_open",
                              on_click=lambda p=str(res.output): reveal(p)).props("outline")
                    ui.label(res.index).classes("ob-cli")
            elif res.output:
                ui.button("Open folder", icon="folder_open",
                          on_click=lambda p=str(res.output): reveal(p)).props("outline")
            cols = [
                {"name": "name", "label": "Ontology", "field": "name", "align": "left"},
                {"name": "terms", "label": "Terms", "field": "terms"},
                {"name": "errors", "label": "Errors", "field": "errors"},
                {"name": "warnings", "label": "Warnings", "field": "warnings"},
                {"name": "external", "label": "ROBOT / OOPS!", "field": "external", "align": "left"},
                {"name": "open", "label": "", "field": "open"},
            ]
            rows = []
            for i, r in enumerate(res.rows):
                rows.append({"id": i, "name": r.title or r.name, "source": r.name, "terms": r.terms if not r.problem else "",
                             "errors": r.errors if not r.problem else "", "warnings": r.warnings if not r.problem else "",
                             "external": r.problem or r.external, "open": link_for(r.output) if r.output else "",
                             "path": r.output, "problem": bool(r.problem)})
            table = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full").props("flat dense wrap-cells")
            table.add_slot("body-cell-name", r'''
                <q-td :props="props"><div :class="props.row.problem ? 'text-negative' : ''">{{ props.row.name }}</div>
                <div class="ob-hint">{{ props.row.source }}</div></q-td>''')
            table.add_slot("body-cell-open", r'''
                <q-td :props="props" class="text-no-wrap">
                  <a v-if="props.value" :href="props.value" target="_blank" rel="noopener">open</a>
                  <q-btn v-if="props.row.path" flat dense round size="sm" icon="folder_open"
                         :aria-label="'Open folder of ' + props.row.name"
                         @click="() => $parent.$emit('reveal', props.row.path)" />
                </q-td>''')
            table.on("reveal", lambda e: reveal(e.args))
            for sk in res.skipped:
                ui.label(f"Skipped (unsupported format): {sk}").classes("ob-hint")

    async def start() -> None:
        problems = s.validate()
        if problems:
            for p in problems:
                ui.notify(p, type="warning")
            return
        s.save()
        run_btn.disable()
        progress.set_visibility(True)
        status.text = f"Running: {TASKS[s.task]}…"
        log_view.push(f"$ {s.cli()}")
        try:
            res = await run.io_bound(run_task, s)
        except Exception as e:  # noqa: BLE001
            drain()
            status.text = f"Failed: {e}"
            ui.notify(f"Failed: {e}", type="negative", multi_line=True)
            record_run(s, None, str(e))
            history.refresh()
        else:
            record_run(s, res)
            history.refresh()
            drain()
            failed = len(res.rows) - res.ok
            status.text = (f"Done in {res.seconds:.1f}s: {res.ok} of {len(res.rows)} succeeded"
                           + (f", {failed} failed." if failed else ".") + f" Output: {res.output}")
            show_results(res)
            ui.notify(status.text, type="positive" if not failed else "warning")
        finally:
            run_btn.enable()
            progress.set_visibility(False)

    def save_toml() -> None:
        problems = [p for p in s.validate() if p.startswith("Choose")]
        if problems:
            ui.notify(problems[0], type="warning")
            return
        base = s.source_path if s.is_folder else (s.source_path.parent if s.source_path else Path.cwd())
        target = base / "ontoreview.toml"
        if target.exists():
            with ui.dialog() as d, ui.card():
                ui.label(f"{target} already exists. Replace it?")
                with ui.row().classes("justify-end w-full"):
                    ui.button("Cancel", on_click=d.close).props("flat")
                    ui.button("Replace", color="negative", on_click=lambda: (write(target), d.close()))
            d.open()
        else:
            write(target)

    def write(target: Path) -> None:
        target.write_text(s.to_toml(), "utf-8")
        ui.notify(f"Saved {target}", type="positive")

    def load_toml(path: str) -> None:
        try:
            loaded = Settings.from_toml(path)
        except Exception as e:  # noqa: BLE001
            ui.notify(f"Could not read {path}: {e}", type="negative")
            return
        for k, v in vars(loaded).items():
            setattr(s, k, v)
        refresh()
        ui.notify(f"Loaded {path}", type="positive")

    def reveal(path: str) -> None:
        try:
            open_in_file_manager(path)
        except Exception as e:  # noqa: BLE001
            ui.notify(str(e), type="warning")

    def reuse(entry) -> None:
        loaded = Settings(**{k: v for k, v in entry.settings.items() if k in vars(Settings())})
        for k, v in vars(loaded).items():
            setattr(s, k, v)
        refresh()
        ui.notify("Settings from that run loaded. Press Run to run it again.", type="info")

    @ui.refreshable
    def history() -> None:
        entries = load_history()
        shown = [e for e in entries if e.matches(hist_text.value or "", hist_task.value)
                 and (e.exists or not hist_exist.value)]
        hist_count.text = f"{len(shown)} of {len(entries)} shown"
        if not shown:
            ui.label("No runs match the filter." if entries else "No runs yet. Runs you start appear here.") \
                .classes("ob-hint q-pa-sm")
        for e in shown[:100]:
            import datetime as _dt
            when = _dt.datetime.fromtimestamp(e.when).strftime("%Y-%m-%d %H:%M")
            with ui.row().classes("w-full items-center no-wrap gap-3 py-2 border-b border-gray-500/20"):
                with ui.column().classes("gap-0 grow min-w-0"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(TASKS.get(e.task, e.task)).classes("font-medium")
                        ui.label(when).classes("ob-hint")
                        if e.failed:
                            ui.badge("failed", color="negative")
                        elif not e.exists:
                            ui.badge("output removed", color="grey")
                        else:
                            ui.label(f"{e.ok}/{e.total} ok · {e.errors} errors · {e.warnings} warnings · "
                                     f"{e.seconds:.1f}s").classes("ob-hint")
                    ui.label(e.source).classes("ob-cli")
                    ui.label(f"→ {e.output}").classes("ob-cli opacity-70")
                with ui.row().classes("gap-0 no-wrap"):
                    if e.index and Path(e.index).exists():
                        ui.button(icon="open_in_new", on_click=lambda i=e.index: ui.navigate.to(link_for(i), new_tab=True)) \
                            .props('flat round aria-label="Open result"').tooltip("Open")
                    if e.exists:
                        ui.button(icon="folder_open", on_click=lambda o=e.output: reveal(o)) \
                            .props('flat round aria-label="Open folder"').tooltip("Open folder")
                    ui.button(icon="replay", on_click=lambda e=e: reuse(e)) \
                        .props('flat round aria-label="Use these settings"').tooltip("Use these settings")
                    ui.button(icon="delete_outline", on_click=lambda i=e.id: (forget_run(i), history.refresh())) \
                        .props('flat round aria-label="Remove from history"').tooltip("Remove from history (files are kept)")

    with history_box:
        history()
    ready.append(True)
    refresh()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ontoreview-ui", description="OntoReview local web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1, this machine only).")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    parser.add_argument("--native", action="store_true", help="Open in a desktop window (needs pywebview).")
    args = parser.parse_args(argv)
    try:
        from nicegui import ui
    except ImportError:
        msg = ("ontoreview-ui needs NiceGUI (Python 3.11+). Install it with:\n"
               '    pip install "ontoreview[ui]"')
        if sys.version_info < (3, 11):
            msg += f"\nThis Python is {sys.version.split()[0]}; NiceGUI 4 requires 3.11 or newer."
        print(msg, file=sys.stderr)
        raise SystemExit(1) from None
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("Warning: the UI can read and write files on this machine; binding to "
              f"{args.host} exposes that to your network.", file=sys.stderr)
    ui.run(build_page, host=args.host, port=args.port, title="OntoReview", reload=False,
           show=not args.no_browser, native=args.native, favicon="📘", show_welcome_message=True,
           dark=None)


if __name__ in {"__main__", "__mp_main__"}:
    main()
