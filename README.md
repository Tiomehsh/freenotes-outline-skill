# FreeNotes Outline Skill

给支持 Skill 的 AI Agent 使用：帮你检查 FreeNotes 导出的 `.freenotes` 文件、提取 PDF 目录，并写入 FreeNotes 大纲。

## 安装

```text
Install https://github.com/Tiomehsh/freenotes-outline-skill/tree/main/skills/freenotes-outline
```

如果不能直接安装 GitHub 路径，就下载仓库，把 `skills/freenotes-outline/` 复制到你的 Agent 的 Skill 目录里。

## 怎么用

把 `.freenotes` 文件交给 Agent，然后说：

```text
请使用 freenotes-outline Skill，帮我提取目录并写入 FreeNotes 大纲。
```

需要 Python 3。扫描版 PDF 可能还需要 `mutool` 和 Tesseract OCR。
