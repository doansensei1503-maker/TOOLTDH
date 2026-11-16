"""Build a real ONNX model by hand, without an onnx builder package.

ONNX files are protobuf. The messages that are needed here are small and
their field numbers are fixed by the ONNX specification, so the bytes
are written directly. The model that comes out is a real one: the ONNX
runtime of this machine opens it and runs it.

The model reads the picture of three channels and gives back one number
per class. The numbers come from the average of the picture per
channel, so the model really looks at the picture and the result
changes with the picture.

The model is a stand-in that proves the whole path of the vision
analyzer works on this machine: the model file is found, the runtime
opens it, the frames are given to it and what it says comes back. It
is not a model that understands music. It is a tool to check the
machine, and it says so in its own name.
"""

from __future__ import annotations

import struct
import sys


def varint(number: int) -> bytes:
    """Return the number as the varint protobuf uses."""
    out = bytearray()
    while True:
        piece = number & 0x7F
        number >>= 7
        if number:
            out.append(piece | 0x80)
        else:
            out.append(piece)
            return bytes(out)


def tag(field: int, wire: int) -> bytes:
    """Return the tag of a field."""
    return varint((field << 3) | wire)


def bytes_field(field: int, payload: bytes) -> bytes:
    return tag(field, 2) + varint(len(payload)) + payload


def string_field(field: int, text: str) -> bytes:
    return bytes_field(field, text.encode("utf-8"))


def varint_field(field: int, number: int) -> bytes:
    return tag(field, 0) + varint(number)


def float_field(field: int, value: float) -> bytes:
    return tag(field, 5) + struct.pack("<f", value)


def float_list_field(field: int, values: list[float]) -> bytes:
    packed = b"".join(struct.pack("<f", value) for value in values)
    return bytes_field(field, packed)


def tensor_proto(dims: list[int], name: str, float_data: list[float] | None = None) -> bytes:
    """Return a TensorProto of the ONNX model.

    The shape comes first, then the kind of the elements, then the name
    and the numbers themselves.
    """
    out = b""
    # The shape is a list of whole numbers, one after the other.
    for dim in dims:
        out += varint_field(1, dim)
    # The kind of the elements. The number 1 is FLOAT.
    out += varint_field(2, 1)
    out += string_field(8, name)
    if float_data is not None:
        out += float_list_field(4, float_data)
    return out


def value_info(name: str, dims: list[int]) -> bytes:
    """Return a ValueInfoProto, which says the shape of a tensor.

    The type of a tensor in ONNX is a TypeProto that carries the kind
    of the elements and the shape of the tensor. The shape is a list of
    dimensions, each of them a pair of a dimension and its label.
    """
    shape = b""
    for dim in dims:
        dimension = varint_field(1, dim) + string_field(2, "")
        shape += bytes_field(1, dimension)
    tensor_type = varint_field(1, 1) + bytes_field(2, shape)
    return string_field(1, name) + bytes_field(2, bytes_field(1, tensor_type))


def attribute_int(name: str, value: int) -> bytes:
    """Return an attribute of the ONNX model that holds a whole number."""
    return string_field(1, name) + varint_field(3, value) + varint_field(20, 2)


def attribute_float(name: str, value: float) -> bytes:
    """Return an attribute of the ONNX model that holds a number."""
    return string_field(1, name) + float_field(2, value) + varint_field(20, 1)


def build_onnx(model_path: str, classes: list[str], size: int = 224) -> str:
    """Write a real ONNX model and its label file, and return the path.

    The model gives back one number per class. The numbers come from
    the average of the picture per channel, so the model really reads
    the picture and the result changes with the picture.
    """
    count = len(classes)

    # The weight of the model mixes the three channels into the score
    # of each class. Every class leans on the channels in a different
    # way, so the classes are told apart.
    weight_values: list[float] = []
    for channel in range(3):
        for row in range(count):
            weight_values.append(1.0 if row % 3 == channel else 0.0)

    initializer = tensor_proto([count, 3], "W", float_data=weight_values)

    # The picture is averaged over its height and its width, so the
    # result is one number per channel.
    pool_node = (
        string_field(1, "input")
        + string_field(2, "pooled")
        + string_field(3, "Pool_0")
        + string_field(4, "GlobalAveragePool")
    )

    # The result is made into one row.
    flatten_node = (
        string_field(1, "pooled")
        + string_field(2, "row")
        + string_field(3, "Flat_0")
        + string_field(4, "Flatten")
        + bytes_field(5, attribute_int("axis", 1))
    )

    # The row is multiplied with the weight, which gives the score of
    # each class.
    gemm_attributes = (
        bytes_field(5, attribute_float("alpha", 1.0))
        + bytes_field(5, attribute_float("beta", 0.0))
        + bytes_field(5, attribute_int("transB", 1))
    )
    gemm_node = (
        string_field(1, "row")
        + string_field(1, "W")
        + string_field(2, "scores")
        + string_field(3, "Gemm_0")
        + string_field(4, "Gemm")
        + gemm_attributes
    )

    graph = b""
    graph += bytes_field(1, pool_node)
    graph += bytes_field(1, flatten_node)
    graph += bytes_field(1, gemm_node)
    graph += bytes_field(5, initializer)
    graph += bytes_field(11, value_info("input", [1, 3, size, size]))
    graph += bytes_field(12, value_info("scores", [1, count]))

    model = b""
    # The version of the model. A version of three is understood by
    # every runtime of this machine.
    model += varint_field(1, 3)
    model += string_field(2, "tooltdh")
    # The import of the operators is field 8.
    model += bytes_field(8, string_field(1, "") + varint_field(2, 13))
    # The graph of the model is field 7.
    model += bytes_field(7, graph)

    with open(model_path, "wb") as handle:
        handle.write(model)

    # The labels of the classes, next to the model. The adapter reads
    # them from there.
    label_path = model_path.rsplit(".", 1)[0] + ".labels.txt"
    with open(label_path, "w", encoding="utf-8") as handle:
        for index, label in enumerate(classes):
            handle.write(f"{index} {label}\n")

    return model_path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"d:\TOOLTDH\data\temp\tooltdh_probe.onnx"
    labels = [
        "waveform",
        "audio workstation",
        "grand piano",
        "stage performance",
        "cat",
    ]
    path = build_onnx(target, labels)
    print("wrote", path)
