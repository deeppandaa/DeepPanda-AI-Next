# Executable packaging acceptance example

Handwritten validation fixture, not evidence of autonomous model coding.
app.py is a finite CLI sum example. Use --self-test for its launch check.
Build dependency: pyinstaller==6.16.0, installed only in the project environment.
Run project_package with entrypoint app.py and smoke_arguments ["--self-test"].
Distribute the whole dist/exe_smoke_demo directory, not the exe alone.
Review generated dependencies.json and bundled third-party licenses before redistribution.
