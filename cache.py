# -*- coding: utf-8 -*-
"""轻量磁盘缓存(JSON 值):供大模型结果 / PDF 解析文本跨会话复用。

为什么需要:Streamlit 的 st.session_state 只属于单个浏览器会话,
同一容器里其它人(或你换浏览器)访问同一份年报时会全部重算。把耗时结果
落盘到共享目录后,同一公司/同一 prompt 只算一次,之后秒回。

- 目录:优先环境变量 AR_CACHE_DIR,否则系统临时目录下的 ar_risk_cache
- 线程安全:写入先落临时文件再原子替换;并发读到旧值无害
- 自动清理:写入时超过条数上限或总字节上限则删除最旧条目
"""
import hashlib
import json
import os
import tempfile
import threading
import time

_LOCK = threading.Lock()
_DEFAULT_CAP = 500          # 默认最大条数
_DEFAULT_MAX_MB = 400.0     # 默认最大总占用(MB)


def cache_root() -> str:
    d = os.getenv("AR_CACHE_DIR", "").strip()
    if not d:
        d = os.path.join(tempfile.gettempdir(), "ar_risk_cache")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _ns_dir(ns: str) -> str:
    ns = "".join(c for c in str(ns) if c.isalnum() or c in "_-") or "default"
    d = os.path.join(cache_root(), ns)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def key_of(*parts) -> str:
    """任意输入 -> 稳定的 sha256 键。"""
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8", "ignore"))
        h.update(b"\x00")
    return h.hexdigest()


def _path(ns: str, key: str) -> str:
    return os.path.join(_ns_dir(ns), key + ".json")


def get(ns: str, key: str, ttl_days: float = 30.0):
    """命中且未过期返回 value,否则 None。任何异常按未命中处理。"""
    try:
        p = _path(ns, key)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            rec = json.load(f)
        if rec.get("k") != key:
            return None
        if ttl_days and time.time() - rec.get("t", 0) > ttl_days * 86400:
            return None
        return rec.get("v")
    except Exception:
        return None


def put(ns: str, key: str, value, ttl_days: float = 30.0) -> None:
    """原子写入(临时文件 + os.replace),随后按需清理。失败静默。"""
    tmp = None
    try:
        d = _ns_dir(ns)
        tmp = os.path.join(d, key + ".tmp" + str(os.getpid()))
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"k": key, "t": time.time(), "v": value},
                      f, ensure_ascii=False)
        os.replace(tmp, _path(ns, key))
        _prune(d)
    except Exception:
        pass
    finally:
        if tmp:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _prune(d: str) -> None:
    """目录内条目数/总字节超限时删最旧(非阻塞加锁,避免多会话同时清理)。"""
    cap = _env_int("AR_CACHE_MAX", _DEFAULT_CAP)
    max_mb = _env_float("AR_CACHE_MAX_MB", _DEFAULT_MAX_MB)
    if not _LOCK.acquire(blocking=False):
        return
    try:
        try:
            files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")]
        except OSError:
            return
        if len(files) <= cap:
            return
        files.sort(key=lambda f: os.path.getmtime(f))
        # 条数超限:删到 cap 的 80%
        over_n = files[: max(0, len(files) - int(cap * 0.8))]
        # 体积超限:从最旧开始删,直到总占用 < max_mb*0.6
        total = sum(os.path.getsize(f) for f in files)
        need_del = total - max_mb * 1024 * 1024 * 0.6
        drop = set(over_n)
        for f in files:
            if need_del <= 0:
                break
            drop.add(f)
            try:
                need_del -= os.path.getsize(f)
            except OSError:
                pass
        for f in drop:
            try:
                os.remove(f)
            except OSError:
                pass
    except Exception:
        pass
    finally:
        _LOCK.release()
