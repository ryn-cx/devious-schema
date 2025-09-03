import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


def to_snake_case(text: str) -> str:
    """Convert a string to snake_case."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return text.lower()


def to_pascal_case(text: str) -> str:
    """Convert a string to PascalCase."""
    return "".join(part[0].upper() + part[1:] for part in text.split("_") if part)


class TypeInfo(BaseModel):
    name: str = Field(default="")
    allow_str: bool = Field(default=False)
    allow_int: bool = Field(default=False)
    allow_float: bool = Field(default=False)
    allow_none: bool = Field(default=False)
    allow_dict: bool = Field(default=False)
    allow_list: bool = Field(default=False)
    optional: bool = Field(default=False)
    list_items: "TypeInfo | None" = Field(default=None)
    dict_keys: dict[str, "TypeInfo"] = Field(default_factory=dict)


parsable_types = (
    str | int | float | None | dict[str, "parsable_types"] | list["parsable_types"]
)


def _parse_value(
    value: parsable_types,
    target_type: TypeInfo,
    key_name: str = "",
) -> None:
    """Parse a single value and update the target TypeInfo."""
    if isinstance(value, str):
        target_type.allow_str = True
    elif isinstance(value, int):
        target_type.allow_int = True
    elif isinstance(value, float):
        target_type.allow_float = True
    elif value is None:
        target_type.allow_none = True
    elif isinstance(value, dict):
        target_type.allow_dict = True
        parse_dict(value, target_type)
    # List elif isn't strictly required as long as the input has the correct type, but
    # there is no way to guarantee the input actually matches the type.
    elif isinstance(value, list):  # type: ignore[reportUnnecessaryIsInstance]
        target_type.allow_list = True
        if target_type.list_items is None:
            target_type.list_items = TypeInfo(
                name=f"{key_name}_item" if key_name else f"{target_type.name}Item",
            )
        for x in value:
            _parse_value(x, target_type.list_items)
    else:
        msg = f"Unexpected list item type: {type(x)}"
        raise TypeError(msg)


def parse_dict(input_data: dict[str, Any], type_info: TypeInfo) -> TypeInfo:
    """Parse dictionary data into TypeInfo."""
    for key, value in input_data.items():
        if key not in type_info.dict_keys:
            type_info.dict_keys[key] = TypeInfo(
                name=f"{type_info.name}{to_pascal_case(key)}",
            )

        _parse_value(value, type_info.dict_keys[key], key)

    # Mark missing keys as optional
    for key in type_info.dict_keys:
        if key not in input_data:
            type_info.dict_keys[key].optional = True

    return type_info


def parse_list(input_data: list[Any], type_info: TypeInfo) -> TypeInfo:
    """Parse list data into TypeInfo."""
    if not input_data:  # Empty list
        type_info.allow_list = True
        return type_info

    if type_info.list_items is None:
        type_info.list_items = TypeInfo(name=f"{type_info.name}Item")

    for item in input_data:
        _parse_value(item, type_info.list_items)

    return type_info


def parse(input_data: dict[str, Any] | list[Any], type_info: TypeInfo) -> TypeInfo:
    """Parse data into TypeInfo that can handle both dicts and lists."""
    if isinstance(input_data, dict):
        return parse_dict(input_data, type_info)
    # List elif isn't strictly required as long as the input has the correct type, but
    # there is no way to guarantee the input actually matches the type.
    if isinstance(input_data, list):  # type: ignore[reportUnnecessaryIsInstance]
        return parse_list(input_data, type_info)

    msg = f"Unexpected input data type: {type(input_data)}"
    raise TypeError(msg)


# C901 - This isn't that complicated, it's only like 30 lines of code and all of it is
# really simple if and string concatenation.
def build_type_annotation(type_info: TypeInfo, models: list[str]) -> str:  # noqa: C901
    """Build type annotation from a TypeInfo."""
    type_parts: list[str] = []

    if type_info.allow_str:
        type_parts.append("str")
    if type_info.allow_int:
        type_parts.append("int")
    if type_info.allow_float:
        type_parts.append("float")
    if type_info.allow_none or type_info.optional:
        type_parts.append("None")

    if type_info.dict_keys:
        dict_class_name = f"{to_pascal_case(type_info.name)}Dict"
        type_parts.append(dict_class_name)
        dict_model = generate_dict_model(type_info, dict_class_name, models)
        models.insert(0, dict_model)
    elif type_info.allow_dict:
        type_parts.append("dict[str, Any]")

    list_types: list[str] = []
    if type_info.list_items:
        list_type = build_type_annotation(type_info.list_items, models)
        list_types.append(list_type)
    elif type_info.allow_list:
        list_types.append("Any")

    if list_types:
        type_parts.append(f"list[{' | '.join(list_types)}]")

    if len(type_parts) == 0:
        return "Any"
    if len(type_parts) == 1:
        return type_parts[0]
    return " | ".join(type_parts)


def generate_dict_model(type_info: TypeInfo, model_name: str, models: list[str]) -> str:
    """Generate a BaseModel class for dictionary data."""
    lines = [f"class {to_pascal_case(model_name)}(BaseModel):"]
    lines.append('    model_config = ConfigDict(extra="forbid")')

    for field_name, field_wrapper in type_info.dict_keys.items():
        field_type = build_type_annotation(field_wrapper, models)

        field_config = ""
        if to_snake_case(field_name) != field_name:
            field_config = f' = Field(alias="{field_name}")'

        lines.append(f"    {to_snake_case(field_name)}: {field_type}{field_config}")

    return "\n".join(lines)


def generate_pydantic_schema(type_info: TypeInfo, class_name: str) -> str:
    """Generate Pydantic model code from a TypeInfo."""
    imports = [
        "from pydantic import BaseModel, Field, ConfigDict",
        "from typing import Any",
    ]
    models: list[str] = []

    # Generate the main model
    if type_info.dict_keys and type_info.list_items:
        # Root is a dictionary
        main_model = generate_dict_model(type_info, class_name, models)
        list_type = build_type_annotation(type_info, models)
        models.append(f"{to_snake_case(type_info.name)}: {list_type}")
    elif type_info.list_items:
        # Root is a list
        list_type = build_type_annotation(type_info, models)
        main_model = f"{to_snake_case(type_info.name)}: {list_type}"
        models.append(main_model)
    elif type_info.dict_keys:
        # Root is a dictionary
        main_model = generate_dict_model(type_info, class_name, models)
        models.append(main_model)
    # Combine everything
    return "\n".join(imports) + "\n\n\n" + "\n\n\n".join(models)


def get_schema(raw_data: dict[str, Any] | list[Any], root_name: str) -> str:
    """Generate Pydantic schema from input data."""
    root = TypeInfo(name=root_name)
    parsed_data = parse(raw_data, root)
    return generate_pydantic_schema(parsed_data, root_name)


def get_schema_from_strings(
    raw_data: list[Any],
    root_name: str,
) -> str:
    """Generate Pydantic schema from multiple input files."""
    root = TypeInfo(name=root_name)
    for data in raw_data:
        parse(data, root)
    return generate_pydantic_schema(root, root_name)


def get_schema_from_files(
    file_paths: list[str | Path] | list[str] | list[Path],
    root_name: str,
) -> str:
    """Generate Pydantic schema from multiple input files."""
    root = TypeInfo(name=root_name)
    for file_path in file_paths:
        path = Path(file_path)
        parsed_data = json.loads(path.read_text(encoding="utf-8"))
        parse(parsed_data, root)
    return generate_pydantic_schema(root, root_name)


def get_schema_from_folder(
    folder_path: str | Path,
    root_name: str,
) -> str:
    """Generate Pydantic schema from all JSON files in a folder."""
    root = TypeInfo(name=root_name)
    path = Path(folder_path)
    if not path.exists() or not path.is_dir():
        msg = f"Error: '{folder_path}' does not exist or is not a directory"
        raise FileNotFoundError(msg)

    for json_file in path.glob("*.json"):
        parsed_data = json.loads(json_file.read_text(encoding="utf-8"))
        parse(parsed_data, root)

    return generate_pydantic_schema(root, root_name)


class CLISettings(BaseSettings):
    """Command line interface settings."""

    files: list[str] = Field(
        default_factory=list,
        description="List of JSON files to process",
    )
    folder: str | None = Field(
        default=None,
        description="Folder containing JSON files to process",
    )
    root_name: str = Field(
        default="Model",
        description="Root name for the generated schema",
    )
    output: str = Field(
        description="Output file path (prints to stdout if not specified)",
    )

    class Config:
        env_prefix = ""


def main() -> None:
    """Main CLI entry point."""
    settings = CLISettings()

    # Collect all file paths
    file_paths: list[Path] = []

    if settings.folder:
        folder_path = Path(settings.folder)
        if not folder_path.exists() or not folder_path.is_dir():
            msg = f"Error: '{settings.folder}' does not exist or is not a directory"
            raise FileNotFoundError(msg)
        file_paths.extend(folder_path.glob("*.json"))

    if settings.files:
        for file_str in settings.files:
            file_path = Path(file_str)
            if not file_path.exists():
                msg = f"Error: File '{file_str}' does not exist"
                raise FileNotFoundError(msg)
            file_paths.append(file_path)

    if not file_paths:
        msg = "Error: No valid input files provided. Use --files or --folder."
        raise FileNotFoundError(msg)

    schema = get_schema_from_files(file_paths, settings.root_name)
    Path(settings.output).write_text(schema, encoding="utf-8")


if __name__ == "__main__":
    main()
