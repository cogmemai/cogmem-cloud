"""Evaluation Workbench — end-to-end ACP testing and strategy optimization.

The workbench orchestrates the full learning loop:
1. Upload CSV data
2. Analyze data structure to derive an initial MemoryStrategy
3. Ingest data using that strategy (chunk, index, embed, graph)
4. Run automated search-quality tests
5. Record outcome signals
6. Trigger MetaKernel evaluation cycle
7. Apply proposed strategy changes
8. Re-ingest and re-test (repeat for N cycles)
9. Compare strategies across cycles
"""
