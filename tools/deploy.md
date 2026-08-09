(If anyone stumbles upon this file, it's just some notes for myself because I always forgor stuff)

### One-time GitHub setup

Configure trusted publishing for the release workflow:

* PyPI project `HyFetch`: trust this repository and `.github/workflows/release.yml`
* npm package `neowofetch`: trust this repository and `.github/workflows/release.yml`

No PyPI or npm API token secrets are needed. The publish jobs request GitHub's
OIDC token with `id-token: write`, and the registries exchange that token through
their trusted publishing flows.

### Things to do before deploying

* [ ] Update changelog (`README.md`) and commit changes
* [ ] Run `python -m tools.deploy-release {version}`
* [ ] Watch the `Release` workflow

The local script prepares the release commit and pushes the version tag. By
default it also updates the built-in fastfetch binaries to the latest upstream
release used by Python wheels. Use `--fastfetch-version {version}` to pin a
specific upstream fastfetch release, or `--skip-fastfetch-update` to keep the
current pin.

GitHub Actions creates/completes the GitHub Release, uploads Python artifacts,
publishes to PyPI, and publishes to npm.

If the workflow fails after one stage already published, fix the problem and
rerun it manually with the same release tag. If the fix changes files needed by
the failed stage, set `source_ref` to the branch or commit containing the fix,
and turn off any stages that already completed. The workflow checks PyPI, npm,
and the GitHub Release first, so completed stages are skipped instead of being
published again.
