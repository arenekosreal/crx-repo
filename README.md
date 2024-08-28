# Crx Repo

Download Chrom(e|ium) extensions from Chrome Web Store and serve a update manifest.

## Usage

1. Get wheel from [Release](https://github.com/arenekosreal/crx-repo/releases) or build it yourself.
2. Install the wheel in your system.
3. Run `crx-repo` to know how to use the cli.

## Build

1. Prepare pdm: See [here](https://pdm-project.org/en/latest/#installation) for more info.

2. Build wheel: Run `pdm build` in the repository.

3. Get wheel: You can find wheel at `./dist` folder.



## What is update manifest

See https://developer.chrome.com/docs/extensions/how-to/distribute/host-on-linux#update_manifest for more info.
