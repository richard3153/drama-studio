"""ComfyUI 适配器（D 范式为主 + B 局部覆盖为辅）。

D 范式：加载 API 格式 workflow JSON 模板 → 按 class_type 结构化定位关键节点
       （Loader / KSampler / SaveImage，prompt 节点经 KSampler 输入引用解析）
       → 结构化替换参数 → POST /prompt → 轮询 /history → /view 下载产物。
B 能力：OverrideSpec 支持任意 class_type 参数覆盖（运行时换模型档、改分辨率等）。

OverrideSpec 语法（值 = None 表示删除该输入键）：
  "CheckpointLoaderSimple.ckpt_name": "xxx.safetensors"
  "positive_text": "..."        # 自动解析 KSampler.positive 引用的 CLIPTextEncode
  "negative_text": "..."
  "KSampler.seed": 123
  "EmptyLatentImage.width": 832
  "EmptyLatentImage.batch_size": None
  "positive_text@1": "..."      # 多个同类节点时按索引
"""
import asyncio
import json
import random
import uuid
from pathlib import Path

import httpx

from ..config import COMFYUI_URL, WORKFLOW_DIR

# ComfyUI 常见节点角色映射（结构化定位用）
SAMPLERS = {"KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"}
IMAGE_SAVERS = {"SaveImage", "SaveImageWebsocket", "SaveAnimatedWEBP", "VHS_VideoCombine"}
AUDIO_SAVERS = {"SaveAudio", "SaveAudioMP3", "SaveAudioOpus", "SaveAudioFlac"}
VIDEO_SAVERS = {"SaveVideo", "SaveWEBM", "SaveAnimatedWEBP"}
LOADERS = {"CheckpointLoaderSimple", "CheckpointLoader", "UnetLoaderGGUF",
           "CLIPLoader", "CLIPLoaderGGUF", "VAELoader", "LoraLoader"}


class ComfyUIError(RuntimeError):
    pass


