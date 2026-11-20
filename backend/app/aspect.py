"""全局画幅比例：项目级设置，统一驱动资产图与分镜帧的分辨率。

两个桶系：
- ASSET_BUCKETS：场景/道具等资产图，用 SDXL 官方分辨率桶（约 1MP，长边 1344 上限），
  flux2 的 EmptyFlux2LatentImage 也接受这些值（均为 32 的倍数）。
- SHOT_BUCKETS：分镜首尾帧/宫格，走 IPA 锁脸通道。实测 IPA 宽画布（1216x832）
  会把单人复制成多人，所以横幅压住长边 ≤832，纵向沿用已验证的 480x832 基准。
角色定妆照/三视图固定竖版，不参与全局画幅。
"""

ASPECT_CHOICES = ("16:9", "21:9", "4:3", "1:1", "3:4", "9:16")

ASSET_BUCKETS = {
    "16:9": (1344, 768),
    "21:9": (1536, 640),
    "4:3":  (1152, 896),
    "1:1":  (1024, 1024),
    "3:4":  (896, 1152),
    "9:16": (768, 1344),
}

SHOT_BUCKETS = {
    "16:9": (832, 468),
    "21:9": (832, 360),
    "4:3":  (832, 624),
    "1:1":  (640, 640),
    "3:4":  (624, 832),
    "9:16": (480, 832),
}


def normalize_aspect(value: str | None) -> str:
    v = (value or "").strip()
    return v if v in ASPECT_CHOICES else "9:16"


def asset_dims(aspect: str | None) -> tuple[int, int]:
    """场景/道具资产图分辨率（按项目全局画幅）。"""
    return ASSET_BUCKETS[normalize_aspect(aspect)]


def shot_dims(aspect: str | None) -> tuple[int, int]:
    """分镜首尾帧/宫格分辨率（按项目全局画幅，IPA 通道压长边）。"""
    return SHOT_BUCKETS[normalize_aspect(aspect)]
