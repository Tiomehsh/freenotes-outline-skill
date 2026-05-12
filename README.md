# FreeNotes Outline Skill

这是一个面向支持 Skill 机制的 AI Agent 的 FreeNotes 辅助 Skill，用来检查 FreeNotes 导出的 `.freenotes` 文件、从 PDF 目录提取大纲，并安全地写入 FreeNotes 内部的大纲/书签结构。

核心 Skill 位于：

```text
skills/freenotes-outline/
```

只要你的 Agent 能读取 `SKILL.md`，并能使用同目录下的 `scripts/` 和 `references/` 资源，就可以使用这个 Skill。`agents/openai.yaml` 是面向 OpenAI/Codex 类界面的展示元数据；不支持该文件的 Agent 可以忽略它。

## 安装方式

如果你的 Agent 支持从 GitHub 路径安装 Skill，可以让它安装这个路径：

```text
Install https://github.com/Tiomehsh/freenotes-outline-skill/tree/main/skills/freenotes-outline
```

如果你使用 Codex，也可以直接运行 Codex 自带的 Skill 安装脚本：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo Tiomehsh/freenotes-outline-skill --path skills/freenotes-outline
```

如果你的 Agent 没有 GitHub 安装器，可以手动下载仓库，然后把 `skills/freenotes-outline/` 复制到该 Agent 的本地 Skill 目录：

```bash
git clone https://github.com/Tiomehsh/freenotes-outline-skill.git
cp -R freenotes-outline-skill/skills/freenotes-outline <your-agent-skills-dir>/
```

安装完成后，通常需要重启对应的 Agent 才会识别新 Skill。

## 主要用途

- 检查 `.freenotes` 包里的 FreeNotes 文档结构。
- 从 FreeNotes 内置 PDF 文本索引里提取目录。
- 对扫描版 PDF 使用 OCR 辅助提取目录。
- 把整理后的目录写回 FreeNotes 大纲。
- 修改 `.freenotes` 文件前默认创建备份。

## 使用提示

安装后，可以把 `.freenotes` 文件交给 Agent，然后说类似这样的话：

```text
请使用 freenotes-outline Skill，帮我检查这个 FreeNotes 文件，提取目录并写入大纲。
```

如果 PDF 是扫描版，OCR 需要本机安装 `mutool` 和 Tesseract。中文扫描件通常还需要 Tesseract 的中文语言包，例如 `chi_sim`。

## 依赖

- Python 3。
- 文本型 PDF 通常不需要额外 OCR 工具，Skill 会优先读取 FreeNotes 的 `index.db`。
- 扫描版 PDF 需要 `mutool` 和 Tesseract，除非你提供自定义 OCR 命令。
