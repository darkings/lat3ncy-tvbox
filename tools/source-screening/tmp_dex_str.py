# -*- coding: utf-8 -*-
"""提取 qist spider.jar Config/LocalFile 类的字符串常量，推断 ext 数据格式。"""

import io
import struct
import urllib.request
import zipfile

URL = "https://ghfast.top/https://raw.githubusercontent.com/qist/tvbox/master/jar/spider.jar"


class DexStr:
    def __init__(self, data: bytes):
        self.data = data
        self.string_ids_size, self.string_ids_off = struct.unpack_from(
            "<II", data, 0x38
        )
        self.type_ids_size, self.type_ids_off = struct.unpack_from("<II", data, 0x40)
        self.method_ids_size, self.method_ids_off = struct.unpack_from(
            "<II", data, 0x58
        )
        self.class_defs_size, self.class_defs_off = struct.unpack_from(
            "<II", data, 0x60
        )

    def _string(self, idx: int) -> str:
        if idx < 0 or idx >= self.string_ids_size:
            return ""
        off = struct.unpack_from("<I", self.data, self.string_ids_off + idx * 4)[0]
        p = off
        while self.data[p] & 0x80:
            p += 1
        start = p + 1
        end = self.data.index(0, start)
        return self.data[start:end].decode("utf-8", "replace")

    def _type(self, idx: int) -> str:
        if idx < 0 or idx >= self.type_ids_size:
            return ""
        return self._string(
            struct.unpack_from("<I", self.data, self.type_ids_off + idx * 4)[0]
        )

    def _uleb(self, cursor: list) -> int:
        result = 0
        shift = 0
        while True:
            b = self.data[cursor[0]]
            cursor[0] += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                return result
            shift += 7

    def class_strings(self, class_desc: str) -> list:
        """返回指定类所有方法中 const-string 引用的字符串。"""
        found = []
        for i in range(self.class_defs_size):
            off = self.class_defs_off + i * 32
            desc = self._type(struct.unpack_from("<I", self.data, off)[0])
            if desc != class_desc:
                continue
            class_data_off = struct.unpack_from("<I", self.data, off + 24)[0]
            if class_data_off <= 0:
                return found
            cursor = [class_data_off]
            sf = self._uleb(cursor)
            inf = self._uleb(cursor)
            dm = self._uleb(cursor)
            vm = self._uleb(cursor)
            for _ in range(sf + inf):
                self._uleb(cursor)
                self._uleb(cursor)
            for count in (dm, vm):
                midx = 0
                for _ in range(count):
                    midx += self._uleb(cursor)
                    self._uleb(cursor)
                    code_off = self._uleb(cursor)
                    if code_off > 0:
                        found.extend(self._code_strings(code_off))
        return sorted(set(found))

    def _code_strings(self, code_off: int) -> list:
        insns_size = struct.unpack_from("<I", self.data, code_off + 12)[0]
        insns_off = code_off + 16
        end = insns_off + insns_size * 2
        out = []
        p = insns_off
        while p + 1 < end:
            op = self.data[p]
            if op == 0x1A and p + 3 < end:  # const-string
                idx = struct.unpack_from("<H", self.data, p + 2)[0]
                out.append(self._string(idx))
            elif op == 0x1B and p + 5 < end:  # const-string/jumbo
                idx = struct.unpack_from("<I", self.data, p + 2)[0]
                out.append(self._string(idx))
            p += 2
        return out


def main():
    with urllib.request.urlopen(
        urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=60
    ) as r:
        data = r.read()
    z = zipfile.ZipFile(io.BytesIO(data))
    dex = DexStr(z.read("classes.dex"))

    for cls in (
        "Lcom/github/catvod/spider/Config;",
        "Lcom/github/catvod/spider/LocalFile;",
    ):
        print("=" * 20, cls)
        for s in dex.class_strings(cls):
            if len(s) > 200:
                s = s[:200] + "..."
            print(" ", repr(s))


if __name__ == "__main__":
    main()
