"""ค้นคืนแบบ hybrid บน chunk ที่ index แล้ว

ทำงานทั้งตอน authoring และตอน runtime — fallback 2D (extractive + citation)
เป็นเส้นทาง runtime จึงต้องแยกจาก llm/ ให้ขาด (ADR-015, ADR-029)
"""
