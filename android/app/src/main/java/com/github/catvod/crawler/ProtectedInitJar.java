package com.github.catvod.crawler;

import android.content.Context;
import android.text.TextUtils;
import android.util.Base64;

import com.github.tvbox.osc.base.App;

import java.io.ByteArrayOutputStream;
import java.io.Closeable;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.util.concurrent.ConcurrentHashMap;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

class ProtectedInitJar {

    private static final byte[] DEX_MAGIC = new byte[]{'d', 'e', 'x'};
    private static final int BUFFER_SIZE = 8192;

    private final ConcurrentHashMap<String, Boolean> jars = new ConcurrentHashMap<>();

    void clear() {
        jars.clear();
    }

    boolean check(String jar) {
        Boolean cached = jars.get(jar);
        if (cached != null) return cached;
        boolean result = scan(jar, App.getInstance().getPackageName());
        jars.put(jar, result);
        return result;
    }

    void init(Class<?> clz) {
        // 危险 jar：仅尝试注入静态 context，不调用 get()/init()/replaceCloudDiskNames/startGoProxy，
        // 避免触发 jar 内置的“加载失败”检测线程（Toast 后延迟 killProcess 自杀）
        try {
            Field context = clz.getDeclaredField("c");
            context.setAccessible(true);
            if (java.lang.reflect.Modifier.isStatic(context.getModifiers())) {
                context.set(null, App.getInstance());
            }
        } catch (Throwable ignored) {
        }
    }

    private static boolean scan(String jar, String packageName) {
        try {
            File file = new File(jar);
            if (!file.exists()) return false;
            java.util.List<byte[]> dexList = new java.util.ArrayList<>();
            if (isDexFile(file)) {
                InputStream is = null;
                try {
                    is = new FileInputStream(file);
                    dexList.add(readBytes(is));
                } finally {
                    close(is);
                }
            } else {
                ZipFile zip = null;
                try {
                    zip = new ZipFile(file);
                    java.util.Enumeration<? extends ZipEntry> entries = zip.entries();
                    while (entries.hasMoreElements()) {
                        ZipEntry entry = entries.nextElement();
                        if (!entry.getName().endsWith(".dex")) continue;
                        InputStream is = null;
                        try {
                            is = zip.getInputStream(entry);
                            dexList.add(readBytes(is));
                        } finally {
                            close(is);
                        }
                    }
                } finally {
                    close(zip);
                }
            }
            // 跨 dex 聚合检测：混淆 jar 可能把 Init 类与 killProcess 调用分散到多个 dex，
            // 单独判定会漏检导致 jar 的自杀逻辑（Toast 后 killProcess）被执行
            boolean hasInit = false;
            boolean hasKillProcess = false;
            boolean hasPackageGuard = false;
            boolean whitelisted = false;
            for (byte[] dexData : dexList) {
                try {
                    Dex dex = new Dex(dexData, packageName);
                    hasInit = hasInit || dex.hasInitClass();
                    hasKillProcess = hasKillProcess || dex.hasKillProcess();
                    hasPackageGuard = hasPackageGuard || dex.hasPackageGuard();
                    whitelisted = whitelisted || dex.initWhitelisted();
                } catch (Throwable ignored) {
                }
            }
            if (whitelisted) return false;
            if (hasInit && hasKillProcess) return true;
            return hasInit && hasPackageGuard;
        } catch (Throwable ignored) {
        }
        return false;
    }

    private static boolean isDexFile(File file) {
        InputStream is = null;
        try {
            is = new FileInputStream(file);
            byte[] magic = new byte[DEX_MAGIC.length];
            int len = is.read(magic);
            return len == DEX_MAGIC.length && startsWith(magic, DEX_MAGIC);
        } catch (Throwable ignored) {
            return false;
        } finally {
            close(is);
        }
    }

    private static byte[] readBytes(InputStream is) throws Exception {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        byte[] buffer = new byte[BUFFER_SIZE];
        int len;
        while ((len = is.read(buffer)) != -1) baos.write(buffer, 0, len);
        close(is);
        return baos.toByteArray();
    }

    private static boolean startsWith(byte[] data, byte[] pattern) {
        if (data == null || pattern == null || data.length < pattern.length) return false;
        for (int i = 0; i < pattern.length; i++) {
            if (data[i] != pattern[i]) return false;
        }
        return true;
    }

    private static void close(Closeable closeable) {
        try {
            if (closeable != null) closeable.close();
        } catch (Throwable ignored) {
        }
    }

