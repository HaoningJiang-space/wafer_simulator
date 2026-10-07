"""Strict framing around the pinned upstream Chakra protobuf schema.

The upstream generated classes own field interpretation. This wrapper differs
from protolib.decodeMessage only in its completion checks: a partial prefix or
payload is an error, never an apparently successful end of the workload.
"""


def read_frame(stream, message_class, *, max_bytes=64 * 1024 * 1024):
    """Read one varint32-delimited protobuf; return None only at clean EOF."""
    offset = stream.tell()
    size = 0
    for index in range(5):
        byte = stream.read(1)
        if not byte:
            if index == 0:
                return None
            raise ValueError(f"Truncated Chakra length at byte {offset}")
        value = byte[0]
        if index == 4 and value > 15:
            raise ValueError(f"Chakra frame length exceeds uint32 at byte {offset}")
        size |= (value & 127) << (7 * index)
        if value < 128:
            break
    if size > max_bytes:
        raise ValueError(f"Chakra frame exceeds configured limit at byte {offset}: {size}")
    payload = stream.read(size)
    if len(payload) != size:
        raise ValueError(f"Truncated Chakra payload at byte {offset}: {len(payload)}/{size}")
    message = message_class()
    message.ParseFromString(payload)
    return offset, message


def read_metadata(stream, schema):
    frame = read_frame(stream, schema.GlobalMetadata)
    # Published 0.0.4 files put the schema version in an attribute instead of
    # GlobalMetadata.version. Both are author-defined, not inferred defaults.
    if frame is None or not (frame[1].version or any(
            a.name == "schema" and a.WhichOneof("value") == "string_val" and a.string_val
            for a in frame[1].attr)):
        raise ValueError("Chakra input requires versioned global metadata")
    return frame[1]


def nodes(stream, schema):
    """Yield source offsets and nodes after metadata; preserve every node."""
    while (frame := read_frame(stream, schema.Node)) is not None:
        offset, node = frame
        if not node.name or not node.type:
            raise ValueError(f"Missing Chakra node name/type at byte {offset}")
        yield offset, node
