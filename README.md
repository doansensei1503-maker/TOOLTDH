# TOOLTDH Pro — Nền tảng nghiên cứu xu hướng, phân tích video, quản lý tri thức và tự động hóa sản xuất nội dung

> Local-first · 8GB RAM · Không bắt buộc GPU · Không API trả phí bắt buộc · AI có thể thay thế/mở rộng.

## Giới thiệu

TOOLTDH Pro là nền tảng nghiên cứu xu hướng, phân tích video, quản lý tri thức và tự động hóa sản xuất nội dung với AI mở rộng. Hệ thống tìm kiếm công khai → chấm điểm → chọn TOP5 → nhập MP4 sở hữu → phân tích local → xuất bản có phê duyệt, toàn bộ chạy trên máy local.

## Tính năng hiện có

- **Dashboard local** tại `http://127.0.0.1:8777` (Overview, Project, Search, Queue, Library, Publishing).
- **Search & Discovery**: lập kế hoạch truy vấn, thu thập một Chrome session/một tab, parser trung thực, TOP5, cooperative cancel, thread-safe, khôi phục sau restart.
- **Project & Version**: run bất biến, idempotent theo `retry_key`, replay offline.
- **Video Lab & Media**: nhập MP4 sở hữu, verify FFprobe, asset READY.
- **AI & Analysis**: local analyzer mặc định (evidence/possibility/undetermined/no_data, thang 100đ); Gemini chỉ khi cấu hình.
- **Publishing**: approve + media thật + claim UPLOADING nguyên tử; chỉ `/video/<id>` xác minh mới tính PUBLISHED.
- **Acceptance**: runner Playwright local 15/15 PASS.

## Kiến trúc

```
web UI → dashboard_server (HTTP /api/*) → dashboard_service (logic)
→ SQLite p1_projects.db + state JSON → web render
Topic → query_planner → p1_pipeline → poster/discovery_live → parse → TOP5 → run
```

Chi tiết: [docs/START_HERE.md](docs/START_HERE.md) · [docs/MODULE_ARCHITECTURE.md](docs/MODULE_ARCHITECTURE.md) · [docs/FILE_INDEX.md](docs/FILE_INDEX.md)

## Quick Start

```bash
py main.py --dashboard
# mở http://127.0.0.1:8777
```

Yêu cầu: Windows, Python 3.13, Chrome hệ thống (cho live search), FFmpeg/FFprobe (cho Video Lab). Không cần key trả phí để chạy local.

## Tài liệu

- [Bắt đầu tại đây](docs/START_HERE.md)
- [Danh mục file](docs/FILE_INDEX.md)
- [Bản đồ sửa lỗi](docs/TROUBLESHOOTING.md)
- [Kiến trúc module](docs/MODULE_ARCHITECTURE.md)
- [Roadmap](docs/DEVELOPMENT_ROADMAP.md)
- [Quyết định kỹ thuật](docs/TECHNICAL_DECISIONS.md)
- [Changelog](docs/CHANGELOG.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)

## Roadmap

7 giai đoạn: ổn định repo → Video Lab/MP4 → AI Vision/Speech provider → Knowledge Engine → Trend Intelligence → tự động hóa sản xuất → Remote Workers/đa nền tảng. Chi tiết [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md).

## Giới hạn hiện tại

- 8GB RAM, không GPU bắt buộc — model nặng cần nâng cấp phần cứng.
- Không API AI trả phí mặc định; tính năng cần key sẽ báo trung thực, không đoán.
- Local-first; live TikTok phụ thuộc phiên Chrome đăng nhập + giới hạn nền tảng (không bypass).
- Publish yêu cầu quyền tái sử dụng + approve + media thật.

## Trạng thái phát triển

Đang ở giai đoạn 1 (ổn định kiến trúc & repository). Search-job đã thread-safe (probe offline 6/6 OK). Không tuyên bố tính năng tương lai là hoàn thành — mọi "CHƯA XÁC MINH" được ghi rõ trong docs.
