# FreeNotes Outline Skill

这是一个给 Codex 使用的 FreeNotes 辅助 Skill，用来检查 FreeNotes 导出的 `.freenotes` 文件、从 PDF 目录提取大纲，并安全地写入 FreeNotes 内部的大纲/书签结构。

## 安装方式

在 Codex 里让它安装这个 GitHub 路径：

```text
Install https://github.com/Tiomehsh/freenotes-outline-skill/tree/main/skills/freenotes-outline
```

也可以直接运行 Codex 自带的 skill 安装脚本：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo Tiomehsh/freenotes-outline-skill --path skills/freenotes-outline
```

安装完成后，重启 Codex 才会识别新 Skill。

## 主要用途

- 检查 `.freenotes` 包里的 FreeNotes 文档结构。
- 从 FreeNotes 内置 PDF 文本索引里提取目录。
- 对扫描版 PDF 使用 OCR 辅助提取目录。
- 把整理后的目录写回 FreeNotes 大纲。
- 修改 `.freenotes` 文件前默认创建备份。

## 使用提示

安装后，可以把 `.freenotes` 文件交给 Codex，然后说类似这样的话：

```text
帮我检查这个 FreeNotes 文件，提取目录并写入大纲。
```

如果 PDF 是扫描版，OCR 需要本机安装 `mutool` 和 Tesseract。中文扫描件通常还需要 Tesseract 的中文语言包，例如 `chi_sim`。

## 依赖

- Python 3。
- 文本型 PDF 通常不需要额外 OCR 工具，Skill 会优先读取 FreeNotes 的 `index.db`。
- 扫描版 PDF 需要 `mutool` 和 Tesseract，除非你提供自定义 OCR 命令。
