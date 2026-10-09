"""Strict local validation of the committed JSON-schema subset; no dependency drift."""

from __future__ import annotations

import math


def validate(document, schema):
    def walk(value, node, path):
        if "$ref" in node:
            target = schema
            for part in node["$ref"].removeprefix("#/").split("/"):
                target = target[part]
            walk(value, target, path)
            return
        if "if" in node:
            try:
                walk(value, node["if"], path)
            except ValueError:
                branch = "else"
            else:
                branch = "then"
            if branch in node:
                walk(value, node[branch], path)
        if "const" in node and value != node["const"]:
            raise ValueError("RESULT_SCHEMA_CONST: " + path)
        if "enum" in node and value not in node["enum"]:
            raise ValueError("RESULT_SCHEMA_ENUM: " + path)
        types = node.get("type", [])
        types = [types] if isinstance(types, str) else types
        kinds = {
            "null": value is None,
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value),
            "boolean": isinstance(value, bool),
        }
        if types and not any(kinds[t] for t in types):
            raise ValueError("RESULT_SCHEMA_TYPE: " + path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if (
                not math.isfinite(value)
                or value < node.get("minimum", -math.inf)
                or value > node.get("maximum", math.inf)
            ):
                raise ValueError("RESULT_SCHEMA_RANGE: " + path)
        if isinstance(value, dict):
            if any(k not in value for k in node.get("required", [])):
                raise ValueError("RESULT_SCHEMA_REQUIRED: " + path)
            props = node.get("properties", {})
            for key, item in value.items():
                if key in props:
                    walk(item, props[key], path + "." + key)
                elif node.get("additionalProperties") is False:
                    raise ValueError("RESULT_SCHEMA_EXTRA: " + path + "." + key)
                elif isinstance(node.get("additionalProperties"), dict):
                    walk(item, node["additionalProperties"], path + "." + key)
        if isinstance(value, list) and "items" in node:
            for i, item in enumerate(value):
                walk(item, node["items"], path + f"[{i}]")

    walk(document, schema, "result")
