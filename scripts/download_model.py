"""
============================================================
预下载 Embedding 模型（从 ModelScope，国内可访问）
============================================================
HuggingFace Hub 在国内被墙，此脚本通过 ModelScope 下载模型文件
到本地目录，并补全 sentence-transformers 4.x 所需的配置文件，
供 sentence-transformers / HuggingFaceEmbeddings 直接加载。

使用方式：
    python scripts/download_model.py
    python scripts/download_model.py --model BAAI/bge-small-zh-v1.5 --output /app/models/bge-small-zh-v1.5
"""
import sys
import json
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))


def download_from_modelscope(model_id: str, output_dir: Path):
    """从 ModelScope 下载模型文件并补全兼容性配置。"""
    from modelscope.hub.snapshot_download import snapshot_download

    print(f"[1/3] 从 ModelScope 下载模型: {model_id}")
    print(f"      目标目录: {output_dir}")

    # 如果 output_dir 已有文件，跳过下载
    if output_dir.exists() and any(output_dir.iterdir()):
        # 但检查是否需要补全 config
        need_fix = not (output_dir / "1_Pooling" / "config.json").exists()
        if not need_fix:
            print("      模型文件已存在且完整，跳过。")
            return
        print("      模型文件存在，但需要补全配置...")

    # ModelScope 的 snapshot_download 会自动处理缓存和断点续传
    cache_dir = snapshot_download(
        model_id=model_id,
        cache_dir=output_dir.parent,
    )

    # 将 ModelScope 缓存目录内容完整复制到 output_dir
    if cache_dir != str(output_dir) and not output_dir.exists():
        print(f"[2/3] 复制模型文件...")
        import shutil
        cache_path = Path(cache_dir)

        # 复制所有文件和子目录
        def copy_recursive(src: Path, dst: Path):
            dst.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                dest = dst / item.name
                if item.is_dir():
                    copy_recursive(item, dest)
                elif item.is_file() and not dest.exists():
                    shutil.copy2(item, dest)
                    print(f"      {item.relative_to(cache_path)}")

        copy_recursive(cache_path, output_dir)

    # 补全 sentence-transformers 4.x 需要的模块配置
    fix_model_config(output_dir)

    print(f"\n模型下载完成 → {output_dir}")


def fix_model_config(model_dir: Path):
    """补全 sentence-transformers 4.x 兼容的配置文件。

    ModelScope 上的旧模型缺少子模块的 config.json，
    而 sentence-transformers 4.x 要求每个模块目录必须有 config.json。
    """
    print(f"[3/3] 补全 sentence-transformers 4.x 兼容配置...")

    # 读取 modules.json 确定有哪些模块
    modules_path = model_dir / "modules.json"
    if not modules_path.exists():
        print("      未找到 modules.json，跳过。")
        return

    modules = json.loads(modules_path.read_text(encoding="utf-8"))

    # 读取模型配置获取 embedding_dimension
    config_path = model_dir / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        config_path = model_dir / "configuration.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

    hidden_size = config.get("hidden_size", 384)

    for mod in modules:
        mod_path_str = mod.get("path", "")
        mod_type = mod.get("type", "")

        if not mod_path_str:
            continue

        mod_dir = model_dir / mod_path_str
        mod_dir.mkdir(parents=True, exist_ok=True)

        config_file = mod_dir / "config.json"
        if config_file.exists():
            continue  # 已有配置，跳过

        # 根据模块类型生成默认配置
        if "Pooling" in mod_type:
            pooling_config = {
                "word_embedding_dimension": hidden_size,
                "pooling_mode_cls_token": False,
                "pooling_mode_mean_tokens": True,
                "pooling_mode_max_tokens": False,
                "pooling_mode_mean_sqrt_len_tokens": False,
            }
            config_file.write_text(
                json.dumps(pooling_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"      + {mod_path_str}/config.json (Pooling, dim={hidden_size})")
        elif "Normalize" in mod_type:
            normalize_config = {}
            config_file.write_text(
                json.dumps(normalize_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"      + {mod_path_str}/config.json (Normalize)")
        elif "Transformer" in mod_type:
            # Transformer 模块不需要单独的 config.json（引用根目录 config.json）
            pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="从 ModelScope 预下载 Embedding 模型")
    parser.add_argument(
        "--model",
        default="BAAI/bge-small-zh-v1.5",
        help="ModelScope 模型 ID（默认：BAAI/bge-small-zh-v1.5）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出目录（默认：/app/models/bge-small-zh-v1.5）",
    )
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else Path("/app/models") / args.model.split("/")[-1]

    download_from_modelscope(args.model, output_dir)


if __name__ == "__main__":
    main()
