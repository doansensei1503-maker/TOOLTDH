# AI & Analysis

- Chức năng: AI & Analysis.
- File:
- [`candidate_analysis.py`](../files/candidate_analysis_py.md)
- [`local_analyzer.py`](../files/local_analyzer_py.md)
- [`local_vision.py`](../files/local_vision_py.md)
- [`relevance.py`](../files/relevance_py.md)
- [`trend_scoring.py`](../files/trend_scoring_py.md)
- [`reviewer.py`](../files/reviewer_py.md)
- [`review_stage.py`](../files/review_stage_py.md)
- Luồng: Frames → local analyzer (evidence/possibility/undetermined/no_data) → 6-dimension 100đ → rank; Gemini chỉ khi TOOLTDH_ANALYZER=gemini.
- Input/Output: In: frames/candidates. Out: verdict + score + breakdown.
- Dependencies: numpy/Pillow/scipy/sklearn (host); không tải model trong nhiệm vụ này.
- API: POST /api/discovery/reanalyze.
- Lỗi chú ý: Thiếu key → NO_QUALIFIED_VIDEO trung thực; không đoán.
- Đã hoạt động: Local-first D3 live-verified.
- Chưa hoàn thiện: Provider architecture Vision/Speech (giai đoạn 3).
- Định hướng: Giai đoạn 3.