    private static class Dex {

        private final byte[] data;
        private final int stringIdsSize;
        private final int stringIdsOff;
        private final int typeIdsSize;
        private final int typeIdsOff;
        private final int methodIdsSize;
        private final int methodIdsOff;
        private final int classDefsSize;
        private final int classDefsOff;
        private final Whitelist whitelist;

        Dex(byte[] data, String packageName) {
            this.data = data;
            this.stringIdsSize = uint(0x38);
            this.stringIdsOff = uint(0x3c);
            this.typeIdsSize = uint(0x40);
            this.typeIdsOff = uint(0x44);
            this.methodIdsSize = uint(0x58);
            this.methodIdsOff = uint(0x5c);
            this.classDefsSize = uint(0x60);
            this.classDefsOff = uint(0x64);
            this.whitelist = new Whitelist(packageName);
        }

        boolean hasInitClass() {
            for (int i = 0; i < classDefsSize; i++) {
                int off = classDefsOff + i * 32;
                String desc = typeDesc(uint(off));
                if ("Lcom/github/catvod/spider/Init;".equals(desc)) return true;
            }
            return false;
        }

        boolean initWhitelisted() {
            for (int i = 0; i < classDefsSize; i++) {
                int off = classDefsOff + i * 32;
                String desc = typeDesc(uint(off));
                if (!"Lcom/github/catvod/spider/Init;".equals(desc)) continue;
                int classDataOff = uint(off + 24);
                if (classDataOff <= 0) continue;
                if (scanInitWhitelist(classDataOff)) return true;
            }
            return false;
        }

        boolean hasKillProcess() {
            for (int i = 0; i < classDefsSize; i++) {
                int off = classDefsOff + i * 32;
                int classDataOff = uint(off + 24);
                if (classDataOff <= 0) continue;
                if (scanKillProcess(classDataOff)) return true;
            }
            return false;
        }

        boolean hasPackageGuard() {
            return containsString("包名不匹配");
        }

        private boolean containsString(String expected) {
            if (TextUtils.isEmpty(expected)) return false;
            for (int i = 0; i < stringIdsSize; i++) {
                String value = string(i);
                if (!TextUtils.isEmpty(value) && value.contains(expected)) return true;
            }
            return false;
        }

        private boolean scanInitWhitelist(int off) {
            int[] cursor = new int[]{off};
            int staticFields = uleb(cursor);
            int instanceFields = uleb(cursor);
            int directMethods = uleb(cursor);
            int virtualMethods = uleb(cursor);
            skipFields(cursor, staticFields + instanceFields);
            return scanInitMethods(cursor, directMethods) || scanInitMethods(cursor, virtualMethods);
        }

        private boolean scanInitMethods(int[] cursor, int count) {
            int methodIdx = 0;
            for (int i = 0; i < count; i++) {
                methodIdx += uleb(cursor);
                uleb(cursor);
                int codeOff = uleb(cursor);
                if (codeOff <= 0 || methodIdx >= methodIdsSize) continue;
                if ("init".equals(methodName(methodIdx)) && scanWhitelist(codeOff)) return true;
            }
            return false;
        }

        private boolean scanKillProcess(int off) {
            int[] cursor = new int[]{off};
            int staticFields = uleb(cursor);
            int instanceFields = uleb(cursor);
            int directMethods = uleb(cursor);
            int virtualMethods = uleb(cursor);
            skipFields(cursor, staticFields + instanceFields);
            return scanKillMethods(cursor, directMethods) || scanKillMethods(cursor, virtualMethods);
        }

        private boolean scanKillMethods(int[] cursor, int count) {
            int methodIdx = 0;
            for (int i = 0; i < count; i++) {
                methodIdx += uleb(cursor);
                uleb(cursor);
                int codeOff = uleb(cursor);
                if (codeOff > 0 && scanKillProcessCode(codeOff)) return true;
            }
            return false;
        }

        private boolean scanWhitelist(int codeOff) {
            int insnsSize = uint(codeOff + 12);
            int insnsOff = codeOff + 16;
            int end = insnsOff + insnsSize * 2;
            for (int off = insnsOff; off + 1 < end && off + 1 < data.length; off += 2) {
                int op = data[off] & 0xff;
                if (op == 0x1a && off + 3 < end) {
                    if (whitelist.contains(string(ushort(off + 2)))) return true;
                } else if (op == 0x1b && off + 5 < end) {
                    if (whitelist.contains(string(uint(off + 2)))) return true;
                }
            }
            return false;
        }

