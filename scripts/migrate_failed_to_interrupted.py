"""把「环境原因导致被打断」的历史 failed 任务迁移为 interrupted。

背景：后端每次重启会把遗留 running/pending 收尸；旧逻辑标 failed，导致队列里
堆积大量红色失败记录（实测 45 条 failed 里 24 条是收尸产物），而它们其实
只是被重启/离线打断，点「继续」按原参数重跑即可，不是代码错误。

用法：
    python scripts/migrate_failed_to_interrupted.py            # 只打印，不改库
    python scripts/migrate_failed_to_interrupted.py --apply    # 实际写入
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "drama_studio.sqlite3"

# 语义：任务本身没问题，是运行环境断了（重启 / 离线 / ComfyUI 不可达 / 轮询挂起）
PATTERNS = (
    "进程重启中断",
    "机器离线",
    "环境离线",
    "All connection attempts failed",
    "轮询偶发挂起",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写库；默认仅预览")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "select id, type, substr(coalesce(error,''),1,50) from tasks where status='failed' order by id"
    ).fetchall()

    hits = [(i, t, e) for (i, t, e) in rows if any(p in e for p in PATTERNS)]
    print(f"failed total={len(rows)}  env-interrupted matches={len(hits)}")
    for i, t, e in hits:
        print(f"  #{i} {t}: {e}")

    if not args.apply:
        print("\n(dry-run) 加 --apply 才会写库")
        return 0

    ids = [i for (i, _, _) in hits]
    if ids:
        conn.executemany(
            "update tasks set status='interrupted' where id=? and status='failed'",
            [(i,) for i in ids],
        )
        conn.commit()
        print(f"\nupdated {len(ids)} rows -> interrupted")

    counts = conn.execute("select status,count(*) from tasks group by status").fetchall()
    print("status counts:", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
