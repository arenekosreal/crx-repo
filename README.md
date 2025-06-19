# Crx Repo

Download Chrom(e|ium) extensions from various sources and serve a update manifest.

[![Test, build and create releases.](/../../actions/workflows/ci.yaml/badge.svg)](/../../actions/workflows/ci.yaml)

## Supported sources

- Chrome Web Store

## Usage

1. Get wheel from [Release](/../../releases) or [build](#build) it yourself.
2. Install the wheel in your system.
3. Run `crx-repo` to know how to use the cli.

## Build

1. Prepare uv: See [here](https://docs.astral.sh/uv/getting-started/installation/) for more info.

   We recommend using your package manager like `winget`, `apt-get`, `brew`, `pacman` or `dnf` to install it.
   This will install uv with managed.

2. Build wheel: Run `uv build` in the repository.

3. Get wheel: You can find wheel at `./dist` folder.

## Optional dependencies

> [!TIP]
> You can always install all optional dependencies with extra `all`.

- uvloop

   High performance async event loop provider. Install with extra `uvloop`.

- lxml

   Support pretty print xml. Install with extra `lxml`.

## What is update manifest

See https://developer.chrome.com/docs/extensions/how-to/distribute/host-on-linux#update_manifest for more info.
