# Evidence Vault 打卡证据归档工具开发文档

## 1. 项目目标

开发一个本地优先的打卡证据归档工具，用于固定每日上班/下班打卡证据。

核心目标不是替代公司考勤系统，而是生成一套可长期保存、可校验、可追溯的个人证据链。

## 2. 核心使用场景

用户每天上班和下班时拍摄一张 Live Photo 或普通照片，照片内容应包含：

* 门禁设备
* 工牌
* 刷卡动作
* 门禁绿灯或提示结果
* 周围固定环境

工具负责自动完成：

* 读取照片 EXIF
* 提取拍摄时间
* 提取 GPS 坐标
* 计算文件 SHA256
* 保存原始文件
* 生成 metadata.json
* 写入 SQLite
* 按月生成 PDF 归档
* 按月导出 ZIP 证据包

## 3. 技术栈建议

第一版建议使用 Python CLI 实现。

推荐技术栈：

* Python 3.11+
* SQLite
* Pillow
* pillow-heif
* exifread 或 exiftool
* reportlab
* hashlib
* pathlib
* argparse

后续可扩展为：

* iOS Shortcut 自动化
* FastAPI 本地服务
* Web UI
* iCloud / OneDrive / GitHub Private Repo 同步

## 4. 目录结构

```text
evidence-vault/
  app/
    main.py
    config.py
    db.py
    importer.py
    metadata.py
    hashing.py
    report.py
    archive.py
  data/
    originals/
      2026/
        06/
          29/
            in.HEIC
            out.HEIC
    metadata/
      2026/
        06/
          29/
            in.json
            out.json
    reports/
      2026-06.pdf
    archives/
      2026-06.zip
    evidence.db
  requirements.txt
  README.md
```

## 5. 数据模型

SQLite 表：evidence_records

字段：

```sql
CREATE TABLE evidence_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date TEXT NOT NULL,
    direction TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    metadata_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    captured_at TEXT,
    imported_at TEXT NOT NULL,
    gps_lat REAL,
    gps_lng REAL,
    device_model TEXT,
    file_size INTEGER,
    mime_type TEXT,
    note TEXT
);
```

direction 取值：

```text
in
out
```

## 6. 单条 metadata.json 格式

```json
{
  "record_date": "2026-06-29",
  "direction": "in",
  "original_filename": "IMG_3287.HEIC",
  "stored_path": "data/originals/2026/06/29/in.HEIC",
  "sha256": "abc123...",
  "captured_at": "2026-06-29T08:59:12+08:00",
  "imported_at": "2026-06-29T09:03:22+08:00",
  "gps": {
    "lat": 23.123456,
    "lng": 113.123456
  },
  "device": {
    "model": "iPhone",
    "software": null
  },
  "file": {
    "size": 3456789,
    "mime_type": "image/heic"
  },
  "note": "Morning clock-in evidence"
}
```

## 7. CLI 命令设计

### 导入证据

```bash
python -m app.main import \
  --file ~/Downloads/IMG_3287.HEIC \
  --direction in \
  --date 2026-06-29
```

如果不传 date，则优先使用 EXIF 拍摄日期。

### 查看某月记录

```bash
python -m app.main list --month 2026-06
```

### 生成月度 PDF

```bash
python -m app.main report --month 2026-06
```

### 导出月度 ZIP

```bash
python -m app.main archive --month 2026-06
```

ZIP 中应包含：

```text
originals/
metadata/
2026-06.pdf
manifest.json
```

## 8. 导入逻辑

导入时执行以下流程：

1. 校验文件存在
2. 判断文件类型
3. 计算 SHA256
4. 读取 EXIF
5. 提取拍摄时间
6. 提取 GPS
7. 生成目标路径
8. 复制原始文件，不修改原文件
9. 写 metadata.json
10. 写 SQLite
11. 返回导入结果

原则：

* 绝不覆盖已有文件
* 原始文件不可修改
* 如果同一天同方向已存在记录，追加序号，例如 in_2.HEIC
* SHA256 相同的文件提示重复导入

## 9. PDF 报告内容

月度 PDF 应包含：

首页：

```text
Evidence Vault Monthly Report
Month: 2026-06
Generated At: 2026-06-30T23:59:00+08:00
Total Records: 42
```

每日记录：

```text
2026-06-29

IN:
Captured At: 08:59:12
GPS: 23.123456, 113.123456
SHA256: abc123...
File: in.HEIC

OUT:
Captured At: 18:03:45
GPS: 23.123456, 113.123456
SHA256: def456...
File: out.HEIC
```

可选：在 PDF 中嵌入缩略图，但必须保留原始文件在 ZIP 中。

## 10. manifest.json

月度 ZIP 中生成 manifest.json：

```json
{
  "month": "2026-06",
  "generated_at": "2026-06-30T23:59:00+08:00",
  "records": [
    {
      "date": "2026-06-29",
      "direction": "in",
      "file": "originals/2026/06/29/in.HEIC",
      "metadata": "metadata/2026/06/29/in.json",
      "sha256": "abc123..."
    }
  ]
}
```

## 11. 第一版验收标准

第一版完成后，应能做到：

* 可以导入 HEIC/JPG/PNG
* 可以读取 EXIF 时间
* 可以读取 GPS，如果没有 GPS 也不报错
* 可以计算 SHA256
* 可以保存原始文件
* 可以生成 metadata.json
* 可以写入 SQLite
* 可以生成月度 PDF
* 可以导出 ZIP
* 重复文件能识别
* 不修改原始图片

## 12. 后续增强

第二版功能：

* 支持 MOV / Live Photo 配套视频
* 支持 iOS Shortcuts 自动调用
* 支持地图反查地址
* 支持云端同步状态记录
* 支持哈希链：每天记录包含前一条记录 hash
* 支持自动生成年度报告
* 支持 Web UI 查看时间线

## 13. 开发优先级

P0：

* import
* metadata
* sha256
* SQLite
* report
* archive

P1：

* Live Photo 支持
* 视频支持
* PDF 缩略图
* 重复导入检测

P2：

* iCloud / OneDrive / GitHub 同步
* Web UI
* 哈希链
* 地址反查
