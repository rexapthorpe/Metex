"""Checksum-verified copy to persistent storage; dry-run by default, never delete."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''): result.update(block)
    return result.hexdigest()


def copy_tree(source,destination,apply=False):
    source=Path(source).resolve(); destination=Path(destination).resolve()
    if destination==source or source in destination.parents:
        raise ValueError('Destination must be outside the source tree')
    count=0
    if not source.exists(): return count
    for path in source.rglob('*'):
        if path.is_symlink(): raise ValueError('Symlink encountered; review storage source')
        if not path.is_file(): continue
        target=destination/path.relative_to(source)
        if target.exists():
            if target.is_symlink() or not target.is_file() or digest(path)!=digest(target):
                raise ValueError('Destination conflict; no existing file overwritten')
            continue
        if apply:
            target.parent.mkdir(parents=True,exist_ok=True)
            if any(parent.is_symlink() for parent in target.parents): raise ValueError('Symlink destination')
            with target.open('xb') as output,path.open('rb') as original: shutil.copyfileobj(original,output)
            if digest(path)!=digest(target): raise RuntimeError('Copied file checksum mismatch')
        count+=1
    return count


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    destination=Path(args.destination)
    public=copy_tree(root/'static/uploads',destination/'public',args.apply)
    private=copy_tree(root/'data/uploads/reports',destination/'private/reports',args.apply)
    if args.apply and (destination/'private').exists(): os.chmod(destination/'private',0o700)
    print(f"{'Copied and verified' if args.apply else 'Would copy'} {public} public and {private} private files; source retained")


if __name__=='__main__': main()
