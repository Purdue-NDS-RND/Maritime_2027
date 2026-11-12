"""Read supplied rosbag2 SQLite splits without changing or reindexing the input."""
from contextlib import ExitStack, closing
from collections import Counter
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
    counts = Counter()
    file_stats = {}
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
            count, first, last = connection.execute(
                "SELECT COUNT(*),MIN(timestamp),MAX(timestamp) FROM messages").fetchone()
            file_stats[str(file.relative_to(metadata.parent))] = dict(
                message_count=count, start_ns=first, duration_ns=last-first if count else 0)
            counts.update({name: number for name, number in connection.execute(
                "SELECT t.name,COUNT(m.id) FROM topics t LEFT JOIN messages m ON t.id=m.topic_id GROUP BY t.id")})
            if sum(number for _, number in connection.execute(
                "SELECT topic_id,COUNT(*) FROM messages WHERE topic_id IN (SELECT id FROM topics) GROUP BY topic_id")) != count:
                raise Unavailable("bag_message_topic_missing")
        sources.append(dict(name=file.name, path=str(file), bytes=file.stat().st_size,
                            sha256=digest.hexdigest()))
    listed = set(declared.get("relative_file_paths", [])) if declared else set()
    supplied = {str(p.relative_to(metadata.parent)) for p in files}
    all_supplied = bool(declared) and listed == supplied
    checks = metadata_checks(declared, file_stats, types, counts) if all_supplied else {}
    verified = bool(checks) and all(value is True for value in checks.values())
    provenance = dict(files=sources, metadata_present=metadata.is_file(),
                      metadata_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest() if declared else None,
                      all_declared_splits_supplied=all_supplied,
                      metadata_consistency_checks=checks, metadata_consistency_verified=verified,
                      archive_completeness_verified=all_supplied and verified,
                      archive_scope="Declared files/counts/receive times only; not lossless sensor delivery or physical validity.")
    return files, types, provenance


def metadata_checks(declared, file_stats, types, counts):
    """Cross-check a complete manifest against the actual database, never infer extra frames."""
    number = sum(f["message_count"] for f in file_stats.values())
    nonempty = [f for f in file_stats.values() if f["message_count"]]
    start = min(f["start_ns"] for f in nonempty) if nonempty else None
    end = max(f["start_ns"]+f["duration_ns"] for f in nonempty) if nonempty else None
    checks = dict(message_count=declared["message_count"] == number if "message_count" in declared else None,
        starting_time=declared["starting_time"]["nanoseconds_since_epoch"] == start
            if "starting_time" in declared and nonempty else None,
        duration=declared["duration"]["nanoseconds"] == end-start
            if "duration" in declared and nonempty else None,
        topics=None, files=None)
    if "topics_with_message_count" in declared:
        items = declared["topics_with_message_count"]
        expected = {item["topic_metadata"]["name"]: (item["topic_metadata"]["type"],
                    item["topic_metadata"]["serialization_format"], item["message_count"]) for item in items}
        actual = {name: (kind, "cdr", counts[name]) for name, kind in types.items()}
        checks["topics"] = len(expected) == len(items) and expected == actual
    if "files" in declared:
        items = declared["files"]
        expected = {item["path"]: dict(message_count=item["message_count"],
            start_ns=item["starting_time"]["nanoseconds_since_epoch"], duration_ns=item["duration"]["nanoseconds"])
            for item in items}
        checks["files"] = len(expected) == len(items) and expected == file_stats
    failed = [name for name, passed in checks.items() if passed is False]
    if failed:
        raise Unavailable("bag_metadata_mismatch:" + ",".join(failed))
    return checks


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
