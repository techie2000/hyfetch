#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import stat
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from packaging import version as pv

from tools.list_distros import generate_help
from tools.reformat_readme import reformat_readme

NEOFETCH_NEW_VERSION = ""
FASTFETCH_RELEASE_API = 'https://api.github.com/repos/fastfetch-cli/fastfetch/releases'
FASTFETCH_ASSETS = [
    'fastfetch-windows-amd64.zip',
    'fastfetch-linux-amd64.zip',
    'fastfetch-linux-aarch64.zip',
    'fastfetch-linux-armv7l.zip',
    'fastfetch-musl-amd64.zip',
    'fastfetch-macos-amd64.zip',
    'fastfetch-macos-aarch64.zip',
]
RELEASE_FILES = [
    'Cargo.lock',
    'Cargo.toml',
    'README.md',
    'docs/hyfetch.1',
    'docs/neofetch.1',
    'hyfetch/__version__.py',
    'neofetch',
    'package.json',
    'tools/build_pkg.sh',
]


def pre_check():
    """
    Check source code status before releasing.
    """
    assert os.path.isfile('./neofetch'), './neofetch doesn\'t exist, you are running this script in the wrong directory'
    assert os.stat('./neofetch').st_mode & stat.S_IEXEC, 'neofetch is not executable'
    assert os.path.islink('./hyfetch/scripts/neowofetch'), 'neowofetch is not a symbolic link'
    assert not subprocess.check_output(['git', 'status', '--porcelain']).strip(), \
        'Please commit or stash all changes before release'

    print('Running shellcheck... (This may take a while)')
    subprocess.check_call(shlex.split('shellcheck neofetch'))


def edit_versions(version: str):
    """
    Edit version numbers in hyfetch/constants.py, package.json, and README.md

    Also edits version number of neofetch, but the neofetch version number is separate.

    :param version: Version to release
    """
    # 1. package.json
    print('Editing package.json...')
    path = Path('package.json')
    content = json.loads(path.read_text())
    cur = pv.parse(content['version'])
    assert cur < pv.parse(version), 'Version did not increase'
    content['version'] = version
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2))

    # 2. hyfetch/constants.py
    print('Editing hyfetch/__version__.py...')
    path = Path('hyfetch/__version__.py')
    content = [f"VERSION = '{version}'" if l.startswith('VERSION = ') else l for l in path.read_text().split('\n')]
    path.write_text('\n'.join(content))

    # 3. Cargo.toml
    print('Editing Cargo.toml...')
    path = Path('Cargo.toml')
    content = path.read_text()
    content = re.sub(r'(?<=^version = ")[^"]+(?="$)', version, content, flags=re.MULTILINE)
    path.write_text(content)

    print('Updating Cargo.lock...')
    subprocess.check_call(['cargo', 'metadata', '--format-version', '1'], stdout=subprocess.DEVNULL)

    # 4. README.md
    print('Editing README.md...')
    path = Path('README.md')
    content = path.read_text()
    changelog_token = '<!-- CHANGELOG STARTS HERE --->'
    changelog_i = content.index(changelog_token) + len(changelog_token)
    content = content[:changelog_i] + f'\n\n### {version}' + content[changelog_i:]
    path.write_text(content)

    # 5. neofetch script
    print('Editing neofetch...')
    path = Path('neofetch')
    lines = path.read_text().replace("\t", "        ").split('\n')
    version_i = next(i for i, l in enumerate(lines) if l.startswith('version='))
    nf = pv.parse(lines[version_i].replace('version=', ''))
    new = pv.parse(version)
    nf = f'{nf.major + new.major - cur.major}.{nf.minor + new.minor - cur.minor}.{nf.micro + new.micro - cur.micro}'
    lines[version_i] = f"version={nf}"
    path.write_text('\n'.join(lines))

    global NEOFETCH_NEW_VERSION
    NEOFETCH_NEW_VERSION = nf


def fetch_fastfetch_release(release: str) -> dict:
    """
    Fetch fastfetch release metadata from GitHub.
    """
    if release == 'latest':
        url = f'{FASTFETCH_RELEASE_API}/latest'
    else:
        tag = urllib.parse.quote(release, safe='')
        url = f'{FASTFETCH_RELEASE_API}/tags/{tag}'

    request = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'hyfetch-release-script',
    })

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404 and release.startswith('v'):
            return fetch_fastfetch_release(release[1:])
        raise


