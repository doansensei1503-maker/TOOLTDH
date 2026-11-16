# Job & Scheduler

- Chức năng: Job & Scheduler.
- File:
- [`scheduler.py`](../files/scheduler_py.md)
- [`task_queue.py`](../files/task_queue_py.md)
- [`workflow.py`](../files/workflow_py.md)
- Luồng: APScheduler → queue → worker → history/cleanup; P1 search jobs chạy thread riêng + cooperative cancel.
- Input/Output: In: lịch/task. Out: runs + history.
- Dependencies: APScheduler.
- API: /api/scheduler/*, /api/queue/*.
- Lỗi chú ý: Trùng job / mất khôi phục — xem search-discovery.
- Đã hoạt động: Ổn định local.
- Chưa hoàn thiện: Phân tán (giai đoạn 7).
- Định hướng: Giai đoạn 7.
