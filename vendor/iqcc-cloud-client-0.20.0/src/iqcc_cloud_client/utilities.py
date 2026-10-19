import ast
import base64
import json
import os
from collections import namedtuple
from pathlib import Path

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

Import = namedtuple("Import", ["module", "name", "alias"])


def format_json_dense_arrays(
    obj,
    indent=2,
    level=0,
    max_items=20,
    show_truncation=True,
):
    pad = " " * (indent * level)
    next_pad = " " * (indent * (level + 1))

    if isinstance(obj, dict):
        items = []
        for k, v in obj.items():
            value = format_json_dense_arrays(
                v, indent, level + 1, max_items, show_truncation
            )
            items.append(f"\n{next_pad}{json.dumps(k)}: {value}")
        return "{" + ",".join(items) + f"\n{pad}" + "}"

    if isinstance(obj, list):
        truncated = obj[:max_items]
        parts = [
            json.dumps(x)
            if not isinstance(x, (dict, list, bool))
            else format_json_dense_arrays(
                x, indent, level, max_items, show_truncation
            )
            for x in truncated
        ]

        if show_truncation and len(obj) > max_items:
            parts.append(json.dumps(f"... {len(obj) - max_items} more items"))

        return "[" + ", ".join(parts) + "]"
    if isinstance(obj, bool):
        return "True" if obj else "False"

    return json.dumps(obj)


def _convert_numpy_to_list(obj) -> dict:
    """
    Recursively converts all numpy arrays AND numpy scalars to native Python types.

    Handles:
    - np.ndarray -> list
    - np.float64, np.int32, etc. -> float, int
    - Dict keys that are not str/bytes -> str
    - Nested dicts, lists, tuples

    Args:
        obj: Any Python object

    Returns:
        Structure with all numpy types converted to native Python types
    """
    if not NUMPY_AVAILABLE:
        return obj

    # 1. Handle Numpy Arrays
    if isinstance(obj, np.ndarray):
        # .tolist() converts array elements recursively, but we ensure scalars are handled too
        return obj.tolist()

    # 2. Handle Numpy Scalars (the specific issue with >2.0 strictness)
    # This catches np.float64(1.0) passed directly, not inside an array
    if isinstance(obj, np.generic):
        return obj.item()

    # 3. Handle Dictionaries
    elif isinstance(obj, dict):
        return {
            str(key)
            if not isinstance(key, (str, bytes))
            else key: _convert_numpy_to_list(value)
            for key, value in obj.items()
        }

    # 4. Handle Lists
    elif isinstance(obj, list):
        return [_convert_numpy_to_list(item) for item in obj]

    # 5. Handle Tuples
    elif isinstance(obj, tuple):
        return tuple(_convert_numpy_to_list(item) for item in obj)

    # 6. Handle Sets
    elif isinstance(obj, set):
        return {_convert_numpy_to_list(item) for item in obj}

    # 7. Default: Return unchanged
    else:
        return obj


def _create_payload(folder_path, max_total_mb=8, max_file_mb=8):
    payload = {}
    total_bytes = 0
    max_total_bytes = max_total_mb * 1024 * 1024
    max_file_bytes = max_file_mb * 1024 * 1024

    if type(folder_path) is not str:
        # this is already expanded payload
        return folder_path

    # List all files in the folder (non-recursive)

    directory = Path(folder_path)
    files = [f for f in directory.rglob("*") if f.is_file()]

    for file_name in files:
        file_path = file_name

        file_size = os.path.getsize(file_path)

        if file_size > max_file_bytes:
            print(
                f"NOTE: Skipping {file_name} since it's size {file_size} is over maximal allowed one {max_file_bytes}."
            )
            continue

        if total_bytes + file_size > max_total_bytes:
            raise ValueError(
                f"Total size of upload directory cannot exceed {max_total_bytes}. Current size {total_bytes + file_size}"
            )

        # Read and base64 encode file
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        relative_path = file_path.relative_to(directory)
        payload[Path(relative_path).as_posix()] = encoded
        total_bytes += file_size
    return payload


def _complex_decoder(obj):
    if "__type__" in obj and obj["__type__"] == "complex":
        return complex(obj["data"][0], obj["data"][1])
    return obj


def _truncate_strings(obj, max_length=300):
    if isinstance(obj, str):
        return obj[:max_length] + ("..." if len(obj) > max_length else "")
    elif isinstance(obj, list):
        return [_truncate_strings(item, max_length) for item in obj]
    elif isinstance(obj, dict):
        return {
            key: _truncate_strings(value, max_length)
            for key, value in obj.items()
        }
    return obj


def _resolve_files(options: dict):
    hooks = ["pre_hook", "sync_hook", "post_hook"]
    for h in hooks:
        if h in options.keys():
            if type(options[h]) is str:
                with open(options[h], "r") as f:
                    options[h] = f.read()
            elif type(options[h]) is dict:
                for key in options[h].keys():
                    if key not in [
                        "user-cache-ref",
                        "image",
                        "directory",
                        "execute",
                        "global-cache-ref",
                    ]:
                        raise ValueError(
                            f"{h} should be either a string to filename or dict with 'user-cache-ref' key"
                        )
                    if key == "directory":
                        options[h]["directory"] = _create_payload(
                            options[h]["directory"]
                        )


def _get_imports(code):
    root = ast.parse(code)

    for node in ast.iter_child_nodes(root):
        if isinstance(node, ast.Import):
            module = []
        elif isinstance(node, ast.ImportFrom):
            module = node.module.split(".")
        else:
            continue

        for n in node.names:
            yield Import(module, n.name.split("."), n.asname)


def _this_is_qua_program(code: str) -> bool:
    try:
        for imp in _get_imports(code):
            if imp.module[0] not in ["qm", "typing"]:
                print(imp.module)
                return False
    except Exception as _:
        return False
    return True
