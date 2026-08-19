# AdaPT Project Page

This folder contains the project page for **AdaPT: Towards Professional Tennis Styles for Humanoid Robots with Adaptive Motion Planning and Tracking**.

## Quick View

For a quick check, open:

```text
index.html
```

Most images and videos are stored locally and should be visible by directly double-clicking `index.html`.

## If Something Does Not Display

Some browsers restrict local `file://` access for interactive WebGL, iframe, JSON, or GLB assets. If any section appears blank or fails to load, serve this folder with a local HTTP server:

```text
python -m http.server 8000
```

Then open:

```text
http://localhost:8000/index.html
```

Run the command from this directory:

```text
adapt.github.io/
```

## Direct Video Access

If the webpage has display issues, the main video assets can be inspected directly under:

```text
static/videos/adapt/
```

Baseline videos are under:

```text
static/videos/adapt/baselines/
```

These files can be opened directly with a local video player.
