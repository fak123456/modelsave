# V16 交接包与 FLUX3 蒸馏模型备份

本仓库保存用户指定的两个文件，合计 **8,973,675,900 字节（约 8.97GB）**：

| 内容 | 大小 | 恢复后的文件名 |
| --- | ---: | --- |
| 原始交接 ZIP，代码、素材、结果、提示词、安装说明 | 3,145,801,121 字节 | `FLUX3蒸馏版_27B扩写_交接包_20261018.zip` |
| FLUX3 蒸馏版 INT8 模型权重 | 5,827,874,779 字节 | `flux3_image_klein_sd_int8_convrot.safetensors` |

[打开完整下载页面](https://github.com/fak123456/modelsave/releases/tag/v16-handoff-20261019)

大文件位于同仓库 Releases，按 1GiB 分成 9 片。Git 主分支保存清单、下载工具和说明。GitHub 的 **Code → Download ZIP** 只下载这些小文件；完整交接内容必须从 Releases 获取。

## 下次下载

先安装 Python 3.12，下载或克隆本仓库，然后在仓库目录运行：

```powershell
git clone https://github.com/fak123456/modelsave.git
cd modelsave
python tools/download_backup.py --only handoff --dest C:/V16_Download
```

上面的命令仅下载交接包，方便先看代码和比较效果；需要模型时再运行：

```powershell
python tools/download_backup.py --only model --dest C:/V16_Download
```

也可以用 `--only all` 一次下载两项。下载器会验证每片和最终文件的 SHA256，再恢复原始文件名；已校验分片会跳过，网络中断后重跑同一命令即可续传。解包后会额外占用约 3.23GB，下载和合并期间应保留足够空间，建议空闲至少 22GB。

## 查看结果与恢复程序

1. 解压恢复的交接 ZIP，打开包内 `results/查看对照.html`，无需模型即可离线比较 72 张固定提示词基准图与 72 张 27B 原样扩写新图。
2. 阅读包内 `00_先读这个.txt`、`01_CODEX_HANDOFF.txt` 和 `02_新电脑安装与显卡适配.txt`。本仓库 `docs/` 也保留这三份原说明。
3. 按说明安装 Python 3.12.10、PyTorch 2.10.0+cu128、固定版 ComfyUI 及 llama.cpp。**原始交接包没有已安装环境**；本次没有额外上传 Python/venv、驱动、27B、Base 或其他模型。
4. 将恢复的蒸馏模型放到新项目 `runtime/v16_comfy/models/diffusion_models/`。
5. 包内 `models/model_downloads.json` 记录当前路线其余必需文件的固定下载地址与 SHA256：Qwen3VL 文本编码器、VAE、27B GGUF 和视觉投影。这些仍需从官方来源另行下载，授权令牌只在新电脑本地使用。
6. 原程序有旧 C/D 盘路径和来源批次绑定，先在新目录适配路径和模型清单，再运行包内环境探测、相关测试与小批量验证。不要直接续跑旧批次。

交接 ZIP 原样保存，内部“模型未打包”说明指 ZIP 自身；本 Release 另外提供一份蒸馏模型。完整性检查不等于新显卡推理适配或人工视觉验收。

## 校验与来源

- 交接 ZIP SHA256：`c6b17c4a7e612d633ea50b0cfc83bb8e0867e37f2f35fef6e80e8da4b89facfb`
- 蒸馏模型 SHA256：`847d8933548afd93df4af2cac2498e70891bf28d9dae06d695f536992e168fe2`
- 全部分片长度、顺序、SHA256 与下载链接：`backup_manifest.json`；纯文本清单：`SHA256SUMS.txt`。
- 模型来自 [Black Forest Labs 官方仓库](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy)，固定 revision `5c9b714851dc072b04a23ef6d2d36421f5ccb3a0`，没有更名或重新量化。
- 模型使用原始 [FLUX Kommunity License](licenses/FLUX_LICENSE.md)，并附 [归属声明](licenses/FLUX_NOTICE.txt)。本仓库不为第三方模型重新授予许可。

如果手工下载了所有分片，可运行以下命令合并并验证：

```powershell
python tools/download_backup.py --local-parts C:/V16_Parts --dest C:/V16_Download
```

不写入合并文件、仅检查现有分片及整文件摘要：

```powershell
python tools/download_backup.py --local-parts C:/V16_Parts --verify-only
```
