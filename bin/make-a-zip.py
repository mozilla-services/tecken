#!/usr/bin/env python

import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin
from zipfile import ZipFile

import requests


def main(symbols, out_file, remote_url):
    def fmt_size(b):
        if b < 1024 * 1024:
            return f"{b / 1024:.1f}KB"
        return f"{b / 1024 / 1024:.1f}MB"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_out_file = Path(tmpdir) / Path("symbols-{}.zip".format(int(time.time())))
        with ZipFile(tmp_out_file, "w") as zip_:
            for symbol in symbols:
                if symbol.count("/") == 1:
                    lib_filename = symbol.split("/")[0]
                    if lib_filename.endswith(".pdb"):
                        symbol_filename = lib_filename[:-4] + ".sym"
                    else:
                        symbol_filename = lib_filename + ".sym"
                    symbol += "/" + symbol_filename
                url = urljoin(remote_url, symbol)
                fn = Path(tmpdir) / Path(symbol)
                fn.parent.mkdir(parents=True, exist_ok=True)
                with requests.get(url) as response, open(fn, "wb") as f:
                    f.write(response.content)
                    raw_size = int(response.headers["content-length"])
                    print(
                        "Downloaded {} bytes ({}, {} on disk) into {}"
                        "".format(
                            raw_size,
                            fmt_size(raw_size),
                            fmt_size(os.stat(fn).st_size),
                            fn.parent,
                        )
                    )
                zip_.write(fn, arcname=Path(symbol))

        shutil.move(tmp_out_file, out_file)
        print("Wrote", os.path.abspath(out_file))


if __name__ == "__main__":

    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", help="Symbols to download and include", nargs="*")
    parser.add_argument(
        "-o", "--out-file", help="ZIP file to create/update", default="symbols.zip"
    )
    parser.add_argument(
        "-u",
        "--remote-url",
        help="URL to download symbols from",
        default="https://symbols.mozilla.org",
    )

    args = parser.parse_args()
    if not args.symbols:
        print("Need at least 1 symbol", file=sys.stderr)
    main(**vars(args))