def update_fastfetch_version(release: str) -> str:
    """
    Update the fastfetch binary version embedded in Python wheels.
    """
    print(f'Checking fastfetch {release}...')
    metadata = fetch_fastfetch_release(release)
    tag = metadata['tag_name']
    assets = {asset['name'] for asset in metadata['assets']}
    missing = sorted(set(FASTFETCH_ASSETS) - assets)
    assert not missing, f'Fastfetch {tag} is missing required release assets: {", ".join(missing)}'

    print(f'Editing tools/build_pkg.sh fastfetch version to {tag}...')
    path = Path('tools/build_pkg.sh')
    content = path.read_text()
    content = re.sub(r'(?<=^FASTFETCH_VERSION=")[^"]+(?="$)', tag, content, flags=re.MULTILINE)
    path.write_text(content)
    return tag


def finalize_neofetch():
    """
    Finalize current version
    """
    # 1. Update distro list
    print('Updating distro list in neofetch...')
    path = Path('neofetch')
    content = path.read_text()
    content = re.compile(r'(?<=# Flag:    --ascii_distro\n#\n).*?(?=ascii_distro=)', re.DOTALL)\
        .sub(generate_help(100, '# ') + '\n', content)
    content = re.compile(r"""(?<=Which Distro's ascii art to print\n\n).*?{distro}_small to use them\.""", re.DOTALL)\
        .sub(generate_help(100, ' ' * 32), content)
    path.write_text(content)

    # 2. Regenerate man page
    print('Regenerating neofetch man page...')
    Path('docs/neofetch.1').write_text(subprocess.check_output(['help2man', './neofetch']).decode())
    Path('docs/hyfetch.1').write_text(subprocess.check_output(['help2man', 'cargo run --']).decode())

    # 3. Reformat readme links
    print('Reformatting readme links...')
    reformat_readme()


def post_check():
    """
    Check after changes are made
    """
    print('Running shellcheck... (This may take a while)')
    subprocess.check_call(shlex.split('shellcheck neofetch'))


def create_release(v: str):
    """
    Create release commit and tag
    """
    print('Committing changes...')

    # 1. Add files
    subprocess.check_call(['git', 'add', *RELEASE_FILES])

    # 2. Commit
    subprocess.check_call(['git', 'commit', '-m', f'[U] Release {v}'])

    # 3. Create tag
    subprocess.check_call(['git', 'tag', v])
    subprocess.check_call(['git', 'tag', f'neofetch-{NEOFETCH_NEW_VERSION}'])

    i = input('Please check the commit is correct. Press y to continue or any other key to cancel.')
    if i.lower() != 'y':
        print('Aborting...')
        subprocess.check_call(['git', 'tag', '-d', v])
        subprocess.check_call(['git', 'tag', '-d', f'neofetch-{NEOFETCH_NEW_VERSION}'])
        subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])
        print('Release commit was undone with changes preserved in the index.')
        exit(1)

    # 4. Push
    print('Pushing commits...')
    subprocess.check_call(['git', 'push'])
    subprocess.check_call(['git', 'push', 'origin', v, f'neofetch-{NEOFETCH_NEW_VERSION}'])


def deploy():
    """
    Deploy release to pip and npm
    """
    print('Deploying to pypi...')
    subprocess.check_call(['bash', 'tools/deploy.sh'])
    print('Done!')

    print('Deploying to crates.io...')
    subprocess.check_call(['bash', 'tools/deploy-crate.sh'])
    print('Done!')

    print('Deploying to npm...')
    otp = input('Please provide 2FA OTP for NPM: ')
    subprocess.check_call(['npm', 'publish', '--otp', otp])
    print('Done!')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HyFetch Release Utility')
    parser.add_argument('version', help='Version to release')
    parser.add_argument(
        '--fastfetch-version',
        default='latest',
        help='Fastfetch release tag to embed in Python wheels, or "latest" (default).',
    )
    parser.add_argument(
        '--skip-fastfetch-update',
        action='store_true',
        help='Keep the existing FASTFETCH_VERSION in tools/build_pkg.sh.',
    )
    parser.add_argument(
        '--local-deploy',
        action='store_true',
        help='Publish from this machine after pushing tags. By default, GitHub Actions publishes the release.',
    )

    args = parser.parse_args()

    pre_check()
    edit_versions(args.version)
    if not args.skip_fastfetch_update:
        update_fastfetch_version(args.fastfetch_version)

    finalize_neofetch()
    post_check()
    create_release(args.version)

    if args.local_deploy:
        deploy()
    else:
        print('Release tag pushed. GitHub Actions will create the GitHub Release and publish packages.')
