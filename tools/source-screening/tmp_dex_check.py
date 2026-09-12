# -*- coding: utf-8 -*-
"""验证 qist spider.jar 中 Config/LocalFile 类是否含自杀/包名检测代码。"""

import io
import struct
import urllib.request
import zipfile

URL = "https://ghfast.top/https://raw.githubusercontent.com/qist/tvbox/master/jar/spider.jar"


class DexReader:
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
        # uleb128 length
        p = off
        while self.data[p] & 0x80:
            p += 1
        start = p + 1
        end = self.data.index(0, start)
        return self.data[start:end].decode("utf-8", "replace")

    def _type(self, idx: int) -> str:
        if idx < 0 or idx >= self.type_ids_size:
            return ""
        desc_idx = struct.unpack_from("<I", self.data, self.type_ids_off + idx * 4)[0]
        return self._string(desc_idx)

    def _method(self, idx: int) -> tuple:
        if idx < 0 or idx >= self.method_ids_size:
            return ("", "")
        off = self.method_ids_off + idx * 8
        class_idx = struct.unpack_from("<H", self.data, off)[0]
        name_idx = struct.unpack_from("<I", self.data, off + 4)[0]
        return (self._type(class_idx), self._string(name_idx))

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

    def class_methods(self, class_desc: str) -> dict:
        """返回 {class_desc: {method_name: [invoke 的 method 引用列表]}}"""
        result = {}
        for i in range(self.class_defs_size):
            off = self.class_defs_off + i * 32
            desc = self._type(struct.unpack_from("<I", self.data, off)[0])
            if desc != class_desc:
                continue
            class_data_off = struct.unpack_from("<I", self.data, off + 24)[0]
            if class_data_off <= 0:
                return {desc: {}}
            cursor = [class_data_off]
            static_fields = self._uleb(cursor)
            instance_fields = self._uleb(cursor)
            direct_methods = self._uleb(cursor)
            virtual_methods = self._uleb(cursor)
            # skip fields
            for _ in range(static_fields + instance_fields):
                self._uleb(cursor)
                self._uleb(cursor)
            methods = {}
            for kind, count in (
                ("direct", direct_methods),
                ("virtual", virtual_methods),
            ):
                midx = 0
                for _ in range(count):
                    midx += self._uleb(cursor)
                    self._uleb(cursor)  # access flags
                    code_off = self._uleb(cursor)
                    cls, name = self._method(midx)
                    invokes = []
                    if code_off > 0:
                        invokes = self._code_invokes(code_off)
                    methods.setdefault(name, []).extend(invokes)
            result[desc] = methods
        return result

    def _code_invokes(self, code_off: int) -> list:
        insns_size = struct.unpack_from("<I", self.data, code_off + 12)[0]
        insns_off = code_off + 16
        end = insns_off + insns_size * 2
        invokes = []
        p = insns_off
        while p + 1 < end:
            op = self.data[p]
            if 0x6E <= op <= 0x72:  # invoke-* 系列
                if p + 3 < end:
                    method_idx = struct.unpack_from("<H", self.data, p + 2)[0]
                    cls, name = self._method(method_idx)
                    if cls == "Landroid/os/Process;" and name == "killProcess":
                        invokes.append("Process.killProcess")
            p += 2
        return invokes


def main():
    with urllib.request.urlopen(
        urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=60
    ) as r:
        data = r.read()
    z = zipfile.ZipFile(io.BytesIO(data))
    dex = DexReader(z.read("classes.dex"))

    for cls in (
        "Lcom/github/catvod/spider/Config;",
        "Lcom/github/catvod/spider/LocalFile;",
    ):
        m = dex.class_methods(cls)
        print(cls)
        for name, invokes in m.get(cls, {}).items():
            print(f"  方法 {name}: killProcess 调用 = {invokes if invokes else '无'}")
        if not m:
            print("  未找到该类！")


if __name__ == "__main__":
    main()
