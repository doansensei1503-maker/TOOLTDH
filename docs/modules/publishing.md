# Publishing

- Chức năng: Publishing.
- File:
- [`p3_publish.py`](../files/p3_publish_py.md)
- [`eligibility.py`](../files/eligibility_py.md)
- Luồng: Approve → attach MP4 thật → claim UPLOADING nguyên tử → publisher → PUBLISHED/PROCESSING/FAILED/PUBLISH_UNKNOWN (chỉ /video/<id> tính).
- Input/Output: In: publication_id + confirm. Out: status + posted_url.
- Dependencies: p2_lab media, scheduler account guards.
- API: /api/p3/*, /api/publish/*.
- Lỗi chú ý: RIGHTS_REQUIRED / ACCOUNT_REQUIRED / media thiếu / double-submit (đã claim).
- Đã hoạt động: Guard đầy đủ, không draft-as-publish.
- Chưa hoàn thiện: Remote workers/đa nền tảng (giai đoạn 7).
- Định hướng: Giai đoạn 6–7.
