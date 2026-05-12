# FreeNotes Outline Skill

适用于支持 Skill 机制的 AI Agent，用于检查 FreeNotes 导出的 `.freenotes` 文件、提取 PDF 目录，并写入 FreeNotes 大纲。

## 安装

```text
Install https://github.com/Tiomehsh/freenotes-outline-skill/tree/main/skills/freenotes-outline
```

若 Agent 不支持直接安装 GitHub 路径，可下载本仓库，并将 `skills/freenotes-outline/` 复制到对应的 Skill 目录。

## 使用

将 `.freenotes` 文件提供给 Agent，并使用类似指令：

```text
请使用 freenotes-outline Skill，帮我提取目录并写入 FreeNotes 大纲。
```

运行环境需要 Python 3。扫描版 PDF 可能还需要 `mutool` 和 Tesseract OCR。
