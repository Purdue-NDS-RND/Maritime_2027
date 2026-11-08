"""Read supplied rosbag2 SQLite splits without changing or reindexing the input."""
from contextlib import ExitStack, closing
import hashlib
import heapq
from pathlib import Path
import sqlite3

import yaml

from ..validation import Unavailable


def bag_storage(bag, storage_id=None):
    path = Path(bag)
    metadata = path / "metadata.yaml" if path.is_dir() else path.parent / "metadata.yaml"
    if storage_id is not None:
        return storage_id
    if metadata.is_file():
        return yaml.safe_load(metadata.read_text())["rosbag2_bagfile_information"]["storage_identifier"]
    if path.suffix == ".db3" or (path.is_dir() and any(path.glob("*.db3"))):
        return "sqlite3"
    raise Unavailable("bag_storage_unknown: supply complete bag metadata or --storage-id")


def sqlite_sources(bag):
    path = Path(bag).resolve()
    metadata = path / "metadata.yaml" if path.is_dir() else path.parent / "metadata.yaml"
    declared = None
    if metadata.is_file():
        declared = yaml.safe_load(metadata.read_text())["rosbag2_bagfile_information"]
        if declared.get("compression_mode", "NONE").lower() not in ("", "none"):
            raise Unavailable("compressed_sqlite_requires_native_ros_reader")
    if path.is_file() and path.suffix == ".db3":
        files = [path]
    elif path.is_dir():
        if declared is not None:
            files = [(path / name).resolve() for name in declared["relative_file_paths"]]
            if any(not file.is_relative_to(path) for file in files):
                raise Unavailable("bag_split_outside_directory")
        else:
            files = sorted(path.glob("*.db3"))
    else:
        raise Unavailable("bag_input_missing")
    if not files or len(set(files)) != len(files) or any(not p.is_file() for p in files):
        raise Unavailable("bag_split_missing_or_duplicated")
    sources = []
    types = {}
    for file in files:
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        with closing(sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise Unavailable("bag_database_integrity_failed")
            for name, kind, serialization in connection.execute("SELECT name,type,serialization_format FROM topics"):
                if serialization != "cdr" or (name in types and types[name] != kind):
                    raise Unavailable("bag_topic_type_or_serialization_mismatch")
                types[name] = kind
        sources.append(dict(name=file.name, path=str(file), bytes=file.stat().st_size,
                            sha256=digest.hexdigest()))
    listed = set(declared.get("relative_file_paths", [])) if declared else set()
    supplied = {str(p.relative_to(metadata.parent)) for p in files}
    provenance = dict(files=sources, metadata_present=metadata.is_file(),
                      all_declared_splits_supplied=bool(declared) and listed == supplied,
                      archive_completeness_verified=False)
    return files, types, provenance


def sqlite_records(files):
    """Merge independently ordered splits; do not assume topic IDs match across splits."""
    with ExitStack() as stack:
        streams = []
        for file in files:
            connection = sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)
            stack.callback(connection.close)
            streams.append(connection.execute(
                "SELECT t.name,m.data,m.timestamp FROM messages m JOIN topics t ON t.id=m.topic_id "
                "ORDER BY m.timestamp,m.id"))
        yield from heapq.merge(*streams, key=lambda item: item[2])


def native_records(bag, storage_id):
    try:
        import rosbag2_py
    except ImportError as exc:
        raise Unavailable("bag_reader_unavailable: source compatible ROS 2") from exc
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage_id),
                rosbag2_py.ConverterOptions("", ""))
    types = {item.name: item.type for item in reader.get_all_topics_and_types()}

    def records():
        while reader.has_next():
            yield reader.read_next()

    return types, records()


def native_decoder():
    try:
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise Unavailable("bag_decode_unavailable: source compatible ROS 2, or use --counts-only") from exc
    classes = {}

    def decode(raw, kind):
        if kind not in classes:
            classes[kind] = get_message(kind)
        return deserialize_message(raw, classes[kind])

    return decode