        private boolean scanKillProcessCode(int codeOff) {
            int insnsSize = uint(codeOff + 12);
            int insnsOff = codeOff + 16;
            int end = insnsOff + insnsSize * 2;
            for (int off = insnsOff; off + 3 < end && off + 3 < data.length; off += 2) {
                int op = data[off] & 0xff;
                if (op >= 0x6e && op <= 0x72 && isKillProcess(ushort(off + 2))) return true;
            }
            return false;
        }

        private void skipFields(int[] cursor, int count) {
            for (int i = 0; i < count; i++) {
                uleb(cursor);
                uleb(cursor);
            }
        }

        private boolean isKillProcess(int methodIdx) {
            if (methodIdx < 0 || methodIdx >= methodIdsSize) return false;
            return "Landroid/os/Process;".equals(methodClass(methodIdx)) && "killProcess".equals(methodName(methodIdx));
        }

        private String methodClass(int methodIdx) {
            return typeDesc(ushort(methodIdsOff + methodIdx * 8));
        }

        private String methodName(int methodIdx) {
            return string(uint(methodIdsOff + methodIdx * 8 + 4));
        }

        private String typeDesc(int typeIdx) {
            if (typeIdx < 0 || typeIdx >= typeIdsSize) return "";
            return string(uint(typeIdsOff + typeIdx * 4));
        }

        private String string(int stringIdx) {
            if (stringIdx < 0 || stringIdx >= stringIdsSize) return "";
            int[] cursor = new int[]{uint(stringIdsOff + stringIdx * 4)};
            uleb(cursor);
            int start = cursor[0];
            int end = start;
            while (end < data.length && data[end] != 0) end++;
            try {
                return new String(data, start, end - start, "UTF-8");
            } catch (Throwable ignored) {
                return "";
            }
        }

        private int uleb(int[] cursor) {
            int result = 0;
            int shift = 0;
            while (cursor[0] < data.length) {
                int b = data[cursor[0]++] & 0xff;
                result |= (b & 0x7f) << shift;
                if ((b & 0x80) == 0) break;
                shift += 7;
            }
            return result;
        }

        private int ushort(int off) {
            if (off < 0 || off + 1 >= data.length) return 0;
            return (data[off] & 0xff) | ((data[off + 1] & 0xff) << 8);
        }

        private int uint(int off) {
            if (off < 0 || off + 3 >= data.length) return 0;
            return (data[off] & 0xff)
                    | ((data[off + 1] & 0xff) << 8)
                    | ((data[off + 2] & 0xff) << 16)
                    | ((data[off + 3] & 0xff) << 24);
        }
    }

    private static class Whitelist {

        private static final String AES_KEY = "1234123412341234";
        private final String packageName;

        Whitelist(String packageName) {
            this.packageName = packageName;
        }

        boolean contains(String value) {
            if (TextUtils.isEmpty(packageName) || TextUtils.isEmpty(value)) return false;
            if (packageName.equals(value) || containsItem(value)) return true;
            return containsItem(decrypt(value));
        }

        private boolean containsItem(String text) {
            if (TextUtils.isEmpty(text)) return false;
            int start = 0;
            while (start <= text.length()) {
                int end = text.indexOf(',', start);
                if (end < 0) end = text.length();
                if (packageName.equals(text.substring(start, end).trim())) return true;
                start = end + 1;
            }
            return false;
        }

        private String decrypt(String value) {
            if (!isCipherText(value)) return "";
            try {
                byte[] key = AES_KEY.getBytes("UTF-8");
                Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
                cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new IvParameterSpec(key));
                return new String(cipher.doFinal(Base64.decode(value, Base64.DEFAULT)), "UTF-8");
            } catch (Throwable ignored) {
                return "";
            }
        }

        private boolean isCipherText(String value) {
            int len = value.length();
            if (len < 24 || len % 4 != 0) return false;
            int padding = 0;
            for (int i = 0; i < len; i++) {
                char c = value.charAt(i);
                if (c == '=') {
                    padding++;
                    if (i < len - 2) return false;
                } else if (!isBase64(c)) {
                    return false;
                }
            }
            int rawLen = len * 3 / 4 - padding;
            return rawLen > 0 && rawLen % 16 == 0;
        }

        private boolean isBase64(char c) {
            return (c >= 'A' && c <= 'Z')
                    || (c >= 'a' && c <= 'z')
                    || (c >= '0' && c <= '9')
                    || c == '+'
                    || c == '/';
        }
    }
}
