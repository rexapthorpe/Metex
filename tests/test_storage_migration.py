from scripts.migrate_upload_storage import copy_tree
import pytest


def test_copy_is_verified_idempotent_and_never_deletes_source(tmp_path):
    source=tmp_path/'old'; source.mkdir(); (source/'photo.jpg').write_bytes(b'photo')
    destination=tmp_path/'persistent'
    assert copy_tree(source,destination)==1 and not destination.exists()
    assert copy_tree(source,destination,True)==1
    assert (destination/'photo.jpg').read_bytes()==b'photo'
    assert (source/'photo.jpg').exists()
    assert copy_tree(source,destination,True)==0
    (destination/'photo.jpg').write_bytes(b'conflicting')
    with pytest.raises(ValueError): copy_tree(source,destination,True)
    assert (destination/'photo.jpg').read_bytes()==b'conflicting'


def test_copy_rejects_symlink_and_nested_destination(tmp_path):
    source=tmp_path/'old'; source.mkdir(); (source/'link').symlink_to(tmp_path/'other')
    with pytest.raises(ValueError): copy_tree(source,tmp_path/'persistent',True)
    with pytest.raises(ValueError): copy_tree(source,source/'nested',True)
