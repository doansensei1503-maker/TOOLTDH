# Video Lab & Media

- Chức năng: Video Lab & Media.
- File:
- [`p2_lab.py`](../files/p2_lab_py.md)
- [`ingest.py`](../files/ingest_py.md)
- [`snaptik.py`](../files/snaptik_py.md)
- Luồng: Import MP4 sở hữu → FFprobe analyze_media → asset READY → phân tích local.
- Input/Output: In: local_path MP4. Out: asset + analysis.
- Dependencies: FFmpeg/FFprobe, ingest.detect_media_format.
- API: /api/p2/*.
- Lỗi chú ý: Thiếu file / sai format / FFprobe lỗi — báo rõ, không bypass.
- Đã hoạt động: Import + verify + offline acceptance.
- Chưa hoàn thiện: Xử lý MP4 nâng cao (giai đoạn 2).
- Định hướng: Giai đoạn 2.