class ComfyUIAdapter:
    def __init__(self, base_url: str = COMFYUI_URL):
        self.base = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    # ---------- 模板加载与解析（D 范式） ----------

    @staticmethod
    def load_template(name: str) -> dict:
        p = WORKFLOW_DIR / name
        if not p.exists():
            raise FileNotFoundError(f"workflow 模板不存在: {p}")
        wf = json.loads(p.read_text(encoding="utf-8"))
        if "nodes" in wf and "links" in wf:
            raise ValueError("这是 UI 格式工作流，请在 ComfyUI 用『导出(API)』保存 API 格式")
        return wf

    @staticmethod
    def index_by_class(wf: dict) -> dict[str, list[str]]:
        idx: dict[str, list[str]] = {}
        for nid, node in wf.items():
            idx.setdefault(node.get("class_type", ""), []).append(nid)
        return idx

    @staticmethod
    def _resolve_prompt_nodes(wf: dict, idx: dict) -> tuple[str | None, str | None]:
        """从任一 KSampler 的 positive/negative 输入引用解析出提示词节点 id。
        Wan 双帧链路里 sampler 的 conditioning 来自 WanFirstLastFrameToVideo，
        需要顺着 link 继续往回找真正的 CLIPTextEncode（条件节点本身没有文本字段）。"""
        pos = neg = None
        for cls in SAMPLERS:
            for nid in idx.get(cls, []):
                ref = wf[nid].get("inputs", {}).get("positive")
                if isinstance(ref, list) and ref:
                    pos = ref[0]
                ref = wf[nid].get("inputs", {}).get("negative")
                if isinstance(ref, list) and ref:
                    neg = ref[0]
                if pos or neg:
                    return (ComfyUIAdapter._walk_to_text(wf, pos, "positive"),
                            ComfyUIAdapter._walk_to_text(wf, neg, "negative"))
        return pos, neg

    @staticmethod
    def _walk_to_text(wf: dict, nid: str | None, prefer: str = "positive",
                      depth: int = 0) -> str | None:
        """顺着 conditioning 链路找到带文本字段的节点（最多 4 层）。
        prefer 决定优先沿 positive 还是 negative 的 link 走，避免正负两类
        条件都被解析到同一个文本节点。"""
        if not nid or depth > 4 or nid not in wf:
            return nid
        node = wf[nid]
        inputs = node.get("inputs", {})
        for f in ("text", "prompt", "positive", "negative"):
            v = inputs.get(f)
            if isinstance(v, str):
                return nid
        order = [prefer] + [k for k in ("positive", "negative", "conditioning",
                                        "conditioning_1", "conditioning_2")
                            if k != prefer]
        for f in order:
            v = inputs.get(f)
            if isinstance(v, list) and v:
                found = ComfyUIAdapter._walk_to_text(wf, v[0], prefer, depth + 1)
                if found:
                    return found
        return nid

    # 提示词节点可能出现的文本字段（QwenImage 系用 prompt/negative_prompt）
    PROMPT_FIELDS_POS = ("text", "prompt", "positive")
    PROMPT_FIELDS_NEG = ("text", "negative_prompt", "negative")

    @classmethod
    def _set_prompt(cls, node: dict, value: str, fields: tuple[str, ...]):
        for f in fields:
            if f in node.get("inputs", {}):
                node["inputs"][f] = value
                return True
        # 兜底：写入第一个字符串型输入
        for k, v in node.get("inputs", {}).items():
            if isinstance(v, str):
                node["inputs"][k] = value
                return True
        return False

    # 潜空间节点别名：不同底模家族用不同 EmptyLatent 节点，
    # 业务层统一写 "EmptyLatentImage.width"，这里按家族自动映射
    LATENT_ALIASES = {
        "EmptyLatentImage": ("EmptyLatentImage", "EmptyFlux2LatentImage", "EmptySD3LatentImage"),
    }

    def apply_overrides(self, wf: dict, overrides: dict) -> dict:
        """D 范式核心：按 class_type 结构化覆盖，不依赖节点编号。"""
        idx = self.index_by_class(wf)
        pos_id, neg_id = self._resolve_prompt_nodes(wf, idx)

        for key, value in overrides.items():
            key = key.strip()
            if key == "positive_text":
                if not pos_id:
                    raise ComfyUIError("模板中未找到 KSampler→positive 提示词节点")
                if not self._set_prompt(wf[pos_id], value, self.PROMPT_FIELDS_POS):
                    raise ComfyUIError(f"提示词节点 {wf[pos_id]['class_type']} 无文本字段")
                continue
            if key == "negative_text":
                if not neg_id:
                    raise ComfyUIError("模板中未找到 KSampler→negative 提示词节点")
                if not self._set_prompt(wf[neg_id], value, self.PROMPT_FIELDS_NEG):
                    raise ComfyUIError(f"提示词节点 {wf[neg_id]['class_type']} 无文本字段")
                continue

            if "@" in key:
                # 格式：Class@序号.字段（如 UnetLoaderGGUF@1.unet_name）
                cls, rest = key.split("@", 1)
                sel, _, field = rest.partition(".")
                n = int(sel or 0)
            else:
                cls, field = key.split(".", 1) if "." in key else (key, "")
                n = 0

            ids = idx.get(cls)
            if not ids and cls in self.LATENT_ALIASES:
                # 家族别名：EmptyLatentImage → EmptyFlux2LatentImage 等
                for alias in self.LATENT_ALIASES[cls]:
                    if alias in idx:
                        cls, ids = alias, idx[alias]
                        break
            if not ids:
                raise ComfyUIError(f"模板中不存在节点 class_type={cls}")
            nid = ids[n] if n < len(ids) else ids[-1]
            node_inputs = wf[nid]["inputs"]
            if field and field not in node_inputs:
                raise ComfyUIError(f"节点 {cls} 无输入字段 {field}（现有: {list(node_inputs)}）")
            if field:
                if value is None:
                    node_inputs.pop(field, None)
                else:
                    node_inputs[field] = value
            else:
                node_inputs.update(value or {})
        return wf

    # ---------- 执行 ----------

    async def _abort_prompt(self, prompt_id: str):
        """放弃等待时把 ComfyUI 侧一起收尾：pending 删掉，正在跑就中断。

        没有这步就是本轮"任务停住"的根因：adapter 超时/失联抛错后，ComfyUI 仍在
        算那个没人等的 prompt（8G 上一条 H3 视频 15-30 分钟），后端又提交下一个
        → 队列越堆越深、GPU 一直 100%、每个请求都把排队时间算进自己的超时预算，
        于是首帧 900s 永远不够，永远超时、永远不落终态。
        """
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{self.base}/queue", json={"delete": [prompt_id]})
                q = (await c.get(f"{self.base}/queue")).json()
                running = [it[1] for it in q.get("queue_running", [])]
                if prompt_id in running:
                    await c.post(f"{self.base}/interrupt")
        except Exception:
            pass

    async def purge_queue(self) -> int:
        """清空 ComfyUI 队列（中断当前执行 + 删所有 pending），返回清掉的条数。

        只在"后端没有任何正在跑的任务"时调用（进程刚重启、DB 已全部收尸为
        interrupted），此时队列里的 prompt 一定没人认领。
        """
        cleared = 0
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                q = (await c.get(f"{self.base}/queue")).json()
                pend = [it[1] for it in q.get("queue_pending", [])]
                run = [it[1] for it in q.get("queue_running", [])]
                if run:
                    await c.post(f"{self.base}/interrupt")
                    cleared += len(run)
                if pend:
                    await c.post(f"{self.base}/queue", json={"delete": pend})
                    cleared += len(pend)
        except Exception:
            pass
        return cleared

    async def run(self, wf: dict, *, filename_prefix: str = "drama_studio/out",
                  save_root: str | Path = "data/downloads",
                  timeout: float = 900.0, poll_interval: float = 1.0,
                  on_stage=None) -> list[Path]:
        """提交并等待完成，下载输出文件，返回本地路径列表。"""
        self.save_root = Path(save_root)
        # 提交用：连接短超时、读宽松（ComfyUI 忙时响应可能数分钟才回）
        submit_to = httpx.Timeout(30, read=300.0)
        # 轮询用：读超时放宽 + 循环内容错，单次慢响应不杀任务
        poll_to = httpx.Timeout(30, read=600.0)
        async with httpx.AsyncClient(timeout=submit_to) as c:
            wf_json = json.dumps(wf)
            # 注入 SaveImage 输出目录前缀（D 范式定位 saver 节点）
            for cls in IMAGE_SAVERS | AUDIO_SAVERS | VIDEO_SAVERS:
                for nid in self.index_by_class(wf).get(cls, []):
                    wf[nid]["inputs"]["filename_prefix"] = filename_prefix

            payload = {"prompt": wf, "client_id": self.client_id}
            r = await c.post(f"{self.base}/prompt", json=payload)
            if r.status_code != 200:
                raise ComfyUIError(f"/prompt 失败 {r.status_code}: {r.text[:500]}")
            prompt_id = r.json()["prompt_id"]

            if on_stage:
                on_stage(f"已提交 ComfyUI 任务 {prompt_id[:8]}，等待执行")

            deadline = asyncio.get_event_loop().time() + timeout
            history = None
            poll_fail = 0
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(poll_interval)
                try:
                    async with httpx.AsyncClient(timeout=poll_to) as pc:
                        r = await pc.get(f"{self.base}/history/{prompt_id}")
                    poll_fail = 0
                except httpx.HTTPError:
                    # ComfyUI 重推理时偶发慢响应/瞬断，跳过本次轮询
                    poll_fail += 1
                    if poll_fail >= 60:
                        await self._abort_prompt(prompt_id)
                        raise ComfyUIError("轮询连续失败（约 60 次），疑似 ComfyUI 无响应")
                    continue
                data = r.json()
                if prompt_id in data:
                    entry = data[prompt_id]
                    status = entry.get("status", {})
                    if status.get("completed"):
                        history = entry
                        break
                    if status.get("status_str") == "error":
                        msgs = json.dumps(status.get("messages", []), ensure_ascii=False)
                        await self._abort_prompt(prompt_id)
                        raise ComfyUIError(f"ComfyUI 执行出错: {msgs[:800]}")
            if history is None:
                await self._abort_prompt(prompt_id)
                raise ComfyUIError(f"执行超时（{timeout}s）")

            return await self._download_outputs(c, history)

    async def _download_outputs(self, client: httpx.AsyncClient,
                                history_entry: dict) -> list[Path]:
        saved: list[Path] = []
        out_dir = Path(history_entry.get("prompt", [None, None, {}])[2]
                       .get("output_dir", ""))
        for node_out in history_entry.get("outputs", {}).values():
            for key in ("images", "audio", "gifs", "videos"):
                for item in node_out.get(key, []):
                    params = {
                        "filename": item["filename"],
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                    }
                    r = await client.get(f"{self.base}/view", params=params)
                    r.raise_for_status()
                    local = Path(self.save_root) / item["filename"]
                    local.parent.mkdir(parents=True, exist_ok=True)
                    local.write_bytes(r.content)
                    saved.append(local)
        return saved

    # ---------- 显存治理 ----------

    async def upload_image(self, path: str | Path, subfolder: str = "drama_studio_in") -> str:
        """上传本地图片到 ComfyUI input 目录，返回 LoadImage 可用的文件名。"""
        p = Path(path)
        async with httpx.AsyncClient(timeout=60) as c:
            with open(p, "rb") as f:
                r = await c.post(f"{self.base}/upload/image",
                                 files={"image": (p.name, f, "image/png")},
                                 data={"overwrite": "true", "subfolder": subfolder})
            r.raise_for_status()
            data = r.json()
            name = data["name"]
            sub = data.get("subfolder") or ""
            return f"{sub}/{name}" if sub else name

    async def upload_audio(self, path: str | Path, subfolder: str = "drama_studio_in") -> str:
        """上传本地音频到 ComfyUI input 目录，返回 LoadAudio 可用的文件名。
        新版 ComfyUI 有 /upload/audio；老版本 405/404 时退回直写 input 目录。"""
        p = Path(path)
        async with httpx.AsyncClient(timeout=60) as c:
            with open(p, "rb") as f:
                r = await c.post(f"{self.base}/upload/audio",
                                 files={"audio": (p.name, f, "audio/mpeg")},
                                 data={"overwrite": "true", "subfolder": subfolder})
            if r.status_code < 400:
                data = r.json()
                name = data["name"]
                sub = data.get("subfolder") or ""
                return f"{sub}/{name}" if sub else name
        # fallback：直写 ComfyUI input 目录（--input-directory 指向的共享目录）
        import shutil
        from ..config import COMFYUI_INPUT_DIR
        dest = Path(COMFYUI_INPUT_DIR) / subfolder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest / p.name)
        return f"{subfolder}/{p.name}"

    async def free_memory(self):
        """阶段结束调用 /free 卸载模型释放显存（低显存调度约束 3）。"""
        async with httpx.AsyncClient(timeout=30) as c:
            await c.post(f"{self.base}/free",
                         json={"unload_models": True, "free_memory": True})

    async def system_stats(self) -> dict:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.base}/system_stats")
            r.raise_for_status()
            return r.json()
