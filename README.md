# Evidence Vault

本地优先的打卡证据归档 CLI。它会复制原始照片、提取可用 EXIF、计算 SHA256、写入 JSON metadata 和 SQLite，并按月生成 PDF 与 ZIP 证据包。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用

导入上班证据：

```bash
python -m app.main import --file ~/Downloads/IMG_3287.HEIC --direction in --date 2026-06-29
```

`--date` accepts either `YYYY-MM-DD` or compact `YYYYMMDD`.

导入下班证据：

```bash
python -m app.main import --file ~/Downloads/IMG_3299.HEIC --direction out --date 2026-06-29 --note "Evening clock-out evidence"
```

查看某月记录：

```bash
python -m app.main list --month 2026-06
```

查看记录 ID（删除时需要）：

```bash
python -m app.main list --month 2026-06
```

生成月度 PDF：

```bash
python -m app.main report --month 2026-06
```

导出月度 ZIP：

```bash
python -m app.main archive --month 2026-06
```

删除误导入的记录：

```bash
python -m app.main remove --id 2
```

删除会先显示记录详情，并要求输入 `DELETE` 确认。原始照片和 metadata 不会直接丢弃，而是移动到 `data/trash/`，并写入 `removed_record.json` 审计文件。

启用防误操作模式：

```bash
python -m app.main mode set-passcode
python -m app.main mode edit
python -m app.main mode view
python -m app.main mode status
```

设置 passcode 后，`import` 和 `remove` 只允许在 edit mode 下执行。view mode 下仍可 `list`、`report`、`archive`。

edit mode 是短时授权：解锁后 5 分钟过期，并且成功执行一次 `import` 或 `remove` 后会自动回到 view mode，避免忘记手动切回导致误操作。

查看操作记录：

```bash
python -m app.main audit
python -m app.main audit --action import
python -m app.main audit --status failed
```

每次 CLI 操作都会写入 `operation_log`，包括 actor、action、status、timestamp、target record 和非敏感参数。默认 actor 是当前系统用户；如果需要记录具体 maker，可以在命令前设置：

```bash
EV_ACTOR="Austin" python -m app.main import --file ~/Downloads/IMG_3287.HEIC --direction in --date 2026-06-29
```

## 数据位置

运行后会生成：

```text
data/
  originals/
  metadata/
  reports/
  archives/
  evidence.db
```

同一天同方向的多次导入会自动追加序号，例如 `in_2.HEIC`。相同 SHA256 的文件会被拒绝，避免重复导入。
