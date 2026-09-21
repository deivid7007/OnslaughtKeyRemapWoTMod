"""
build_wotmod.py

Zips res/ + meta.xml into a .wotmod, writing every entry with a full
local header (real crc32/sizes, no streamed "data descriptor").

Usage:
    python build_wotmod.py

Options:
    --root DIR    Project root containing meta.xml and res/ (default:
                   this script's own directory)
    --out PATH    Output .wotmod path (default: <root>/<id>_<version>.wotmod,
                   read from meta.xml)
"""
import argparse
import datetime
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


def read_meta(meta_path):
    root = ET.parse(meta_path).getroot()
    mod_id = root.findtext('id')
    version = root.findtext('version')
    if not mod_id or not version:
        raise ValueError('meta.xml is missing <id> or <version>: %s' % meta_path)
    return mod_id, version


def _iter_res_entries(res_dir):
    dirs = []
    files = []
    for dirpath, dirnames, filenames in os.walk(res_dir):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, res_dir)
        dirs.append(rel_dir)
        for name in sorted(filenames):
            files.append(os.path.join(rel_dir, name))
    return sorted(dirs), sorted(files)


def _arcname(rel_path):
    parts = [p for p in rel_path.replace('\\', '/').split('/') if p not in ('', '.')]
    return 'res/' + '/'.join(parts)


_MOD_FILE_RE = re.compile(r'^mod_(.+)\.pyc?$')


def _validate_mod_filenames(res_dir, rel_files):
    mods_suffix = os.path.join('scripts', 'client', 'gui', 'mods')
    for rel_file in rel_files:
        rel_dir = os.path.dirname(rel_file)
        if not rel_dir.replace('/', os.sep).endswith(mods_suffix):
            continue
        name = os.path.basename(rel_file)
        if not name.endswith(('.py', '.pyc')):
            continue

        if not name.startswith('mod_'):
            raise ValueError(
                "%s does not start with 'mod_'. The client's loader "
                "(_isValidMOD in gui/mods/__init__.py) only picks up files "
                "named 'mod_*.py'/'mod_*.pyc' under this folder -- anything "
                "else is silently skipped, no warning, no error, it just "
                "never loads. Rename it with a 'mod_' prefix." % rel_file
            )

        match = _MOD_FILE_RE.match(name)
        if match and '.' in match.group(1):
            raise ValueError(
                "%s has a dot in its name besides the extension. The client's "
                "loader turns 'mod_X.pyc' into the Python module name "
                "'gui.mods.mod_X' by just stripping '.pyc' -- any interior dot "
                "becomes an invalid package separator and the mod fails to "
                "import (ImportError: No module named ...). Rename it without "
                "the extra dot (e.g. underscore instead)." % rel_file
            )


def build(root_dir, out_path):
    meta_path = os.path.join(root_dir, 'meta.xml')
    res_dir = os.path.join(root_dir, 'res')
    if not os.path.isfile(meta_path):
        raise IOError('meta.xml not found: %s' % meta_path)
    if not os.path.isdir(res_dir):
        raise IOError('res/ folder not found: %s' % res_dir)

    mod_id, version = read_meta(meta_path)
    if out_path is None:
        out_path = os.path.join(root_dir, '%s_%s.wotmod' % (mod_id, version))

    now = tuple(datetime.datetime.now().timetuple())[:6]
    rel_dirs, rel_files = _iter_res_entries(res_dir)
    _validate_mod_filenames(res_dir, rel_files)

    zf = zipfile.ZipFile(out_path, 'w', zipfile.ZIP_STORED)
    try:
        info = zipfile.ZipInfo('meta.xml', now)
        info.external_attr = 0o644 << 16
        meta_fh = open(meta_path, 'rb')
        try:
            zf.writestr(info, meta_fh.read())
        finally:
            meta_fh.close()

        info = zipfile.ZipInfo('res/', now)
        zf.writestr(info, '')
        for rel_dir in rel_dirs:
            if rel_dir == '.':
                continue
            info = zipfile.ZipInfo(_arcname(rel_dir) + '/', now)
            zf.writestr(info, '')

        for rel_file in rel_files:
            info = zipfile.ZipInfo(_arcname(rel_file), now)
            info.external_attr = 0o644 << 16
            fh = open(os.path.join(res_dir, rel_file), 'rb')
            try:
                zf.writestr(info, fh.read())
            finally:
                fh.close()
    finally:
        zf.close()

    return out_path, len(rel_files)


def verify(out_path):
    z = zipfile.ZipFile(out_path)
    try:
        ok = True
        for info in z.infolist():
            if info.flag_bits & 0x08:
                ok = False
                print('WARNING: streamed entry (data descriptor) in %s -- this will fail to load!' % info.filename)
        return ok
    finally:
        z.close()


def main():
    parser = argparse.ArgumentParser(description='Package res/ + meta.xml into a .wotmod.')
    parser.add_argument('--root', default=None, help="Project root containing meta.xml and res/ (default: this script's directory)")
    parser.add_argument('--out', default=None, help='Output .wotmod path (default: <root>/<id>_<version>.wotmod)')
    args = parser.parse_args()

    root_dir = args.root if args.root else os.path.dirname(os.path.abspath(__file__))
    out_path = args.out if args.out else None

    try:
        out_path, file_count = build(root_dir, out_path)
    except Exception as e:
        print('Build failed: %s' % e)
        sys.exit(1)

    ok = verify(out_path)
    print('Built %s (%d file(s) from res/)' % (out_path, file_count))
    print('Zip framing OK -- no streamed entries.' if ok else 'Zip framing INVALID -- see warnings above.')


if __name__ == '__main__':
    main()
