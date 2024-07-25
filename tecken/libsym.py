# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


class SymParseError(Exception):
    """Any kind of error when parsing a sym file."""


def extract_sym_header_data(file_path):
    """Returns header data from thh sym file header.

    :arg file_path: the path to the sym file

    :returns: sym info as a dict

    :raises SymParseError: any kind of sym parse error

    """
    data = {
        "debug_filename": "",
        "debug_id": "",
        "code_file": "",
        "code_id": "",
        "generator": "",
    }
    with open(file_path, "r") as fp:
        line = "no line yet"
        try:
            for line in fp:
                if line.startswith("MODULE"):
                    parts = line.strip().split()
                    _, opsys, arch, debug_id, debug_filename = parts
                    data["debug_filename"] = debug_filename
                    data["debug_id"] = debug_id.upper()

                elif line.startswith("INFO CODE_ID"):
                    parts = line.strip().split()
                    # NOTE(willkg): Non-Windows module sym files don't have a code_file
                    if len(parts) == 3:
                        _, _, code_id = parts
                        code_file = ""
                    elif len(parts) == 4:
                        _, _, code_id, code_file = parts

                    data["code_file"] = code_file
                    data["code_id"] = code_id.upper()

                elif line.startswith("INFO GENERATOR"):
                    _, _, generator = line.strip().split(maxsplit=2)
                    data["generator"] = generator

                else:
                    break

        except Exception as exc:
            raise SymParseError(f"sym parse error {exc!r} with {line!r}") from exc

    return data
