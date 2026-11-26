r"""给 ComfyUI-Easy-Use 打 IPAdapter 缓存补丁（幂等，可重复执行）。

修的问题：`easy ipadapterApply` 的 load_model 在"缓存命中"分支里只回填了
`pipeline['ipadapter']['model']`，漏了 `['file']`。第二个适配器节点（我们的
scene_ipadapter_dual.json 里 31 号，`optional_ipadapter:["30",3]`）复用该
pipeline 时，`get_lora_pattern(pipeline['ipadapter']['file'])` 拿到 None：

    TypeError: expected str, bytes or os.PathLike object, not NoneType
    [ComfyUI-Easy-Use/py/nodes/adapter.py:459 in get_lora_pattern]

双 IPA（有人镜 + 场景锚图，或双人镜）几乎必踩，表现为"IPAdapter 失败"。

用法：python scripts/patch_easy_use_ipadapter.py [adapter.py 路径]
默认路径取 D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\ComfyUI-Easy-Use\py\nodes\adapter.py
"""
import sys
from pathlib import Path

DEFAULT = Path(r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes"
               r"\ComfyUI-Easy-Use\py\nodes\adapter.py")

ANCHOR = """                log_node_info("easy ipadapterApply", f"Using IpAdapterModel {ipadapter_name} Cached")
                _, ipadapter = backend_cache.cache[ipadapter_name][1]"""

PATCH = """
                # [drama-studio patch] 缓存命中也要记文件路径：下游节点用 optional_ipadapter
                # 复用本 pipeline 时，load_model 会读 pipeline['ipadapter']['file'] 算 lora_pattern，
                # 漏记就是 TypeError: expected str, bytes or os.PathLike object, not NoneType
                pipeline['ipadapter']['file'] = ipadapter_file"""


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not target.exists():
        print(f"[patch] 找不到 {target}")
        return 2
    src = target.read_text(encoding="utf-8")
    if "[drama-studio patch]" in src:
        print("[patch] 已打过补丁，跳过（幂等）")
        return 0
    if ANCHOR not in src:
        print("[patch] 锚点未命中：Easy-Use 版本可能已变，请人工确认缓存分支")
        return 3
    src = src.replace(ANCHOR, ANCHOR + PATCH, 1)
    # 备份一份（首次打补丁时）
    bak = target.with_suffix(".py.bak")
    if not bak.exists():
        bak.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[patch] 已备份 -> {bak.name}")
    target.write_text(src, encoding="utf-8")
    print(f"[patch] 补丁已写入 {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
