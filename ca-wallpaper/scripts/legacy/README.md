# legacy

- `fix_depth.py`：通过补 LKState 的 position/bounds 视差、写 renderingConfiguration、改 family 来"修景深"。
  **已被真机实验证明无效**（枯木逢春 v1–v5、太空保时捷）。保留仅作记录，不要用于修景深。
- `render_ca.py`：旧渲染器，不支持旋转/缩放/锚点，状态覆盖不完整。请用 `../tendies.py render/flatten`。
