"""Verify an explicit source package, or source plus required historical evidence.

The versioned configs/source_package.json manifest works without Git metadata.
Source mode excludes local evidence; evidence mode requires its declared inputs.
Neither mode selects private artifacts or establishes functional/patient validity.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

MANIFEST = 'configs/source_package.json'
FORBIDDEN = {"data/raw", "data/processed", "weights", ".venv", ".venv312", "venv", ".git", "node_modules"}


class IntegrityError(ValueError):
    pass


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_path(root, relative):
    if (not isinstance(relative,str) or not relative or "\\" in relative or
        ":" in relative or "\x00" in relative or
        PureWindowsPath(relative).is_absolute() or PurePosixPath(relative).is_absolute() or
        any(part in {"", ".", ".."} or part.endswith((' ','.')) or
            any(ord(c)<32 or c in '<>"|?*' for c in part) or
            PureWindowsPath(part).is_reserved() for part in relative.split("/"))):
        raise IntegrityError(f"Unsafe manifest path: {relative!r}")
    path = root.joinpath(*relative.split("/"))
    if not path.resolve().is_relative_to(root.resolve()):
        raise IntegrityError(f"Manifest path escapes root: {relative}")
    # A symlink/reparse path is not a selected immutable regular source file.
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction())
           for p in [path, *path.parents] if p != root.parent):
        raise IntegrityError(f"Linked manifest path: {relative}")
    if any(relative.casefold()==f or relative.casefold().startswith(f+'/') for f in FORBIDDEN):
        raise IntegrityError(f"Forbidden package path: {relative}")
    return path


def verify_package(source, destination, required, optional=()):
    """Copy a prehashed source snapshot to an empty isolated directory.

    No success result is returned unless every selected byte and required path
    is verified. The caller owns temporary destination cleanup on failure.
    """
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if destination==source or destination.is_relative_to(source):
        raise IntegrityError('Package destination must be outside source')
    if destination.exists() and any(destination.iterdir()):
        raise IntegrityError('Package destination must be empty')
    required,optional=list(required),list(optional)
    seen=set();snapshot=[];missing_optional=[]
    for is_required, paths in [(True,required),(False,optional)]:
        for relative in paths:
            key=relative.casefold() if isinstance(relative,str) else relative
            if key in seen:raise IntegrityError(f'Duplicate manifest path: {relative}')
            seen.add(key)
            src=safe_path(source,relative);safe_path(destination,relative)
            if not src.is_file():
                if is_required:raise IntegrityError(f'Missing required file: {relative}')
                missing_optional.append(relative);continue
            snapshot.append((relative,is_required,src.stat().st_size,sha256_file(src)))
    destination.mkdir(parents=True,exist_ok=True)
    entries=[]
    for relative,is_required,size,digest in snapshot:
        src=safe_path(source,relative);dst=safe_path(destination,relative)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)
        copied_digest=sha256_file(dst)
        if dst.stat().st_size!=size or copied_digest!=digest or sha256_file(src)!=digest:
            raise IntegrityError(f'Copy/snapshot hash mismatch: {relative}')
        entries.append(dict(file=relative,required=is_required,size_bytes=size,
                            source_sha256=digest,package_sha256=copied_digest))
    actual={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
    if actual!={r[0] for r in snapshot} or not set(required).issubset(actual):
        raise IntegrityError('Incomplete or unexpected package manifest coverage')
    # Recheck all entries after all copies, catching later-copy corruption.
    for entry in entries:
        dst=safe_path(destination,entry['file'])
        if dst.stat().st_size!=entry['size_bytes'] or sha256_file(dst)!=entry['source_sha256']:
            raise IntegrityError(f"Final destination hash mismatch: {entry['file']}")
    return dict(portable_package_version='2.0.0',integrity='PASS',
                total_files_packaged=len(actual),required_files_count=len(required),
                optional_missing=missing_optional,hash_audit=entries)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='New JSON report path; existing files are refused')
    parser.add_argument('--mode',choices=['source','evidence'],default='source')
    parser.add_argument('--root',type=Path,default=ROOT,help='Source checkout or explicitly assembled candidate snapshot')
    args=parser.parse_args(argv)
    try:
        if args.output and args.output.exists():raise IntegrityError(f'Output already exists: {args.output}')
        source=args.root.resolve()
        manifest_path=safe_path(source,MANIFEST)
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if (manifest.get('schema_version')!=1 or any(not isinstance(manifest.get(key),list) or
            any(not isinstance(p,str) for p in manifest[key]) for key in
            ['required_source_files','required_evidence_files','optional_evidence_files'])):
            raise IntegrityError('Invalid source package manifest schema')
        required=list(manifest['required_source_files'])
        if MANIFEST not in required:raise IntegrityError('Source manifest must require itself')
        if any(p.startswith('reports/') for p in required):
            raise IntegrityError('Source requirements cannot include historical/local reports')
        optional=[]
        if args.mode=='evidence':
            required+=manifest['required_evidence_files']
            optional=manifest['optional_evidence_files']
        with tempfile.TemporaryDirectory(prefix='glucotwin_portable_') as temp:
            result=verify_package(source,Path(temp)/'package',required,optional)
        result.update(package_mode=args.mode,manifest_sha256=sha256_file(manifest_path),
                      evidence_selected=args.mode=='evidence')
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
        print(f"Integrity PASS: {result['total_files_packaged']} actual files copied and hashed. Functional checks are separate.")
        return 0
    except (OSError,ValueError) as exc:
        print(f'Integrity FAIL: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
