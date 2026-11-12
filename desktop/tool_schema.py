from __future__ import annotations

from typing import Any


def form_schema(spec: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in spec.get("fields", []):
        name, kind = field["name"], field.get("type", "text")
        if name == "approved" or kind == "password":
            continue
        if kind == "file":
            properties["attachment_index"] = {
                "type": "integer", "minimum": 0, "maximum": 31,
                "description": "Kullanıcının seçtiği ekin sıfır tabanlı sırası; dosya içeriği üretme.",
            }
            if field.get("required"):
                required.append("attachment_index")
            continue
        definition: dict[str, Any] = {"description": field.get("label", name)}
        if kind == "number":
            definition["type"] = "integer" if field.get("step", 1) in (1, "1") else "number"
            for source, target in (("min", "minimum"), ("max", "maximum")):
                if source in field:
                    definition[target] = field[source]
        elif kind == "checkbox":
            definition["type"] = "boolean"
        elif kind == "lines":
            definition.update(type="array", items={"type": "string"})
            if field.get("maxLines"):
                definition["maxItems"] = field["maxLines"]
            if field.get("maxLineLength"):
                definition["items"]["maxLength"] = field["maxLineLength"]
            if field.get("required"):
                definition["minItems"] = 1
        elif kind == "json":
            definition.update(field.get("schema", {}))
        else:
            definition["type"] = "string"
            if field.get("maxLength"):
                definition["maxLength"] = field["maxLength"]
            if field.get("required") and not field.get("preserveWhitespace"):
                definition["minLength"] = 1
            if field.get("pattern"):
                definition["pattern"] = f"^(?:{field['pattern']})$"
            if kind == "select":
                definition["enum"] = field.get("options", [])
        properties[name] = definition
        if field.get("required"):
            required.append(name)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
